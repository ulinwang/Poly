"""Test helper: substring-routed ClickHouse stub.

Used by data/query test modules + downstream agent feature tests.
Pattern lifted from tests/test_population_priors.py:_StubClient."""
from __future__ import annotations

from typing import Any, Callable, Union

RouteValue = Union[list, Callable[[dict], list]]


class StubClient:
    def __init__(self, route_map: dict[str, RouteValue]):
        self.route_map = route_map
        self.calls: list[tuple[str, dict]] = []

    def execute(self, sql: str, params: Any = None) -> list:
        self.calls.append((sql, dict(params or {})))
        for substr, rows in self.route_map.items():
            if substr in sql:
                if callable(rows):
                    return rows(dict(params or {}))
                return rows
        raise AssertionError(f"unrouted SQL:\n{sql[:240]}")


class StubCH:
    def __init__(self, route_map: dict[str, RouteValue]):
        self.client = StubClient(route_map)
        self.database = "polymetl"
