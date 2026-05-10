"""Internal helper: lazily build a single ClickHouse client per
process for the query layer. Callers never see the driver."""
from __future__ import annotations

from typing import Optional

from data.store.clickhouse import ClickHouse
from data.store.config import get_settings

_CH: Optional[ClickHouse] = None


def get_ch(ch: Optional[ClickHouse] = None) -> ClickHouse:
    """If `ch` is provided (e.g., test stub), use it. Else build a
    process-singleton from Settings."""
    global _CH
    if ch is not None:
        return ch
    if _CH is None:
        s = get_settings()
        _CH = ClickHouse(
            host=s.CLICKHOUSE_HOST, port=s.CLICKHOUSE_PORT,
            user=s.CLICKHOUSE_USER, password=s.CLICKHOUSE_PASSWORD,
            database=s.CLICKHOUSE_DATABASE,
        )
    return _CH


def reset_ch_for_tests() -> None:
    """Test-only: drop the cached client so the next call rebuilds."""
    global _CH
    _CH = None
