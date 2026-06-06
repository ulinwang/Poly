"""Checkpoint persistence for pausing / resuming a streaming run.

A checkpoint is a single pickle file holding *everything* the tick loop in
`runner_stream.run_stream` needs to continue from a tick boundary:

  - the live `Simulation` (agents incl. cash/positions/belief/memory, the
    YES/NO order books, every per-tick log, mid histories) — this is the
    same object `sensitivity_run` deepcopies in env.py, so it pickles cleanly;
  - the env's RNG state (`random.Random.getstate()`), so within-tick agent
    ordering shuffles continue from exactly where they stopped;
  - `next_tick`: the index of the *next* tick to run (the loop resumes at
    `range(next_tick, n_ticks)`);
  - the run parameters (slug, persona_set, seed, temperature, n_ticks),
    the resolved `market_meta`, and the derived `priors` — so the resumed
    process does not need to re-derive priors or re-resolve the market and
    therefore reproduces the original run bit-for-bit from the pause point.

The pickle protocol is pinned to 4 for stable cross-version round-trips.

Pausing only happens at a tick boundary (never mid-LLM-call), so the saved
`Simulation` is always internally consistent.
"""
from __future__ import annotations

import pickle
import random
from pathlib import Path
from typing import Any

# Pinned for reproducible round-trips across Python minor versions.
PICKLE_PROTOCOL = 4

# Bumped if the on-disk layout changes incompatibly.
CHECKPOINT_VERSION = 1


def save_checkpoint(
    path: str | Path,
    *,
    sim: Any,
    rng: random.Random,
    next_tick: int,
    n_ticks: int,
    slug: str,
    persona_set: str,
    seed: int,
    temperature: float,
    market_meta: dict,
    priors: dict,
    prev_yes_mid: float | None,
) -> None:
    """Serialize the full run state to `path` (pickle, protocol 4).

    `rng` is the env's live `random.Random`; we persist `rng.getstate()`
    so the resumed run reconstructs an identical generator.
    """
    payload = {
        "version": CHECKPOINT_VERSION,
        "sim": sim,
        "rng_state": rng.getstate(),
        "next_tick": int(next_tick),
        "n_ticks": int(n_ticks),
        "slug": slug,
        "persona_set": persona_set,
        "seed": int(seed),
        "temperature": float(temperature),
        "market_meta": market_meta,
        "priors": priors,
        "prev_yes_mid": (float(prev_yes_mid) if prev_yes_mid is not None else None),
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # Write atomically: dump to a temp sibling, then rename.
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("wb") as fh:
        pickle.dump(payload, fh, protocol=PICKLE_PROTOCOL)
    tmp.replace(p)


def load_checkpoint(path: str | Path) -> dict:
    """Deserialize a checkpoint written by `save_checkpoint`.

    Returns the payload dict; `rng_state` should be applied to a fresh
    `random.Random` via `rng.setstate(payload["rng_state"])`.
    """
    with Path(path).open("rb") as fh:
        payload = pickle.load(fh)
    version = payload.get("version")
    if version != CHECKPOINT_VERSION:
        raise ValueError(
            f"checkpoint version {version!r} != supported {CHECKPOINT_VERSION!r}"
        )
    return payload


def rng_from_state(state: Any) -> random.Random:
    """Build a `random.Random` restored to a previously saved state."""
    rng = random.Random()
    rng.setstate(state)
    return rng
