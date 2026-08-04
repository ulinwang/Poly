from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from data.store.config import Settings
from agent.prompt.registry import PromptResolver, create_prompt_resolver


class FakeManagedPrompt:
    def __init__(self, *, version=7, is_fallback=False):
        self.version = version
        self.is_fallback = is_fallback

    def compile(self, **variables):
        return f"remote:{variables['value']}"


class FakeClient:
    def __init__(self, prompt=None, error=None, **kwargs):
        self.prompt = prompt or FakeManagedPrompt()
        self.error = error
        self.init_kwargs = kwargs
        self.calls = []

    def get_prompt(self, name, **kwargs):
        self.calls.append((name, kwargs))
        if self.error:
            raise self.error
        return self.prompt


def test_local_identity_is_reproducible_and_deeply_immutable():
    variables = {"value": "local", "nested": {"items": [1, 2]}}
    result = PromptResolver().resolve(
        "belief_stage",
        language="en",
        variables=variables,
        local_content="local prompt",
    )
    assert result.identity.source == "local"
    assert result.identity.version == "v1"
    assert len(result.identity.content_hash) == 64
    variables["nested"]["items"].append(3)
    assert result.identity.to_dict()["variables"]["nested"]["items"] == [1, 2]
    with pytest.raises(TypeError):
        result.identity.variables["new"] = "value"


def test_managed_prompt_uses_configured_label_ttl_and_keeps_link():
    client = FakeClient()
    result = PromptResolver(
        client=client, label="staging", cache_ttl_seconds=123,
    ).resolve(
        "trade_stage",
        language="zh",
        variables={"value": "compiled"},
        local_content="fallback",
    )
    assert result.content == "remote:compiled"
    assert result.identity.source == "langfuse"
    assert result.identity.version == "7"
    assert result.provider_prompt is client.prompt
    assert client.calls == [(
        "poly/trade-stage/zh",
        {
            "label": "staging",
            "cache_ttl_seconds": 123,
            "type": "text",
            "fallback": "fallback",
        },
    )]


def test_remote_error_falls_back_and_emits_observable_warning():
    warnings = []
    result = PromptResolver(
        client=FakeClient(error=RuntimeError("offline")),
    ).resolve(
        "user_state",
        language="en",
        variables={"value": "x"},
        local_content="local survives",
        on_warning=warnings.append,
    )
    assert result.content == "local survives"
    assert result.identity.source == "fallback"
    assert result.provider_prompt is None
    assert warnings[0]["fallback"] == "local"
    assert "offline" in warnings[0]["reason"]


def test_factory_is_disabled_by_default_and_client_has_tracing_off():
    disabled = create_prompt_resolver(SimpleNamespace())
    assert disabled.resolve(
        "belief_stage", language="en", variables={}, local_content="local",
    ).identity.source == "local"

    clients = []

    def factory(**kwargs):
        client = FakeClient(**kwargs)
        clients.append(client)
        return client

    resolver = create_prompt_resolver(
        SimpleNamespace(
            LANGFUSE_PROMPT_MANAGEMENT_ENABLED=True,
            LANGFUSE_PUBLIC_KEY="pk-test",
            LANGFUSE_SECRET_KEY="sk-test",
            LANGFUSE_BASE_URL="https://langfuse.internal",
            LANGFUSE_PROMPT_LABEL="production",
            LANGFUSE_PROMPT_CACHE_TTL_SECONDS=60,
        ),
        client_factory=factory,
    )
    assert clients[0].init_kwargs["tracing_enabled"] is False
    assert resolver.label == "production"


@pytest.mark.parametrize("ttl", [-1, 86_401])
def test_settings_reject_invalid_prompt_cache_ttl(ttl):
    with pytest.raises(ValidationError):
        Settings(
            RPC_URL="http://localhost",
            LANGFUSE_PROMPT_CACHE_TTL_SECONDS=ttl,
        )
