#!/usr/bin/env python3
"""CLI wrapper for runner_stream.py.

Reads a JSON config object from stdin, calls run_stream(), and writes
events as JSON Lines to stdout.  Catches SIGTERM to cancel an in-flight
run via a threading.Event passed to run_stream().
"""
from __future__ import annotations

import json
import signal
import sys
import threading
from pathlib import Path

from webapp.runner_stream import run_stream


def main() -> None:
    cancel_event = threading.Event()

    def _on_sigterm(signum, frame):  # noqa: ARG001
        cancel_event.set()

    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)

    # 1. Read config from stdin
    try:
        config_raw = sys.stdin.read()
        if not config_raw:
            print(json.dumps({"kind": "error", "data": {"message": "empty stdin"}}))
            sys.exit(1)
        config = json.loads(config_raw)
    except json.JSONDecodeError as exc:
        print(
            json.dumps(
                {"kind": "error", "data": {"message": f"invalid JSON on stdin: {exc}"}}
            )
        )
        sys.exit(1)

    required = {"slug", "n_agents", "n_ticks", "persona_set", "seed", "temperature", "data_dir"}
    missing = required - set(config.keys())
    if missing:
        print(
            json.dumps(
                {"kind": "error", "data": {"message": f"missing fields: {sorted(missing)}"}}
            )
        )
        sys.exit(1)

    # 2. Stream events as JSON Lines
    def on_event(kind: str, data: dict) -> None:
        line = json.dumps({"kind": kind, "data": data})
        print(line, flush=True)

    # 3. Run simulation
    try:
        kwargs = dict(
            slug=config["slug"],
            n_agents=config["n_agents"],
            n_ticks_override=config["n_ticks"] if config["n_ticks"] is not None else None,
            persona_set=config["persona_set"],
            seed=config["seed"],
            temperature=config["temperature"],
            on_event=on_event,
            cancel=cancel_event,
            data_dir=Path(config["data_dir"]),
        )
        # Pass through optional LLM overrides from frontend settings
        for key in ("api_key", "base_url", "model"):
            if key in config and config[key] is not None:
                kwargs[key] = config[key]
        run_stream(**kwargs)
    except Exception as exc:  # noqa: BLE001
        on_event("error", {"message": str(exc)})
        sys.exit(1)
    finally:
        on_event("__end__", {})


if __name__ == "__main__":
    main()
