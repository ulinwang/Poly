from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from data.store.config import Settings
from observability.langfuse import (
    LangfuseObservability,
    NoOpObservability,
    create_observability,
    sanitize_payload,
)


class FakeObservation:
    def __init__(self, name: str, kwargs: dict, parent: str | None):
        self.name = name
        self.kwargs = kwargs
        self.parent = parent
        self.updates: list[dict] = []
        self.scores: list[dict] = []

    def update(self, **kwargs):
        self.updates.append(kwargs)

    def score(self, **kwargs):
        self.scores.append(kwargs)


class FakeObservationContext:
    def __init__(self, client, observation):
        self.client = client
        self.observation = observation

    def __enter__(self):
        self.client.active.append(self.observation)
        self.client.events.append(("enter", self.observation.name))
        return self.observation

    def __exit__(self, exc_type, exc, tb):
        assert self.client.active[-1] is self.observation
        self.client.active.pop()
        self.client.events.append(("exit", self.observation.name))


class FakeClient:
    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.active: list[FakeObservation] = []
        self.observations: list[FakeObservation] = []
        self.events: list[tuple[str, str]] = []
        self.flush_count = 0

    def start_as_current_observation(self, **kwargs):
        observation = FakeObservation(
            kwargs["name"],
            kwargs,
            self.active[-1].name if self.active else None,
        )
        self.observations.append(observation)
        return FakeObservationContext(self, observation)

    def flush(self):
        self.flush_count += 1


@dataclass
class FakeLoopContext:
    run_id: str = "sim-1"
    tick: int = 3
    agent_id: int = 7
    decision_id: str = "decision-7"


@dataclass
class FakeStepContext:
    loop: FakeLoopContext
    stage: object
    iteration: int


@dataclass
class FakeAgentLoopEvent:
    kind: str
    context: FakeStepContext
    sequence: int
    payload: dict


def _event(kind, *, stage="trade", sequence=0, payload=None):
    return FakeAgentLoopEvent(
        kind=kind,
        context=FakeStepContext(
            loop=FakeLoopContext(),
            stage=SimpleNamespace(value=stage),
            iteration=sequence,
        ),
        sequence=sequence,
        payload=payload or {},
    )


def _telemetry(*, capture_policy="metadata"):
    client = FakeClient()
    telemetry = LangfuseObservability(
        client=client,
        propagate_attributes=lambda **kwargs: nullcontext(kwargs),
        session_id="session-1",
        metadata={"seed": 42},
        capture_policy=capture_policy,
        flush_timeout_seconds=1,
    )
    return client, telemetry


def test_nested_runner_agent_generation_and_tool_hierarchy():
    client, telemetry = _telemetry(capture_policy="full")
    telemetry.on_runner_event("run_started", {"slug": "market"})
    telemetry.on_runner_event("tick_started", {"tick": 3})
    telemetry.on_event(_event(
        "loop_started",
        payload={"model": "deepseek", "token_budget": 1000},
    ))
    telemetry.on_event(_event(
        "generation_started",
        payload={"model": "deepseek", "user_prompt": "visible"},
    ))
    telemetry.on_event(_event(
        "generation_completed",
        payload={"status": "ok", "prompt_tokens": 11, "completion_tokens": 4},
    ))
    telemetry.on_event(_event(
        "tool_started",
        payload={"tool_name": "read_forum", "arguments": {"limit": 5}},
    ))
    telemetry.on_event(_event(
        "tool_completed",
        payload={"status": "ok", "output": ["post"]},
    ))
    telemetry.on_event(_event(
        "loop_completed",
        stage="finish",
        payload={"status": "ok", "latency_ms": 20},
    ))
    telemetry.on_runner_event("tick_finished", {"tick": 3, "elapsed_s": 0.2})
    telemetry.on_runner_event("done", {"sim_id": "sim-1"})

    by_name = {observation.name: observation for observation in client.observations}
    assert by_name["poly.tick.3"].parent == "poly.experiment"
    assert by_name["poly.agent-loop"].parent == "poly.tick.3"
    assert by_name["poly.generation.trade"].parent == "poly.agent-loop"
    assert by_name["poly.tool.read_forum"].parent == "poly.agent-loop"
    generation_update = by_name["poly.generation.trade"].updates[-1]
    assert generation_update["usage_details"] == {
        "input_tokens": 11,
        "output_tokens": 4,
        "total_tokens": 15,
    }
    assert client.flush_count == 1
    assert client.active == []


def test_metadata_policy_omits_content_and_always_redacts_secrets():
    payload = {
        "model": "deepseek",
        "user_prompt": "private prompt",
        "messages": [{"content": "private"}],
        "api_key": "sk-secret",
        "reasoning_content": "hidden chain of thought",
        "variables": {"private_market_context": "private"},
        "_langfuse_prompt": object(),
        "prompt_tokens": 12,
    }
    sanitized = sanitize_payload(payload, capture_policy="metadata")
    assert "user_prompt" not in sanitized
    assert "messages" not in sanitized
    assert "variables" not in sanitized
    assert "_langfuse_prompt" not in sanitized
    assert sanitized["api_key"] == "[REDACTED]"
    assert sanitized["reasoning_content"] == "[REDACTED]"
    assert sanitized["prompt_tokens"] == 12


