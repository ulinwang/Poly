"""Compact checkpoint artifacts for long-tick experiment runs.

The raw parquet files remain the lossless record. This module writes a small
state capsule that can be pasted into, or read after, a compacted Codex thread
without replaying every LLM response and action row.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from experiments.parquet_sink import ACTION_COLUMNS, FILL_COLUMNS


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rows_as_dicts(rows: list[tuple], columns: list[str]) -> list[dict]:
    return [dict(zip(columns, row)) for row in rows]


def _belief_payload(row: dict) -> dict | None:
    raw = row.get("raw_response") or ""
    if not raw:
        return None
    try:
        payload = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None
    belief = payload.get("belief_update") if isinstance(payload, dict) else None
    return belief if isinstance(belief, dict) else None


def estimate_context_chars(sim) -> int:
    """Estimate accumulated textual context carried by the run.

    The runner cannot inspect the external Codex chat window, so this proxy
    counts persisted model responses and reasoning fields in action rows. It is
    intentionally conservative enough to trigger handoff files before raw logs
    become unwieldy.
    """
    total = 0
    for row in _rows_as_dicts(sim.actions_log, ACTION_COLUMNS):
        total += len(str(row.get("raw_response") or ""))
        total += len(str(row.get("reasoning") or ""))
    return total


def build_tick_summaries(sim) -> list[dict]:
    actions = _rows_as_dicts(sim.actions_log, ACTION_COLUMNS)
    fills = _rows_as_dicts(sim.fills_log, FILL_COLUMNS)
    if not actions and not fills:
        return []

    tick_values = {
        int(row["tick_idx"]) for row in actions + fills
        if row.get("tick_idx") is not None
    }
    summaries: list[dict] = []
    for tick in sorted(tick_values):
        action_rows = [r for r in actions if int(r["tick_idx"]) == tick]
        fill_rows = [r for r in fills if int(r["tick_idx"]) == tick]
        counts = Counter(str(r.get("action_type") or "UNKNOWN") for r in action_rows)
        trade_rows = [
            r for r in action_rows
            if str(r.get("action_type") or "") != "UPDATE_BELIEF"
        ]
        beliefs = [
            b for b in (_belief_payload(r) for r in action_rows)
            if b is not None
        ]
        yes_probs = [_safe_float(b.get("yes_prob")) for b in beliefs]
        confidences = [_safe_float(b.get("confidence")) for b in beliefs]
        mids = [
            _safe_float(r.get("yes_mid_after"))
            for r in action_rows
            if r.get("yes_mid_after") is not None
        ]
        last_mid = mids[-1] if mids else _safe_float(getattr(sim, "yes_mid", 0.0))
        first_mid = mids[0] if mids else last_mid
        summaries.append({
            "tick": tick,
            "yes_mid_start": round(first_mid, 6),
            "yes_mid_end": round(last_mid, 6),
            "yes_mid_delta": round(last_mid - first_mid, 6),
            "n_actions": len(action_rows),
            "action_counts": dict(sorted(counts.items())),
            "n_trade_actions": len(trade_rows),
            "n_belief_updates": len(beliefs),
            "belief_yes_prob_mean": (
                round(mean(yes_probs), 6) if yes_probs else None
            ),
            "belief_confidence_mean": (
                round(mean(confidences), 6) if confidences else None
            ),
            "n_fills": len(fill_rows),
            "fill_notional": round(
                sum(_safe_float(r.get("notional")) for r in fill_rows), 6,
            ),
            "response_chars": sum(
                len(str(r.get("raw_response") or "")) for r in action_rows
            ),
        })
    return summaries


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _direction_text(sim) -> tuple[str, float | None]:
    resolved = getattr(sim, "market_resolved_yes", None)
    if resolved is None:
        return "unresolved; YES price is interpreted as event probability", None
    truth = 1.0 if int(resolved) == 1 else 0.0
    target = "toward 1.00" if truth == 1.0 else "toward 0.00"
    return target, truth


def write_handoff(
    out_dir: Path,
    *,
    sim,
    tick: int,
    n_ticks: int,
    reason: str,
    max_recent_ticks: int = 5,
) -> Path:
    checkpoint = out_dir / "checkpoint"
    checkpoint.mkdir(parents=True, exist_ok=True)
    summaries = build_tick_summaries(sim)
    recent = summaries[-max_recent_ticks:]
    direction, truth = _direction_text(sim)
    mids = [r["yes_mid_end"] for r in summaries]
    start = mids[0] if mids else _safe_float(getattr(sim, "yes_mid", 0.0))
    end = mids[-1] if mids else start
    min_mid = min(mids) if mids else start
    max_mid = max(mids) if mids else start
    total_actions = sum(r["n_actions"] for r in summaries)
    total_fills = sum(r["n_fills"] for r in summaries)
    total_notional = sum(r["fill_notional"] for r in summaries)
    context_chars = estimate_context_chars(sim)
    context_tokens = round(context_chars / 4)

    lines = [
        "# Compact Experiment Handoff",
        "",
        f"- market_slug: `{getattr(sim, 'market_slug', '')}`",
        f"- question: {getattr(sim, 'question', '')}",
        f"- checkpoint_reason: {reason}",
        f"- current_tick: {tick + 1} / {n_ticks}",
        f"- n_agents: {len(getattr(sim, 'agents', []) or [])}",
        f"- truth_target: {direction}",
        f"- resolved_yes: {truth if truth is not None else 'unresolved'}",
        f"- yes_price_path: start={start:.3f}, end={end:.3f}, "
        f"min={min_mid:.3f}, max={max_mid:.3f}",
        f"- totals: actions={total_actions}, fills={total_fills}, "
        f"fill_notional={total_notional:.3f}",
        f"- estimated_context: chars={context_chars}, tokens~={context_tokens}",
        "",
        "## Recent Tick Capsule",
        "",
    ]
    for row in recent:
        lines.append(
            "- tick {tick}: yes_mid {start:.3f}->{end:.3f}, "
            "actions={actions}, fills={fills}, belief_mean={belief}".format(
                tick=row["tick"] + 1,
                start=row["yes_mid_start"],
                end=row["yes_mid_end"],
                actions=row["action_counts"],
                fills=row["n_fills"],
                belief=row["belief_yes_prob_mean"],
            )
        )
    lines.extend([
        "",
        "## Continuation Notes",
        "",
        "- Full action/fill/position records remain in `raw/*.parquet`.",
        "- Use `checkpoint/tick_summary.jsonl` for compact per-tick replay.",
        "- Interpret YES price as the market-implied probability of event occurrence.",
    ])
    path = checkpoint / "handoff.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def update_checkpoint(
    out_dir: Path,
    *,
    sim,
    tick: int,
    n_ticks: int,
    force_handoff: bool = False,
    reason: str = "tick",
    max_recent_ticks: int = 5,
) -> dict:
    """Refresh tick summaries and optionally write the human handoff."""
    checkpoint = out_dir / "checkpoint"
    checkpoint.mkdir(parents=True, exist_ok=True)
    summaries = build_tick_summaries(sim)
    _write_jsonl(checkpoint / "tick_summary.jsonl", summaries)

    result = {
        "tick_summary": str(checkpoint / "tick_summary.jsonl"),
        "handoff": None,
        "context_chars": estimate_context_chars(sim),
    }
    if force_handoff:
        path = write_handoff(
            out_dir,
            sim=sim,
            tick=tick,
            n_ticks=n_ticks,
            reason=reason,
            max_recent_ticks=max_recent_ticks,
        )
        result["handoff"] = str(path)
        event_path = checkpoint / "compact_events.jsonl"
        event = {
            "tick": tick,
            "reason": reason,
            "context_chars": result["context_chars"],
            "handoff": str(path),
        }
        with event_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return result
