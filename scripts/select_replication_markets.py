"""v13 B1 — Sample a panel of resolved binary markets for the
external-validity replication experiment.

Usage
-----
Select:
  python scripts/select_replication_markets.py \
      --n 10 --balance yes_no --min-volume 5000 --max-volume 5000000 \
      --min-wallets 30 --seed 0 \
      --out experiments/configs/b1_markets.yaml

Validate an existing selection (no DB calls):
  python scripts/select_replication_markets.py \
      --validate experiments/configs/b1_markets.yaml

Selection algorithm
-------------------
1. Pull candidates via ``data.query.markets.select_resolved_markets``
   with the user-supplied volume / wallets / binary filters.
2. Look up each candidate's winning_idx via ``get_market_meta`` (the
   selector helper doesn't return it).
3. Bin candidates into 10 volume deciles (computed from the candidate
   pool itself, not the full population — so the panel always spans
   the available range).
4. Sample ``--n`` rows balanced on winning_idx (5 YES + 5 NO by
   default, within tolerance ±1) and spread across the deciles —
   we cycle through deciles in deterministic order before picking.
5. Output YAML with ``{slug, condition_id, winning_idx, volume,
   end_date, question}`` per market.

The sampler is deterministic given ``--seed`` (default 0).

Validation mode
---------------
Reads the YAML and reports:
* balance: count of yes-resolved vs no-resolved
* volume range and per-decile coverage
* unique-slug check
* problems are printed to stderr; exit code 1 on any failure.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import random
import sys
from pathlib import Path
from typing import Optional

import yaml


log = logging.getLogger(__name__)


# ---------------------------------------------------------------
# Selection
# ---------------------------------------------------------------


def _volume_decile(volumes: list[float], v: float) -> int:
    """0..9 index of `v` in the sorted `volumes` distribution."""
    if not volumes:
        return 0
    sorted_v = sorted(volumes)
    n = len(sorted_v)
    # find first index where sorted_v[i] >= v
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if sorted_v[mid] < v:
            lo = mid + 1
        else:
            hi = mid
    rank = lo / max(n - 1, 1)
    return min(9, max(0, int(rank * 10)))


def _balance_pick(
    candidates: list[dict],
    n: int,
    rng: random.Random,
    balance: str,
    tolerance: int = 1,
) -> list[dict]:
    """Pick `n` rows; if balance='yes_no', aim for an even YES/NO split
    on winning_idx with tolerance `tolerance`. Spreads across volume
    deciles (cycles deciles each pick)."""
    if not candidates:
        return []
    volumes = [c["volume"] for c in candidates]
    # group by (winning_idx, decile)
    bucket: dict[tuple[int, int], list[dict]] = {}
    for c in candidates:
        key = (int(c["winning_idx"]), _volume_decile(volumes, c["volume"]))
        bucket.setdefault(key, []).append(c)
    # Deterministic shuffle inside buckets
    for v in bucket.values():
        rng.shuffle(v)

    if balance != "yes_no":
        # Spread across deciles only.
        out: list[dict] = []
        deciles_cycle = list(range(10))
        rng.shuffle(deciles_cycle)
        i = 0
        used: set[str] = set()
        attempts = 0
        while len(out) < n and attempts < 10 * n + 50:
            d = deciles_cycle[i % 10]
            picked = None
            for key, rows in bucket.items():
                if key[1] != d:
                    continue
                while rows:
                    cand = rows.pop()
                    if cand["slug"] not in used:
                        picked = cand
                        break
                if picked:
                    break
            if picked:
                out.append(picked)
                used.add(picked["slug"])
            i += 1
            attempts += 1
        return out

    n_yes_target = n // 2
    n_no_target = n - n_yes_target
    picks_yes: list[dict] = []
    picks_no: list[dict] = []
    used: set[str] = set()

    deciles_cycle = list(range(10))
    rng.shuffle(deciles_cycle)

    def _take(target_idx: int, decile: int) -> Optional[dict]:
        rows = bucket.get((target_idx, decile))
        if not rows:
            return None
        while rows:
            c = rows.pop()
            if c["slug"] not in used:
                used.add(c["slug"])
                return c
        return None

    # Round-robin alternating YES / NO across deciles
    i = 0
    while (len(picks_yes) < n_yes_target or len(picks_no) < n_no_target) \
            and i < 10 * n * 4:
        d = deciles_cycle[i % 10]
        if len(picks_yes) < n_yes_target:
            c = _take(1, d)
            if c is not None:
                picks_yes.append(c)
        if len(picks_no) < n_no_target:
            c = _take(0, d)
            if c is not None:
                picks_no.append(c)
        i += 1

    # If we couldn't hit the target, relax tolerance: take anything left.
    needed = n - len(picks_yes) - len(picks_no)
    if needed > 0:
        leftover: list[dict] = []
        for rows in bucket.values():
            leftover.extend(rows)
        rng.shuffle(leftover)
        for c in leftover:
            if needed <= 0:
                break
            if c["slug"] in used:
                continue
            used.add(c["slug"])
            if int(c["winning_idx"]) == 1 and len(picks_yes) < n_yes_target + tolerance:
                picks_yes.append(c); needed -= 1
            elif int(c["winning_idx"]) == 0 and len(picks_no) < n_no_target + tolerance:
                picks_no.append(c); needed -= 1

    out = picks_yes + picks_no
    # Sort deterministically for stable output
    out.sort(key=lambda r: (r["winning_idx"], r["volume"], r["slug"]))
    return out


def select_markets(
    *,
    n: int,
    min_volume: float,
    max_volume: float,
    min_wallets: int,
    balance: str = "yes_no",
    seed: int = 0,
    ch=None,
    select_fn=None,
    meta_fn=None,
    candidate_limit: int = 500,
) -> list[dict]:
    """Pure-logic entry: takes injected ``select_fn`` and ``meta_fn``
    so the test suite can run without ClickHouse."""
    if select_fn is None:
        from data.query.markets import select_resolved_markets as select_fn  # type: ignore  # noqa
    if meta_fn is None:
        from data.query.markets import get_market_meta as meta_fn  # type: ignore  # noqa

    rows = select_fn(
        min_volume=min_volume, max_volume=max_volume,
        min_wallets=min_wallets, require_binary=True,
        limit=candidate_limit, ch=ch,
    )
    candidates: list[dict] = []
    for row in rows:
        slug, condition_id, volume, n_wallets, end_date, question = row
        meta = meta_fn(slug, ch=ch)
        if meta is None:
            continue
        wi = meta.get("winning_idx")
        if wi is None or wi < 0:
            # unresolved or unknown — skip
            continue
        candidates.append({
            "slug": slug,
            "condition_id": condition_id,
            "winning_idx": int(wi),
            "volume": float(volume or 0.0),
            "end_date": (end_date.isoformat()
                         if hasattr(end_date, "isoformat") else str(end_date)),
            "question": str(question or ""),
            "n_wallets": int(n_wallets),
        })
    rng = random.Random(seed)
    return _balance_pick(candidates, n=n, rng=rng, balance=balance)


# ---------------------------------------------------------------
# Validation
# ---------------------------------------------------------------


def validate_selection(yaml_path: Path) -> tuple[bool, dict]:
    """Read the YAML and report balance + volume coverage.

    Returns (ok, report)."""
    data = yaml.safe_load(yaml_path.read_text()) or {}
    markets = data.get("markets") or []
    report: dict = {"path": str(yaml_path), "n": len(markets), "problems": []}

    yes = sum(1 for m in markets if int(m.get("winning_idx", -1)) == 1)
    no = sum(1 for m in markets if int(m.get("winning_idx", -1)) == 0)
    report["yes_resolved"] = yes
    report["no_resolved"] = no
    if abs(yes - no) > 1:
        report["problems"].append(
            f"yes/no imbalance: {yes} YES vs {no} NO (tolerance ±1)"
        )

    slugs = [m["slug"] for m in markets]
    if len(set(slugs)) != len(slugs):
        report["problems"].append("duplicate slugs in selection")

    volumes = [float(m.get("volume", 0.0)) for m in markets]
    if volumes:
        report["volume_min"] = min(volumes)
        report["volume_max"] = max(volumes)
        deciles_hit = {_volume_decile(volumes, v) for v in volumes}
        report["deciles_hit"] = sorted(deciles_hit)
        if len(deciles_hit) < max(2, len(markets) // 3):
            report["problems"].append(
                f"poor volume spread: only {len(deciles_hit)} deciles hit "
                f"(want >= {max(2, len(markets) // 3)})"
            )
    return (len(report["problems"]) == 0, report)


# ---------------------------------------------------------------
# CLI
# ---------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=10, help="number of markets to select")
    parser.add_argument("--balance", choices=["yes_no", "none"], default="yes_no")
    parser.add_argument("--min-volume", type=float, default=5_000.0)
    parser.add_argument("--max-volume", type=float, default=5_000_000.0)
    parser.add_argument("--min-wallets", type=int, default=30)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--out", type=Path,
                        default=Path("experiments/configs/b1_markets.yaml"))
    parser.add_argument("--candidate-limit", type=int, default=500,
                        help="upper bound on candidates pulled from DB")
    parser.add_argument("--validate", type=Path, default=None,
                        help="validate an existing YAML and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    if args.validate is not None:
        ok, report = validate_selection(args.validate)
        print(json.dumps(report, indent=2, default=str))
        return 0 if ok else 1

    markets = select_markets(
        n=args.n,
        min_volume=args.min_volume,
        max_volume=args.max_volume,
        min_wallets=args.min_wallets,
        balance=args.balance,
        seed=args.seed,
        candidate_limit=args.candidate_limit,
    )
    log.info("selected %d markets (target %d)", len(markets), args.n)

    payload = {
        "_generated_by": "scripts/select_replication_markets.py",
        "seed": args.seed,
        "balance": args.balance,
        "min_volume": args.min_volume,
        "max_volume": args.max_volume,
        "min_wallets": args.min_wallets,
        "n_requested": args.n,
        "n_returned": len(markets),
        "markets": markets,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(yaml.safe_dump(payload, sort_keys=False,
                                       default_flow_style=False))
    log.info("wrote %s", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