def test_managed_prompt_is_linked_to_generation_but_never_serialized():
    client, telemetry = _telemetry(capture_policy="full")
    managed_prompt = object()
    telemetry.on_event(_event("loop_started", payload={"model": "deepseek"}))
    telemetry.on_event(_event(
        "generation_started",
        payload={
            "model": "deepseek",
            "prompt_identity": [{"name": "poly/trade-stage/en", "version": 4}],
            "_langfuse_prompt": managed_prompt,
        },
    ))

    generation = next(
        observation for observation in client.observations
        if observation.name == "poly.generation.trade"
    )
    assert generation.kwargs["prompt"] is managed_prompt
    assert "_langfuse_prompt" not in generation.kwargs["input"]
    assert "_langfuse_prompt" not in generation.kwargs["metadata"]
    telemetry.close()


def test_local_agent_and_run_scores_are_mirrored_to_langfuse():
    client, telemetry = _telemetry()
    telemetry.on_event(_event("loop_started", payload={"model": "deepseek"}))
    telemetry.on_event(_event("loop_completed", stage="finish", payload={"status": "ok"}))
    telemetry.on_runner_event("agent_scores", {
        "decision_id": "decision-7",
        "scores": [{
            "name": "decision.schema_valid", "value": 1.0,
            "passed": True, "hard": True, "evaluator_version": "1",
        }],
    })
    telemetry.on_runner_event("run_scores", {
        "scores": [{
            "name": "multi_agent.sequence_valid", "value": 1.0,
            "passed": True, "hard": True, "evaluator_version": "1",
        }],
    })

    by_name = {observation.name: observation for observation in client.observations}
    assert by_name["poly.agent-loop"].scores[0]["name"] == "decision.schema_valid"
    assert by_name["poly.experiment"].scores[0]["name"] == "multi_agent.sequence_valid"
    telemetry.close()


def test_full_policy_keeps_visible_content_but_not_hidden_reasoning():
    sanitized = sanitize_payload(
        {
            "user_prompt": "visible prompt",
            "output": "visible output",
            "secret_key": "secret",
            "reasoning_content": "hidden",
        },
        capture_policy="full",
    )
    assert sanitized["user_prompt"] == "visible prompt"
    assert sanitized["output"] == "visible output"
    assert sanitized["secret_key"] == "[REDACTED]"
    assert sanitized["reasoning_content"] == "[REDACTED]"


def test_disabled_or_missing_credentials_never_constructs_client():
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeClient(**kwargs)

    disabled = create_observability(
        SimpleNamespace(LANGFUSE_ENABLED=False),
        session_id="session",
        metadata={},
        client_factory=factory,
        propagate_attributes_fn=lambda **kwargs: nullcontext(kwargs),
    )
    missing = create_observability(
        SimpleNamespace(
            LANGFUSE_ENABLED=True,
            LANGFUSE_PUBLIC_KEY=None,
            LANGFUSE_SECRET_KEY=None,
        ),
        session_id="session",
        metadata={},
        client_factory=factory,
        propagate_attributes_fn=lambda **kwargs: nullcontext(kwargs),
    )
    zero_sample = create_observability(
        SimpleNamespace(
            LANGFUSE_ENABLED=True,
            LANGFUSE_SAMPLE_RATE=0.0,
            LANGFUSE_PUBLIC_KEY="pk-test",
            LANGFUSE_SECRET_KEY="sk-test",
        ),
        session_id="session",
        metadata={},
        client_factory=factory,
        propagate_attributes_fn=lambda **kwargs: nullcontext(kwargs),
    )
    assert isinstance(disabled, NoOpObservability)
    assert isinstance(missing, NoOpObservability)
    assert isinstance(zero_sample, NoOpObservability)
    assert calls == []


def test_factory_passes_cloud_or_self_hosted_configuration():
    clients = []

    def factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    telemetry = create_observability(
        SimpleNamespace(
            LANGFUSE_ENABLED=True,
            LANGFUSE_PUBLIC_KEY="pk-test",
            LANGFUSE_SECRET_KEY="sk-test",
            LANGFUSE_BASE_URL="https://langfuse.internal",
            LANGFUSE_ENVIRONMENT="ci",
            LANGFUSE_RELEASE="sha-123",
            LANGFUSE_SAMPLE_RATE=0.25,
            LANGFUSE_CAPTURE_POLICY="metadata",
            LANGFUSE_FLUSH_TIMEOUT_SECONDS=1,
        ),
        session_id="session",
        metadata={},
        client_factory=factory,
        propagate_attributes_fn=lambda **kwargs: nullcontext(kwargs),
    )
    assert isinstance(telemetry, LangfuseObservability)
    assert clients[0].init_kwargs == {
        "public_key": "pk-test",
        "secret_key": "sk-test",
        "base_url": "https://langfuse.internal",
        "environment": "ci",
        "release": "sha-123",
        "sample_rate": 0.25,
    }
    telemetry.close()


@pytest.mark.parametrize("terminal_kind", ["done", "paused", "cancelled", "error"])
def test_every_terminal_state_closes_and_flushes(terminal_kind):
    client, telemetry = _telemetry()
    telemetry.on_runner_event("tick_started", {"tick": 1})
    payload = {"message": "boom"} if terminal_kind == "error" else {"tick": 1}
    telemetry.on_runner_event(terminal_kind, payload)
    telemetry.close()
    assert client.active == []
    assert client.flush_count == 1


@pytest.mark.parametrize("sample_rate", [-0.1, 1.1])
def test_settings_reject_invalid_langfuse_sample_rate(sample_rate):
    with pytest.raises(ValidationError):
        Settings(RPC_URL="http://localhost", LANGFUSE_SAMPLE_RATE=sample_rate)


@pytest.mark.parametrize("environment", ["Production", "langfuse-prod", "bad env"])
def test_settings_reject_invalid_langfuse_environment(environment):
    with pytest.raises(ValidationError):
        Settings(RPC_URL="http://localhost", LANGFUSE_ENVIRONMENT=environment)
