"""HTTP-mocked tests for data_api fetch_trades / fetch_holders / fetch_oi."""
from __future__ import annotations

import unittest
from unittest import mock

from data.sources.data_api import puller as dapi
from tests._http_mock import (
    fake_urlopen_sequence, fake_urlopen_returning, http_error,
)


class FetchTradesTests(unittest.TestCase):
    def test_paginates_offsets_and_stops_on_short_page(self):
        # PAGE_SIZE imported from puller; build pages of full + short to exit
        full = [{"transactionHash": f"h{i}"} for i in range(dapi.PAGE_SIZE)]
        short = [{"transactionHash": "last"}]
        seq = fake_urlopen_sequence([full, short])
        with mock.patch.object(dapi.urllib.request, "urlopen", seq):
            out = dapi.fetch_trades("0xCID")
        self.assertEqual(len(out), dapi.PAGE_SIZE + 1)

    def test_breaks_on_empty_page(self):
        seq = fake_urlopen_sequence([[]])
        with mock.patch.object(dapi.urllib.request, "urlopen", seq):
            self.assertEqual(dapi.fetch_trades("0xCID"), [])

    def test_breaks_on_400_or_422_without_raising(self):
        seq = fake_urlopen_sequence([http_error(400)])
        with mock.patch.object(dapi.urllib.request, "urlopen", seq), \
             mock.patch.object(dapi.time, "sleep", lambda *_: None):
            # The current http_get only retries on 429/5xx; 400 raises HTTPError.
            # fetch_trades catches 400/422 and breaks out → returns [].
            self.assertEqual(dapi.fetch_trades("0xCID"), [])

    def test_non_list_response_breaks(self):
        seq = fake_urlopen_sequence([{"unexpected": "shape"}])
        with mock.patch.object(dapi.urllib.request, "urlopen", seq):
            self.assertEqual(dapi.fetch_trades("0xCID"), [])


class FetchHoldersTests(unittest.TestCase):
    def test_flattens_outcome_blocks(self):
        # API shape: [{"token": "T1", "holders": [...]}, ...]
        payload = [
            {"token": "T1", "holders": [{"proxyWallet": "W1"},
                                         {"proxyWallet": "W2"}]},
            {"token": "T2", "holders": [{"proxyWallet": "W3"}]},
        ]
        with mock.patch.object(dapi.urllib.request, "urlopen",
                                fake_urlopen_returning(payload)):
            out = dapi.fetch_holders("0xCID")
        self.assertEqual(len(out), 3)
        # _token tag added so holder_to_row can use as fallback
        self.assertEqual({h["_token"] for h in out}, {"T1", "T2"})

    def test_non_list_returns_empty(self):
        with mock.patch.object(dapi.urllib.request, "urlopen",
                                fake_urlopen_returning({"err": "no"})):
            self.assertEqual(dapi.fetch_holders("0xCID"), [])

    def test_handles_malformed_outcome_blocks(self):
        payload = [
            "string instead of dict",
            {"token": "T1", "holders": [{"proxyWallet": "W"}]},
        ]
        with mock.patch.object(dapi.urllib.request, "urlopen",
                                fake_urlopen_returning(payload)):
            out = dapi.fetch_holders("0xCID")
        self.assertEqual(len(out), 1)


class FetchOiTests(unittest.TestCase):
    def test_returns_list(self):
        with mock.patch.object(dapi.urllib.request, "urlopen",
                                fake_urlopen_returning([{"market": "M", "value": 10}])):
            self.assertEqual(dapi.fetch_oi("M"),
                              [{"market": "M", "value": 10}])

    def test_returns_empty_when_not_list(self):
        with mock.patch.object(dapi.urllib.request, "urlopen",
                                fake_urlopen_returning({"k": 1})):
            self.assertEqual(dapi.fetch_oi("M"), [])


if __name__ == "__main__":
    unittest.main()
