#!/usr/bin/env python3
"""CLI wrapper for runner_stream.py.

Reads a JSON config object from stdin, calls run_stream() (or
resume_stream() when `resume_checkpoint` is supplied), and writes events
as JSON Lines to stdout.

Signals:
  - SIGTERM / SIGINT -> cancel the in-flight run (threading.Event).
  - SIGUSR1          -> request a pause: the tick loop checkpoints at the
                        next tick boundary, emits `paused`, and exits.

Optional config fields:
  - resume_checkpoint : path to a checkpoint pickle to continue from.
  - checkpoint_out    : where to write the checkpoint when paused.
"""
from __future__ import annotations

import json
import signal
import sys
import threading
from pathlib import Path


def _emit(kind: str, data: dict) -> None:
    """Write one runner event before or after the simulation is imported."""
    print(json.dumps({"kind": kind, "data": data}), flush=True)


def main() -> None:
    cancel_event = threading.Event()
    pause_event = threading.Event()

    def _on_sigterm(signum, frame):  # noqa: ARG001
        cancel_event.set()

    def _on_sigusr1(signum, frame):  # noqa: ARG001
        pause_event.set()

    signal.signal(signal.SIGTERM, _on_sigterm)
    signal.signal(signal.SIGINT, _on_sigterm)
    # SIGUSR1 requests a clean checkpoint-and-exit at the next tick boundary.
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, _on_sigusr1)

    # Import lazily so missing runtime dependencies can be reported through the
    # same structured event stream as simulation failures. The web UI can then
    # show an actionable message instead of only "process exited with code 1".
    try:
        from .runner_stream import resume_stream, run_stream
    except ModuleNotFoundError as exc:
        package = exc.name or "unknown package"
        _emit(
            "error",
            {
                "message": (
                    f"Simulation dependency missing: {package}. "
                    "Run `uv sync --frozen` from the project root."
                )
            },
        )
        _emit("__end__", {})
        sys.exit(1)
    except ImportError as exc:
        _emit("error", {"message": f"Simulation runner failed to import: {exc}"})
        _emit("__end__", {})
        sys.exit(1)

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

    resume_checkpoint = config.get("resume_checkpoint")
    checkpoint_out = config.get("checkpoint_out")

    if not resume_checkpoint:
        # Fresh run requires the full config; a resume reads these from
        # the checkpoint instead.
        required = {
            "slug", "n_agents", "n_ticks", "persona_set",
            "seed", "temperature", "data_dir",
        }
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
        _emit(kind, data)

    # 3. Run (or resume) the simulation
    try:
        if resume_checkpoint:
            kwargs = dict(
                resume_checkpoint=resume_checkpoint,
                on_event=on_event,
                cancel=cancel_event,
                pause=pause_event,
                checkpoint_out=checkpoint_out,
            )
            for key in (
                "api_key", "base_url", "model",
                "request_timeout_seconds", "max_retries", "max_tokens",
            ):
                if key in config and config[key] is not None:
                    kwargs[key] = config[key]
            resume_stream(**kwargs)
        else:
            kwargs = dict(
                slug=config["slug"],
                n_agents=config["n_agents"],
                n_ticks_override=config["n_ticks"] if config["n_ticks"] is not None else None,
                persona_set=config["persona_set"],
                seed=config["seed"],
                temperature=config["temperature"],
                on_event=on_event,
                cancel=cancel_event,
                pause=pause_event,
                checkpoint_out=checkpoint_out,
                data_dir=Path(config["data_dir"]),
                market_context=config.get("market_context"),
            )
            # Pass through optional LLM overrides from frontend settings
            for key in (
                "api_key", "base_url", "model",
                "request_timeout_seconds", "max_retries", "max_tokens",
            ):
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
