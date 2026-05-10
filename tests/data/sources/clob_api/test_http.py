"""HTTP-mocked tests for clob_api.puller.http_get / http_post."""
from __future__ import annotations

import unittest
from unittest import mock

from data.sources.clob_api import puller as clob
from tests._http_mock import (
    fake_urlopen_returning, fake_urlopen_sequence, http_error,
)


class HttpGetTests(unittest.TestCase):
    def test_returns_decoded_json(self):
        with mock.patch.object(clob.urllib.request, "urlopen",
                                fake_urlopen_returning({"hello": "world"})):
            self.assertEqual(clob.http_get("/x"), {"hello": "world"})

    def test_retries_on_429_then_succeeds(self):
        seq = fake_urlopen_sequence([
            http_error(429),
            {"ok": True},
        ])
        with mock.patch.object(clob.urllib.request, "urlopen", seq), \
             mock.patch.object(clob.time, "sleep", lambda *_: None):
            self.assertEqual(clob.http_get("/x"), {"ok": True})

    def test_retries_on_503_then_succeeds(self):
        seq = fake_urlopen_sequence([
            http_error(503),
            {"ok": 1},
        ])
        with mock.patch.object(clob.urllib.request, "urlopen", seq), \
             mock.patch.object(clob.time, "sleep", lambda *_: None):
            self.assertEqual(clob.http_get("/x"), {"ok": 1})

    def test_404_raises_immediately_no_retry(self):
        seq = fake_urlopen_sequence([http_error(404)])
        with mock.patch.object(clob.urllib.request, "urlopen", seq), \
             mock.patch.object(clob.time, "sleep", lambda *_: None):
            with self.assertRaises(clob.urllib.error.HTTPError) as ctx:
                clob.http_get("/x")
            self.assertEqual(ctx.exception.code, 404)

    def test_exhausts_retries_raises_runtime_error(self):
        seq = fake_urlopen_sequence([http_error(500)] * 5)
        with mock.patch.object(clob.urllib.request, "urlopen", seq), \
             mock.patch.object(clob.time, "sleep", lambda *_: None):
            with self.assertRaises(RuntimeError):
                clob.http_get("/x", max_retries=5)


class HttpPostTests(unittest.TestCase):
    def test_serializes_body_and_returns_decoded_json(self):
        captured = {}

        def fake_urlopen(req, *args, **kwargs):
            captured["data"] = req.data
            captured["url"] = req.full_url
            return fake_urlopen_returning({"echo": True})(req)

        with mock.patch.object(clob.urllib.request, "urlopen", fake_urlopen):
            out = clob.http_post("/midpoints", [{"token_id": "T1"}])
        self.assertEqual(out, {"echo": True})
        # body should be JSON-encoded list
        import json as _json
        self.assertEqual(_json.loads(captured["data"]),
                         [{"token_id": "T1"}])
        self.assertTrue(captured["url"].endswith("/midpoints"))


if __name__ == "__main__":
    unittest.main()
