"""Retry-with-backoff wrapper for the LLM call.

Fulfills the v5-audit queued item: every LLM call retries on transient
failure (HTTPError, URLError, OSError, JSONDecodeError) up to
`max_attempts` with exponential backoff. Permanent failures (auth,
quota) escape on first attempt because their .reason is non-transient.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
from typing import Callable, TypeVar

T = TypeVar("T")
log = logging.getLogger(__name__)


_TRANSIENT_EXC = (
    urllib.error.HTTPError, urllib.error.URLError,
    OSError, ValueError, KeyError, json.JSONDecodeError,
)


def call_with_retry(
    fn: Callable[..., T],
    *args,
    max_attempts: int = 3,
    backoff_base_s: float = 2.0,
    backoff_cap_s: float = 30.0,
    **kwargs,
) -> T:
    """Run `fn(*args, **kwargs)` with exponential backoff on transient
    exceptions. Returns the first successful result; re-raises after
    `max_attempts` failed tries.

    `backoff_delay = min(backoff_cap_s, backoff_base_s ** attempt)`.
    """
    last: BaseException | None = None
    for attempt in range(max_attempts):
        try:
            return fn(*args, **kwargs)
        except _TRANSIENT_EXC as exc:
            last = exc
            if attempt + 1 >= max_attempts:
                break
            delay = min(backoff_cap_s, backoff_base_s ** (attempt + 1))
            log.warning(
                "transient error (attempt %d/%d): %s; sleeping %.1fs",
                attempt + 1, max_attempts, exc, delay,
            )
            time.sleep(delay)
    assert last is not None
    raise last
