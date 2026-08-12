"""Versioned prompt registry with optional Langfuse-managed overrides."""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol

from data.store.config import get_settings


log = logging.getLogger(__name__)
PromptWarningCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class PromptSpec:
    key: str
    remote_name: str
    local_version: str = "v1"


@dataclass(frozen=True)
class PromptIdentity:
    source: str
    name: str
    version: str
    label: str | None
    content_hash: str
    language: str
    variables: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "variables", _freeze(dict(self.variables)))

    def to_dict(self, *, include_variables: bool = True) -> dict[str, Any]:
        result = {
            "source": self.source,
            "name": self.name,
            "version": self.version,
            "label": self.label,
            "content_hash": self.content_hash,
            "language": self.language,
            "variable_names": sorted(self.variables),
        }
        if include_variables:
            result["variables"] = _thaw(self.variables)
        return result


@dataclass(frozen=True)
class ResolvedPrompt:
    content: str
    identity: PromptIdentity
    provider_prompt: Any = field(default=None, repr=False, compare=False)


class PromptClient(Protocol):
    def get_prompt(self, name: str, **kwargs: Any) -> Any: ...


PROMPT_SPECS: Mapping[str, PromptSpec] = MappingProxyType({
    "clob_system": PromptSpec("clob_system", "poly/clob-system"),
    "user_state": PromptSpec("user_state", "poly/user-state"),
    "belief_stage": PromptSpec("belief_stage", "poly/belief-stage"),
    "trade_stage": PromptSpec("trade_stage", "poly/trade-stage"),
})


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(item) for item in value]
    return str(value)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _identity(
    *,
    source: str,
    name: str,
    version: str,
    label: str | None,
    language: str,
    content: str,
    variables: Mapping[str, Any],
) -> PromptIdentity:
    return PromptIdentity(
        source=source,
        name=name,
        version=version,
        label=label,
        content_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        language=language,
        variables=_json_safe(variables),
    )


class PromptResolver:
    """Resolve local prompts or optional Langfuse overrides, always fail-open."""

    def __init__(
        self,
        *,
        client: PromptClient | None = None,
        label: str = "production",
        cache_ttl_seconds: int = 300,
        unavailable_reason: str | None = None,
    ) -> None:
        self._client = client
        self.label = label
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self._unavailable_reason = unavailable_reason

    def resolve(
        self,
        key: str,
        *,
        language: str,
        variables: Mapping[str, Any],
        local_content: str,
        on_warning: PromptWarningCallback | None = None,
    ) -> ResolvedPrompt:
        spec = PROMPT_SPECS[key]
        remote_name = f"{spec.remote_name}/{language}"
        if self._client is None:
            source = "fallback" if self._unavailable_reason else "local"
            if self._unavailable_reason:
                self._warn(
                    on_warning,
                    name=remote_name,
                    reason=self._unavailable_reason,
                )
            return ResolvedPrompt(
                content=local_content,
                identity=_identity(
                    source=source,
                    name=remote_name,
                    version=spec.local_version,
                    label=self.label if source == "fallback" else None,
                    language=language,
                    content=local_content,
                    variables=variables,
                ),
            )

        try:
            provider_prompt = self._client.get_prompt(
                remote_name,
                label=self.label,
                cache_ttl_seconds=self.cache_ttl_seconds,
                type="text",
                fallback=local_content,
            )
            content = str(provider_prompt.compile(**dict(variables)))
            is_fallback = bool(getattr(provider_prompt, "is_fallback", False))
            source = "fallback" if is_fallback else "langfuse"
            if is_fallback:
                self._warn(on_warning, name=remote_name, reason="remote fetch failed")
            version = (
                spec.local_version if is_fallback
                else str(getattr(provider_prompt, "version", "unknown"))
            )
            return ResolvedPrompt(
                content=content,
                identity=_identity(
                    source=source,
                    name=remote_name,
                    version=version,
                    label=self.label,
                    language=language,
                    content=content,
                    variables=variables,
                ),
                provider_prompt=None if is_fallback else provider_prompt,
            )
        except Exception as exc:  # noqa: BLE001 - prompt outages must fail open
            log.warning("Langfuse prompt lookup failed for %s", remote_name, exc_info=True)
            self._warn(on_warning, name=remote_name, reason=str(exc))
            return ResolvedPrompt(
                content=local_content,
                identity=_identity(
                    source="fallback",
                    name=remote_name,
                    version=spec.local_version,
                    label=self.label,
                    language=language,
                    content=local_content,
                    variables=variables,
                ),
            )

    @staticmethod
    def _warn(
        callback: PromptWarningCallback | None,
        *,
        name: str,
        reason: str,
    ) -> None:
        if callback is None:
            return
        try:
            callback({"name": name, "reason": reason, "fallback": "local"})
        except Exception:  # noqa: BLE001
            log.debug("prompt warning callback failed", exc_info=True)


def create_prompt_resolver(
    settings: Any,
    *,
    client_factory: Callable[..., PromptClient] | None = None,
) -> PromptResolver:
    enabled = bool(getattr(settings, "LANGFUSE_PROMPT_MANAGEMENT_ENABLED", False))
    label = str(getattr(settings, "LANGFUSE_PROMPT_LABEL", "production"))
    ttl = int(getattr(settings, "LANGFUSE_PROMPT_CACHE_TTL_SECONDS", 300))
    if not enabled:
        return PromptResolver(label=label, cache_ttl_seconds=ttl)
    public_key = getattr(settings, "LANGFUSE_PUBLIC_KEY", None)
    secret_key = getattr(settings, "LANGFUSE_SECRET_KEY", None)
    if not public_key or not secret_key:
        return PromptResolver(
            label=label,
            cache_ttl_seconds=ttl,
            unavailable_reason="prompt management enabled without credentials",
        )
    try:
        if client_factory is None:
            from langfuse import Langfuse

            client_factory = Langfuse
        client = client_factory(
            public_key=public_key,
            secret_key=secret_key,
            base_url=getattr(settings, "LANGFUSE_BASE_URL", "https://cloud.langfuse.com"),
            tracing_enabled=False,
        )
        return PromptResolver(client=client, label=label, cache_ttl_seconds=ttl)
    except Exception as exc:  # noqa: BLE001
        log.warning("Langfuse prompt client initialization failed", exc_info=True)
        return PromptResolver(
            label=label,
            cache_ttl_seconds=ttl,
            unavailable_reason=f"prompt client unavailable: {type(exc).__name__}",
        )


@lru_cache(maxsize=1)
def get_prompt_resolver() -> PromptResolver:
    return create_prompt_resolver(get_settings())


def prompt_metadata_json(prompts: list[ResolvedPrompt]) -> str:
    """Stable serialized prompt identity for checkpoints and audit logs."""
    return json.dumps(
        [prompt.identity.to_dict() for prompt in prompts],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
