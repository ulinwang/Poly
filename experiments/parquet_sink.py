"""Persist sim logs to `output/<exp_id>/raw/*.parquet` and
`output/<exp_id>/raw/llm_calls.jsonl`.

Schema mirrors the v7 ClickHouse insert tuples 1:1 so analyses can
run against either source. Used by `experiments.runner` in
dual-write mode (Stage 4 default per user decision).
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Sequence

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


# Schemas mirror the insert tuples already used by data.store.clickhouse.
ACTION_COLUMNS = [
    "sim_id", "tick_idx", "agent_id",
    "action_type", "outcome", "side",
    "price", "size_usd",
    "yes_mid_before", "yes_mid_after", "shares_taken",
    "n_fills",
    "reasoning", "raw_response", "api_latency_ms", "api_error", "fetched_at",
]

FILL_COLUMNS = [
    "sim_id", "tick_idx", "maker_order_id", "taker_order_id",
    "maker_agent_id", "taker_agent_id", "outcome", "maker_side",
    "price", "size", "notional", "fetched_at",
]

POSITION_COLUMNS = [
    "sim_id", "tick_idx", "agent_id",
    "yes_shares", "no_shares", "cash",
    "realized_pnl", "unrealized_pnl",
]

PERSONA_COLUMNS = [
    "sim_id", "agent_id", "persona_type",
    "risk_aversion", "capital_initial", "profile_text",
]


def write_parquet(
    rows: Sequence[tuple], columns: list[str], path: Path,
    compression: str = "zstd",
) -> int:
    """Write `rows` (list[tuple]) to `path` as parquet. Returns row
    count. No-op on empty input (creates an empty file with schema)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        # Empty: write a header-only parquet so the file always exists.
        pa_table = pa.table({c: pa.array([], type=pa.string()) for c in columns})
        pq.write_table(pa_table, path, compression=compression)
        return 0
    df = pd.DataFrame(rows, columns=columns)
    df.to_parquet(path, compression=compression, index=False)
    return len(df)


def dump_simulation(
    sim, out_dir: Path, compression: str = "zstd",
    persona_rows: list[tuple] | None = None,
) -> dict:
    """Write all four sim logs to `out_dir/raw/*.parquet`. Returns
    {filename: rows_written}."""
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    out: dict[str, int] = {}
    out["agent_actions"] = write_parquet(
        sim.actions_log, ACTION_COLUMNS,
        raw / "agent_actions.parquet", compression,
    )
    out["agent_fills"] = write_parquet(
        sim.fills_log, FILL_COLUMNS,
        raw / "agent_fills.parquet", compression,
    )
    out["agent_positions"] = write_parquet(
        sim.positions_log, POSITION_COLUMNS,
        raw / "agent_positions.parquet", compression,
    )
    if persona_rows is not None:
        out["agent_personas"] = write_parquet(
            persona_rows, PERSONA_COLUMNS,
            raw / "agent_personas.parquet", compression,
        )
    return out


_LLM_CALLS_LOCK = threading.Lock()


def append_llm_call(
    out_dir: Path, sim_id: str, tick: int, agent_id: int,
    system_prompt: str, user_prompt: str, response: str,
) -> None:
    """One JSONL entry per LLM call for full replay capability.
    Append-only — runner calls this from inside the per-tick loop.

    Thread-safe via a module-level lock: v9.3's concurrent per-tick
    decisions would otherwise interleave bytes from different lines."""
    raw = out_dir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    p = raw / "llm_calls.jsonl"
    line = json.dumps({
        "sim_id": sim_id, "tick": tick, "agent_id": agent_id,
        "system": system_prompt, "user": user_prompt, "response": response,
    }, ensure_ascii=False)
    with _LLM_CALLS_LOCK, p.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)
