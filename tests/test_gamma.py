from __future__ import annotations

import datetime as dt
import unittest

from src import gamma


SAMPLE_MARKET = {
    "id": "12345",
    "slug": "will-trump-win-2024",
    "question": "Will Donald Trump win the 2024 US presidential election?",
    "description": "Resolves YES if Trump wins.",
    "category": "Politics",
    "outcomes": '["Yes", "No"]',
    "clobTokenIds": '["111111", "222222"]',
    "outcomePrices": '["0.55", "0.45"]',
    "volume": "1234567.89",
    "endDate": "2024-11-05T23:59:59Z",
    "active": True,
    "closed": False,
}


class ParseHelpersTest(unittest.TestCase):
    def test_parse_json_array_string(self):
        self.assertEqual(gamma._parse_json_array('["a","b"]'), ["a", "b"])

    def test_parse_json_array_already_list(self):
        self.assertEqual(gamma._parse_json_array(["a", "b"]), ["a", "b"])

    def test_parse_json_array_none(self):
        self.assertEqual(gamma._parse_json_array(None), [])

    def test_parse_json_array_invalid(self):
        self.assertEqual(gamma._parse_json_array("not json"), [])

    def test_parse_datetime_iso_z(self):
        out = gamma._parse_datetime("2024-11-05T23:59:59Z")
        self.assertEqual(out, dt.datetime(2024, 11, 5, 23, 59, 59))

    def test_parse_datetime_invalid(self):
        self.assertIsNone(gamma._parse_datetime("not a date"))

    def test_parse_datetime_none(self):
        self.assertIsNone(gamma._parse_datetime(None))

    def test_to_float_ok(self):
        self.assertEqual(gamma._to_float("3.14"), 3.14)

    def test_to_float_bad(self):
        self.assertEqual(gamma._to_float("oops"), 0.0)


class MarketToRowTest(unittest.TestCase):
    def test_full_market(self):
        fixed = dt.datetime(2026, 1, 1, 0, 0, 0)
        row = gamma.market_to_row(SAMPLE_MARKET, fetched_at=fixed)
        self.assertEqual(row[0], "12345")
        self.assertEqual(row[1], "will-trump-win-2024")
        self.assertIn("Trump", row[2])
        self.assertEqual(row[4], "Politics")
        self.assertEqual(row[5], ["Yes", "No"])
        self.assertEqual(row[6], ["111111", "222222"])
        self.assertEqual(row[7], [0.55, 0.45])
        self.assertAlmostEqual(row[8], 1234567.89)
        self.assertEqual(row[9], dt.datetime(2024, 11, 5, 23, 59, 59))
        self.assertEqual(row[10], 1)  # active
        self.assertEqual(row[11], 0)  # closed
        self.assertEqual(row[12], fixed)

    def test_missing_fields(self):
        row = gamma.market_to_row({"id": "x"})
        self.assertEqual(row[0], "x")
        self.assertEqual(row[5], [])
        self.assertEqual(row[6], [])
        self.assertEqual(row[7], [])
        self.assertEqual(row[8], 0.0)
        self.assertIsNone(row[9])
        self.assertEqual(row[10], 0)


class IterAllMarketsTest(unittest.TestCase):
    def test_pagination_stops_on_short_page(self):
        pages = [
            [{"id": "1"}, {"id": "2"}],
            [{"id": "3"}],
        ]
        calls: list[dict] = []

        def fake_fetch(limit, offset, closed):
            calls.append({"limit": limit, "offset": offset, "closed": closed})
            idx = offset // limit
            return pages[idx] if idx < len(pages) else []

        results = list(
            gamma.iter_all_markets(page_size=2, sleep=0, fetch_fn=fake_fetch)
        )
        self.assertEqual([m["id"] for m in results], ["1", "2", "3"])
        self.assertEqual(len(calls), 2)

    def test_pagination_stops_on_422(self):
        import urllib.error

        calls = []

        def fake_fetch(limit, offset, closed):
            calls.append(offset)
            if offset == 0:
                return [{"id": "1"}, {"id": "2"}]
            raise urllib.error.HTTPError(
                "http://x", 422, "Unprocessable Entity", {}, None
            )

        results = list(
            gamma.iter_all_markets(page_size=2, sleep=0, fetch_fn=fake_fetch)
        )
        self.assertEqual([m["id"] for m in results], ["1", "2"])

    def test_pagination_propagates_500(self):
        import urllib.error

        def fake_fetch(limit, offset, closed):
            raise urllib.error.HTTPError("http://x", 500, "Server Error", {}, None)

        with self.assertRaises(urllib.error.HTTPError):
            list(gamma.iter_all_markets(page_size=2, sleep=0, fetch_fn=fake_fetch))

    def test_pagination_stops_on_empty(self):
        pages = [[{"id": "1"}, {"id": "2"}], []]

        def fake_fetch(limit, offset, closed):
            idx = offset // limit
            return pages[idx] if idx < len(pages) else []

        results = list(
            gamma.iter_all_markets(page_size=2, sleep=0, fetch_fn=fake_fetch)
        )
        self.assertEqual(len(results), 2)


class FakeClickHouse:
    def __init__(self):
        self.schema_called = False
        self.inserted: list[tuple] = []

    def ensure_markets_schema(self):
        self.schema_called = True

    def insert_markets(self, rows):
        self.inserted.extend(rows)


class RunIntegrationTest(unittest.TestCase):
    def test_run_with_fakes(self):
        original = gamma.iter_all_markets

        def fake_iter(*args, **kwargs):
            yield SAMPLE_MARKET
            yield {"id": "x2", "slug": "ai", "question": "Q?"}

        gamma.iter_all_markets = fake_iter
        try:
            ch = FakeClickHouse()
            total = gamma.run(ch=ch, batch_size=10)
        finally:
            gamma.iter_all_markets = original
        self.assertTrue(ch.schema_called)
        self.assertEqual(total, 2)
        self.assertEqual(len(ch.inserted), 2)
        self.assertEqual(ch.inserted[0][0], "12345")
        self.assertEqual(ch.inserted[1][0], "x2")


if __name__ == "__main__":
    unittest.main()
