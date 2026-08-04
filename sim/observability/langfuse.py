"""Fail-open Langfuse v4 adapter for runner and Agent Loop lifecycle events.

The module deliberately avoids importing ``langfuse`` at import time. The SDK
is loaded only when telemetry is explicitly enabled and credentials exist, so
the default simulation path has no telemetry dependency or network side effect.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from typing import TYPE_CHECKING, Any, Literal, Protocol

if TYPE_CHECKING:
    from agent.loop import AgentLoopEvent, AgentLoopObserver


log = logging.getLogger(__name__)

CapturePolicy = Literal["metadata", "full"]
_TERMINAL_RUNNER_EVENTS = frozenset({"done", "paused", "cancelled", "error"})
_SENSITIVE_KEYS = frozenset({
    "api_key", "apikey", "authorization", "cookie", "password",
    "public_key", "secret", "secret_key", "token", "access_token",
    "refresh_token", "reasoning_content", "raw", "raw_response",
})
_CONTENT_KEYS = frozenset({
    "arguments", "content", "description", "input", "messages", "output",
    "question", "reasoning", "results", "system_prompt", "text", "user_prompt",
    "variables",
})


class _Observation(Protocol):
    def update(self, **kwargs: Any) -> Any: ...

    def score(self, **kwargs: Any) -> Any: ...


class _LangfuseClient(Protocol):
    def start_as_current_observation(self, **kwargs: Any) -> AbstractContextManager: ...

    def flush(self) -> Any: ...


def _clean_key(key: object) -> str:
    return str(key).strip().lower().replace("-", "_")


def sanitize_payload(
    value: Any,
    *,
    capture_policy: CapturePolicy,
    max_string_chars: int = 4_000,
) -> Any:
    """Return JSON-safe telemetry data with secrets and hidden reasoning removed."""
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for original_key, item in value.items():
            key = str(original_key)
            normalized = _clean_key(key)
            # Private payload entries are process-local integration objects.
            # They must never be serialized into Langfuse input or metadata.
            if key.startswith("_"):
                continue
            if normalized in _SENSITIVE_KEYS:
                clean[key] = "[REDACTED]"
                continue
            if capture_policy == "metadata" and normalized in _CONTENT_KEYS:
                continue
            clean[key] = sanitize_payload(
                item,
                capture_policy=capture_policy,
                max_string_chars=max_string_chars,
            )
        return clean
    if isinstance(value, (list, tuple, set, frozenset)):
        return [
            sanitize_payload(
                item,
                capture_policy=capture_policy,
                max_string_chars=max_string_chars,
            )
            for item in value
        ]
    if isinstance(value, str):
        return value[:max_string_chars]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:max_string_chars]


class NoOpObservability:
    """Default runtime: no imports, threads, buffering, or network I/O."""

    agent_loop_observer: "AgentLoopObserver"

    def __init__(self) -> None:
        self.agent_loop_observer = self

    def on_event(self, event: "AgentLoopEvent") -> None:  # noqa: ARG002
        return

    def on_runner_event(self, kind: str, payload: Mapping[str, Any]) -> None:  # noqa: ARG002
        return

    def record_fatal_error(self, exc: BaseException) -> None:  # noqa: ARG002
        return

    def close(self) -> None:
        return


class LangfuseObservability:
    """Map Poly lifecycle events onto a nested Langfuse observation tree."""

    agent_loop_observer: "AgentLoopObserver"

    def __init__(
        self,
        *,
        client: _LangfuseClient,
        propagate_attributes: Callable[..., AbstractContextManager],
        session_id: str,
        metadata: Mapping[str, Any],
        capture_policy: CapturePolicy = "metadata",
        release: str | None = None,
        environment: str = "development",
        flush_timeout_seconds: float = 5.0,
    ) -> None:
        self.agent_loop_observer = self
        self._client = client
        self._propagate_attributes = propagate_attributes
        self._session_id = str(session_id)
        self._capture_policy = capture_policy
        self._release = release
        self._environment = environment
        self._flush_timeout_seconds = max(0.0, float(flush_timeout_seconds))
        self._disabled = False
        self._closed = False
        self._flushed = False
        self._attributes_cm: AbstractContextManager | None = None
        self._run_cm: AbstractContextManager | None = None
        self._run_observation: _Observation | None = None
        self._tick_cm: AbstractContextManager | None = None
        self._tick_observation: _Observation | None = None
        self._loop_cm: AbstractContextManager | None = None
        self._loop_observation: _Observation | None = None
        self._generation_cm: AbstractContextManager | None = None
        self._generation_observation: _Observation | None = None
        self._tool_cm: AbstractContextManager | None = None
        self._tool_observation: _Observation | None = None
        self._loop_score_targets: dict[str, _Observation] = {}
        self._start_run(metadata)

    def _safe(self, operation: Callable[[], None]) -> None:
        if self._disabled or self._closed:
            return
        try:
            operation()
        except Exception:  # noqa: BLE001 - telemetry must never change the run
            log.warning("Langfuse observability disabled after adapter failure", exc_info=True)
            self._disabled = True
            self._force_close_contexts()

    def _start_run(self, metadata: Mapping[str, Any]) -> None:
        clean_metadata = sanitize_payload(metadata, capture_policy="metadata")
        try:
            self._attributes_cm = self._propagate_attributes(
                trace_name="poly.experiment",
                session_id=self._session_id,
                tags=["poly", "agent-simulation"],
                version=self._release,
                metadata=clean_metadata,
                environment=self._environment,
            )
            self._attributes_cm.__enter__()
            self._run_cm = self._client.start_as_current_observation(
                name="poly.experiment",
                as_type="span",
                metadata=clean_metadata,
                version=self._release,
            )
            self._run_observation = self._run_cm.__enter__()
        except Exception:
            self._force_close_contexts()
            raise

    def on_runner_event(self, kind: str, payload: Mapping[str, Any]) -> None:
        self._safe(lambda: self._on_runner_event(kind, payload))

    def _on_runner_event(self, kind: str, payload: Mapping[str, Any]) -> None:
        clean = sanitize_payload(payload, capture_policy=self._capture_policy)
        metadata = sanitize_payload(payload, capture_policy="metadata")
        if kind == "tick_started":
            self._finish_tick()
            self._tick_cm = self._client.start_as_current_observation(
                name=f"poly.tick.{int(payload.get('tick', 0))}",
                as_type="span",
                input=clean or None,
                metadata=metadata,
                version=self._release,
            )
            self._tick_observation = self._tick_cm.__enter__()
        elif kind == "tick_finished":
            self._update(self._tick_observation, output=clean or None, metadata=metadata)
            self._finish_tick()
        elif kind in {"run_started", "run_resumed", "env_ready", "settled"}:
            self._update(self._run_observation, metadata={kind: metadata})
            if kind == "settled":
                self._update(self._run_observation, output=clean or None)
        elif kind == "error":
            self._update(
                self._run_observation,
                level="ERROR",
                status_message=str(payload.get("message", "runner error"))[:500],
                output=clean or None,
            )
        elif kind == "agent_scores":
            decision_id = str(payload.get("decision_id", ""))
            target = self._loop_score_targets.pop(decision_id, None)
            self._emit_scores(target, payload.get("scores", ()))
        elif kind == "run_scores":
            self._emit_scores(self._run_observation, payload.get("scores", ()))

        if kind in _TERMINAL_RUNNER_EVENTS:
            self._finish_run(kind=kind, payload=clean)
            self._flush_with_timeout()

    def on_event(self, event: "AgentLoopEvent") -> None:
        self._safe(lambda: self._on_agent_loop_event(event))

    def _on_agent_loop_event(self, event: "AgentLoopEvent") -> None:
        kind = getattr(event.kind, "value", event.kind)
        payload = dict(event.payload)
        clean = sanitize_payload(payload, capture_policy=self._capture_policy)
        metadata = sanitize_payload(payload, capture_policy="metadata")
        context = event.context.loop
        identity = {
            "run_id": context.run_id,
            "tick": context.tick,
            "agent_id": context.agent_id,
            "decision_id": context.decision_id,
            "stage": event.context.stage.value,
            "iteration": event.context.iteration,
            "sequence": event.sequence,
        }

        if kind == "loop_started":
            self._finish_loop()
            self._loop_cm = self._client.start_as_current_observation(
                name="poly.agent-loop",
                as_type="agent",
                input=clean or None,
                metadata={**identity, **metadata},
                version=self._release,
            )
            self._loop_observation = self._loop_cm.__enter__()
        elif kind == "generation_started":
            self._finish_generation()
            managed_prompt = payload.get("_langfuse_prompt")
            model_parameters = {
                key: payload[key]
                for key in ("temperature", "tool_choice")
                if payload.get(key) is not None
            }
            generation_kwargs: dict[str, Any] = {
                "name": f"poly.generation.{event.context.stage.value}",
                "as_type": "generation",
                "input": clean or None,
                "metadata": {**identity, **metadata},
                "model": str(payload.get("model") or "unknown"),
                "model_parameters": model_parameters or None,
                "version": self._release,
            }
            if managed_prompt is not None:
                generation_kwargs["prompt"] = managed_prompt
            self._generation_cm = self._client.start_as_current_observation(
                **generation_kwargs,
            )
            self._generation_observation = self._generation_cm.__enter__()
        elif kind == "generation_completed":
            usage = {
                "input_tokens": int(payload.get("prompt_tokens", 0)),
                "output_tokens": int(payload.get("completion_tokens", 0)),
            }
            usage["total_tokens"] = usage["input_tokens"] + usage["output_tokens"]
            update: dict[str, Any] = {
                "output": clean or None,
                "metadata": metadata,
                "usage_details": usage,
            }
            if payload.get("status") == "error":
                update.update(
                    level="ERROR",
                    status_message=str(payload.get("error", "generation error"))[:500],
                )
            self._update(self._generation_observation, **update)
            self._finish_generation()
        elif kind == "tool_started":
            self._finish_tool()
            tool_name = str(payload.get("tool_name") or payload.get("name") or "tool")
            self._tool_cm = self._client.start_as_current_observation(
                name=f"poly.tool.{tool_name}",
                as_type="tool",
                input=clean or None,
                metadata={**identity, **metadata},
                version=self._release,
            )
            self._tool_observation = self._tool_cm.__enter__()
        elif kind == "tool_completed":
            update = {"output": clean or None, "metadata": metadata}
            if payload.get("status") == "error":
                update.update(
                    level="ERROR",
                    status_message=str(payload.get("error", "tool error"))[:500],
                )
            self._update(self._tool_observation, **update)
            self._finish_tool()
        elif kind == "loop_failed":
            self._update(
                self._loop_observation,
                level="ERROR",
                status_message=str(payload.get("error", "agent loop error"))[:500],
                metadata={**identity, **metadata},
            )
        elif kind == "loop_completed":
            self._update(
                self._loop_observation,
                output=clean or None,
                metadata={**identity, **metadata},
            )
            if self._loop_observation is not None:
                self._loop_score_targets[context.decision_id] = self._loop_observation
            self._finish_loop()

    @staticmethod
    def _emit_scores(observation: _Observation | None, scores: Any) -> None:
        if observation is None or not hasattr(observation, "score"):
            return
        for score in scores or ():
            if not isinstance(score, Mapping):
                continue
            observation.score(
                name=str(score.get("name", "poly.evaluation")),
                value=float(score.get("value", 0.0)),
                data_type="NUMERIC",
                metadata={
                    "passed": bool(score.get("passed")),
                    "hard": bool(score.get("hard")),
                    "evaluator_version": str(score.get("evaluator_version", "1")),
                },
            )

    @staticmethod
    def _update(observation: _Observation | None, **kwargs: Any) -> None:
        if observation is not None:
            observation.update(**kwargs)

    @staticmethod
    def _exit(cm: AbstractContextManager | None) -> None:
        if cm is not None:
            cm.__exit__(None, None, None)

    def _finish_tool(self) -> None:
        self._exit(self._tool_cm)
        self._tool_cm = None
        self._tool_observation = None

    def _finish_generation(self) -> None:
        self._finish_tool()
        self._exit(self._generation_cm)
        self._generation_cm = None
        self._generation_observation = None

    def _finish_loop(self) -> None:
        self._finish_generation()
        self._exit(self._loop_cm)
        self._loop_cm = None
        self._loop_observation = None

    def _finish_tick(self) -> None:
        self._finish_loop()
        self._exit(self._tick_cm)
        self._tick_cm = None
        self._tick_observation = None

    def _finish_run(self, *, kind: str, payload: Any) -> None:
        self._finish_tick()
        self._update(
            self._run_observation,
            output={"status": kind, "event": payload},
            level="ERROR" if kind == "error" else "DEFAULT",
        )
        self._exit(self._run_cm)
        self._run_cm = None
        self._run_observation = None
        self._exit(self._attributes_cm)
        self._attributes_cm = None
        self._loop_score_targets.clear()

    def _force_close_contexts(self) -> None:
        """Best-effort unwind used only after an adapter/SDK failure."""
        for cm_attr, observation_attr in (
            ("_tool_cm", "_tool_observation"),
            ("_generation_cm", "_generation_observation"),
            ("_loop_cm", "_loop_observation"),
            ("_tick_cm", "_tick_observation"),
            ("_run_cm", "_run_observation"),
            ("_attributes_cm", None),
        ):
            cm = getattr(self, cm_attr, None)
            if cm is not None:
                try:
                    cm.__exit__(None, None, None)
                except Exception:  # noqa: BLE001
                    log.debug("Langfuse context cleanup failed", exc_info=True)
            setattr(self, cm_attr, None)
            if observation_attr is not None:
                setattr(self, observation_attr, None)

    def _flush_with_timeout(self) -> None:
        if self._flushed:
            return
        self._flushed = True
        flush_thread = threading.Thread(
            target=self._flush_safely,
            name="poly-langfuse-flush",
            daemon=True,
        )
        flush_thread.start()
        flush_thread.join(timeout=self._flush_timeout_seconds)
        if flush_thread.is_alive():
            log.warning(
                "Langfuse flush exceeded %.1fs; simulation shutdown continues",
                self._flush_timeout_seconds,
            )

    def _flush_safely(self) -> None:
        try:
            self._client.flush()
        except Exception:  # noqa: BLE001 - exporter outages are fail-open
            log.warning("Langfuse flush failed", exc_info=True)

    def record_fatal_error(self, exc: BaseException) -> None:
        self.on_runner_event(
            "error",
            {"where": "runner", "error_type": type(exc).__name__, "message": str(exc)},
        )

    def close(self) -> None:
        if self._closed:
            return
        if not self._disabled:
            try:
                if self._run_cm is not None:
                    self._finish_run(kind="closed", payload={})
            except Exception:  # noqa: BLE001
                log.warning("Langfuse observation close failed", exc_info=True)
            self._flush_with_timeout()
        self._closed = True


def create_observability(
    settings: Any,
    *,
    session_id: str,
    metadata: Mapping[str, Any],
    client_factory: Callable[..., _LangfuseClient] | None = None,
    propagate_attributes_fn: Callable[..., AbstractContextManager] | None = None,
) -> LangfuseObservability | NoOpObservability:
    """Build the optional adapter, returning no-op for every soft failure."""
    if not bool(getattr(settings, "LANGFUSE_ENABLED", False)):
        return NoOpObservability()

    # Langfuse 4.14 resolves `sample_rate = sample_rate or env_default`, which
    # turns an explicit 0.0 back into 1.0. Honor the operator's zero-sampling
    # intent before importing or constructing the SDK.
    sample_rate = float(getattr(settings, "LANGFUSE_SAMPLE_RATE", 1.0))
    if sample_rate <= 0.0:
        return NoOpObservability()

    public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", None)
    secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", None)
    if not public_key or not secret_key:
        log.warning("Langfuse enabled without both credentials; tracing disabled")
        return NoOpObservability()

    try:
        if client_factory is None or propagate_attributes_fn is None:
            from langfuse import Langfuse, propagate_attributes

            client_factory = client_factory or Langfuse
            propagate_attributes_fn = propagate_attributes_fn or propagate_attributes
        client = client_factory(
            public_key=public_key,
            secret_key=secret_key,
            base_url=getattr(settings, "LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            environment=getattr(settings, "LANGFUSE_ENVIRONMENT", "development"),
            release=getattr(settings, "LANGFUSE_RELEASE", None),
            sample_rate=sample_rate,
        )
        return LangfuseObservability(
            client=client,
            propagate_attributes=propagate_attributes_fn,
            session_id=session_id,
            metadata=metadata,
            capture_policy=getattr(settings, "LANGFUSE_CAPTURE_POLICY", "metadata"),
            release=getattr(settings, "LANGFUSE_RELEASE", None),
            environment=getattr(settings, "LANGFUSE_ENVIRONMENT", "development"),
            flush_timeout_seconds=float(
                getattr(settings, "LANGFUSE_FLUSH_TIMEOUT_SECONDS", 5.0)
            ),
        )
    except Exception:  # noqa: BLE001 - missing SDK/init errors are non-fatal
        log.warning("Langfuse initialization failed; tracing disabled", exc_info=True)
        return NoOpObservability()
