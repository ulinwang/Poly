"""Tests for gamma_api.puller fetch_markets_page / iter_all_markets / run."""
from __future__ import annotations

import unittest
from unittest import mock

from data.sources.gamma_api import puller as gamma
from tests.data._stub_ch import StubCH
from tests._http_mock import (
    fake_urlopen_returning, fake_urlopen_sequence, http_error,
)


class FetchMarketsPageTests(unittest.TestCase):
    def test_unwraps_data_envelope(self):
        with mock.patch.object(gamma.urllib.request, "urlopen",
                                fake_urlopen_returning({"data": [{"id": "M1"}]})):
            out = gamma.fetch_markets_page(limit=10)
        self.assertEqual(out, [{"id": "M1"}])

    def test_passes_through_bare_list(self):
        with mock.patch.object(gamma.urllib.request, "urlopen",
                                fake_urlopen_returning([{"id": "M1"}])):
            out = gamma.fetch_markets_page(limit=10, closed=True)
        self.assertEqual(out, [{"id": "M1"}])

    def test_empty_payload_returns_empty(self):
        with mock.patch.object(gamma.urllib.request, "urlopen",
                                fake_urlopen_returning(None)):
            self.assertEqual(gamma.fetch_markets_page(), [])


class IterAllMarketsTests(unittest.TestCase):
    def test_short_page_terminates(self):
        pages = iter([
            [{"id": f"M{i}"} for i in range(5)],   # full
            [{"id": "Mlast"}],                      # short → stop
        ])

        def fake_fetch(*args, **kwargs):
            return next(pages)

        out = list(gamma.iter_all_markets(page_size=5, sleep=0,
                                            fetch_fn=fake_fetch))
        self.assertEqual(len(out), 6)

    def test_swallows_400_and_422(self):
        def fake_fetch(*args, **kwargs):
            raise http_error(400)
        out = list(gamma.iter_all_markets(page_size=10, sleep=0,
                                            fetch_fn=fake_fetch))
        self.assertEqual(out, [])

    def test_propagates_other_http_errors(self):
        def fake_fetch(*args, **kwargs):
            raise http_error(500)
        with self.assertRaises(gamma.urllib.error.HTTPError):
            list(gamma.iter_all_markets(page_size=10, sleep=0,
                                         fetch_fn=fake_fetch))

    def test_stops_on_empty_page(self):
        out = list(gamma.iter_all_markets(page_size=10, sleep=0,
                                            fetch_fn=lambda **kw: []))
        self.assertEqual(out, [])


class RunTests(unittest.TestCase):
    def test_inserts_in_batches(self):
        # 5 markets, batch_size=2 → flushes twice (2+2) then drains 1
        markets = [{"id": f"M{i}"} for i in range(5)]
        inserts: list[list] = []
        ch = StubCH({})
        original = ch.client.execute
        def execute(sql, params=None):
            if "INSERT INTO polymetl.markets_full" in sql and isinstance(params, list):
                inserts.append(params)
                return []
            return original(sql, params) if "FROM" in sql else []
        ch.client.execute = execute  # type: ignore

        with mock.patch.object(gamma, "iter_all_markets",
                               return_value=iter(markets)):
            total = gamma.run(closed=None, page_size=10, batch_size=2, ch=ch)
        self.assertEqual(total, 5)
        self.assertEqual(len(inserts), 3)
        self.assertEqual([len(b) for b in inserts], [2, 2, 1])


if __name__ == "__main__":
    unittest.main()
