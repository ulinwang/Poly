"""Onchain table reads — v8 SCAFFOLD.

Activated once `data.sources.onchain.puller` is implemented and the
`onchain_*` tables are populated. For now every function raises
`NotImplementedError` to make the unfinished state loud at call
time (rather than silently returning empty rows)."""
from __future__ import annotations

from typing import Optional


def get_onchain_fills(
    condition_id: str, since_ts: Optional[int] = None,
    until_ts: Optional[int] = None, ch=None,
) -> list[tuple]:
    raise NotImplementedError(
        "data.query.onchain.get_onchain_fills is a v8 scaffold; "
        "ingest data.sources.onchain first"
    )


def get_onchain_redeems(
    condition_id: str, ch=None,
) -> list[tuple]:
    raise NotImplementedError(
        "data.query.onchain.get_onchain_redeems is a v8 scaffold; "
        "ingest data.sources.onchain first"
    )


def get_onchain_splits(
    condition_id: str, ch=None,
) -> list[tuple]:
    raise NotImplementedError(
        "data.query.onchain.get_onchain_splits is a v8 scaffold; "
        "ingest data.sources.onchain first"
    )
