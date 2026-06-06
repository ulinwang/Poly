"""Live web search backing the `get_information` agent tool.

Reproducibility note
---------------------
Unlike the rest of the simulation, web search is **not** bit-for-bit
reproducible: results change as the live web changes over time. This is an
accepted trade-off for giving agents genuinely up-to-date information in a
prediction-market setting. We preserve *auditability* instead of strict
reproducibility by logging the actual query and the actual results that
came back (see the ``agent_info_query`` event emitted by the runner): a
later reader can see exactly what each agent saw, even if re-running the
search would return something different.

Pluggable backends
-------------------
``WebSearchBackend`` is a small protocol. The default,
``DuckDuckGoBackend``, is **keyless** (no API key required) and uses the
``ddgs`` package (the maintained successor of ``duckduckgo_search``).

Extension point: ``backend_from_env`` selects a backend based on
environment variables, so an operator can drop in a keyed provider (e.g.
Tavily via ``TAVILY_API_KEY``, Serper via ``SERPER_API_KEY``) without code
changes elsewhere. Those keyed backends are stubbed as wiring points; the
default offline-friendly path is DuckDuckGo.

Graceful degradation
--------------------
Any failure (missing dependency, no network, rate limit, timeout) is caught
and turned into a single "information temporarily unavailable" result rather
than an exception. A failed search must never crash an agent's tick or the
whole run.
"""
from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class SearchResult:
    """One web-search hit returned to the agent."""

    title: str
    snippet: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


@runtime_checkable
class WebSearchBackend(Protocol):
    """A pluggable web-search provider.

    ``name`` is recorded in the run log. ``search`` must never raise: on any
    failure it should return a single degraded result (see
    :func:`degraded_result`)."""

    name: str

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        ...


def degraded_result(reason: str) -> list[SearchResult]:
    """A single placeholder result used when search is unavailable.

    Returned (rather than raising) so a search failure degrades gracefully
    instead of taking down the agent's decision or the run."""
    return [SearchResult(
        title="Information temporarily unavailable",
        snippet=f"Web search could not be completed ({reason}). "
                f"Proceed using the information you already have.",
        url="",
    )]


class DuckDuckGoBackend:
    """Keyless DuckDuckGo backend via the ``ddgs`` package.

    ``ddgs`` is imported lazily so the module loads even when the package
    (or the network) is absent — in that case ``search`` returns a degraded
    result instead of raising.
    """

    name = "duckduckgo"

    def __init__(self, *, timeout: int = 10) -> None:
        self._timeout = timeout

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        query = (query or "").strip()
        if not query:
            return degraded_result("empty query")
        try:
            # Maintained successor of duckduckgo_search; keyless.
            from ddgs import DDGS
        except ImportError:
            return degraded_result("ddgs package not installed")
        try:
            results: list[SearchResult] = []
            with DDGS(timeout=self._timeout) as ddgs:
                for row in ddgs.text(query, max_results=max_results):
                    results.append(SearchResult(
                        title=str(row.get("title", "")).strip(),
                        snippet=str(
                            row.get("body") or row.get("snippet") or ""
                        ).strip(),
                        url=str(row.get("href") or row.get("url") or "").strip(),
                    ))
            if not results:
                return degraded_result("no results")
            return results[:max_results]
        except Exception as exc:        # noqa: BLE001 — never crash the tick
            return degraded_result(f"{type(exc).__name__}: {exc}")


# --- Keyed-provider wiring points (extension; not the default path). ------
#
# These are intentionally thin: they only activate when the corresponding
# env var is set. Filling in the HTTP call is left as a follow-up; until
# then they degrade gracefully like any other backend.

class _EnvKeyedBackend:
    """Base for keyed providers selected via env vars. Degrades unless a
    concrete subclass implements `search`."""

    name = "keyed"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        return degraded_result(f"{self.name} backend not implemented")


def backend_from_env() -> WebSearchBackend:
    """Choose a backend from the environment (extension point).

    Precedence: an explicit keyed provider if its API key is present,
    otherwise the keyless DuckDuckGo default. Operators can add a keyed
    provider by setting e.g. ``TAVILY_API_KEY`` / ``SERPER_API_KEY`` and
    implementing the corresponding backend above.
    """
    # Reserved env names for future keyed backends. Presence of a key only
    # routes to the (currently stubbed) keyed backend, which still degrades
    # gracefully — so this never breaks the default offline-friendly path.
    for env_name, label in (("TAVILY_API_KEY", "tavily"),
                            ("SERPER_API_KEY", "serper")):
        key = os.environ.get(env_name)
        if key:
            backend = _EnvKeyedBackend(key)
            backend.name = label
            return backend
    return DuckDuckGoBackend()


def search_web(
    query: str,
    *,
    backend: WebSearchBackend | None = None,
    max_results: int = 5,
) -> list[SearchResult]:
    """Run a web search via ``backend`` (default chosen from env).

    Never raises: returns a degraded single-item result on any failure.
    """
    bk = backend or backend_from_env()
    try:
        return bk.search(query, max_results=max_results)
    except Exception as exc:        # noqa: BLE001 — defensive belt-and-braces
        return degraded_result(f"{type(exc).__name__}: {exc}")
