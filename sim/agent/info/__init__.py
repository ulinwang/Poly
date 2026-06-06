"""Live web search backing the `get_information` agent tool.

Public API:
    SearchResult        — one web-search hit (title + snippet + url)
    WebSearchBackend    — protocol for pluggable search providers
    DuckDuckGoBackend   — default keyless backend (ddgs)
    backend_from_env()  — choose a backend from env vars (extension point)
    search_web(...)     — run a search; never raises (graceful degradation)

Web search is intentionally NOT bit-for-bit reproducible (results change
over time). We keep auditability by logging the actual query + results.
"""
from agent.info.search import (
    DuckDuckGoBackend,
    SearchResult,
    WebSearchBackend,
    backend_from_env,
    search_web,
)

__all__ = [
    "SearchResult",
    "WebSearchBackend",
    "DuckDuckGoBackend",
    "backend_from_env",
    "search_web",
]
