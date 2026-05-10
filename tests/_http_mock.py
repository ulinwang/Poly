"""Test helper: monkeypatch-friendly fakes for `urllib.request.urlopen`.

Pattern lifted from the puller modules' use of stdlib `urllib`. All ETL
pullers (data/sources/*) call urlopen as a context manager: `with urlopen(req)
as r: r.read()`. These helpers return a callable suitable for
`monkeypatch.setattr(target, fake)` or `unittest.mock.patch.object(...)`.
"""
from __future__ import annotations

import io
import json
import urllib.error
from typing import Any, Iterator, Sequence


class _FakeResponse:
    """Context-manager wrapper around a BytesIO body."""

    def __init__(self, body: bytes, status: int = 200):
        self._buf = io.BytesIO(body)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._buf.close()
        return False

    def read(self) -> bytes:
        return self._buf.read()


def fake_urlopen_returning(payload: Any, *, encode_json: bool = True):
    """Return a urlopen replacement that always yields `payload`.

    If `payload` is a bytes object it's used verbatim; otherwise it's
    json-dumped (default) or stringified.
    """
    if isinstance(payload, (bytes, bytearray)):
        body = bytes(payload)
    elif encode_json:
        body = json.dumps(payload).encode("utf-8")
    else:
        body = str(payload).encode("utf-8")

    def _fake(req, *args, **kwargs):
        return _FakeResponse(body)

    return _fake


def fake_urlopen_sequence(payloads: Sequence[Any]):
    """Return a urlopen replacement that yields each payload in order.

    Subsequent calls past the end raise `AssertionError` so accidental
    re-fetches are caught loudly.
    """
    iterator: Iterator[Any] = iter(payloads)

    def _fake(req, *args, **kwargs):
        try:
            payload = next(iterator)
        except StopIteration as e:
            raise AssertionError("urlopen called more times than payloads provided") from e
        if isinstance(payload, Exception):
            raise payload
        if isinstance(payload, (bytes, bytearray)):
            body = bytes(payload)
        else:
            body = json.dumps(payload).encode("utf-8")
        return _FakeResponse(body)

    return _fake


def http_error(code: int, msg: str = "err", url: str = "http://x") -> urllib.error.HTTPError:
    """Build a `urllib.error.HTTPError` with the given status code."""
    return urllib.error.HTTPError(url, code, msg, hdrs=None, fp=None)
