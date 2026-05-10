"""Unit tests for data.sources.clob_api.puller — pure helper coercions."""
from __future__ import annotations

import datetime as dt
import json
import unittest

from data.sources.clob_api.puller import _S, _F, _I, _B, _DT, _J


class StringHelperTests(unittest.TestCase):
    def test_S_none_returns_empty(self):
        self.assertEqual(_S(None), "")

    def test_S_int_stringified(self):
        self.assertEqual(_S(42), "42")

    def test_S_passthrough_str(self):
        self.assertEqual(_S("hi"), "hi")


class FloatHelperTests(unittest.TestCase):
    def test_F_handles_str_and_int(self):
        self.assertAlmostEqual(_F("3.14"), 3.14)
        self.assertAlmostEqual(_F(2), 2.0)

    def test_F_invalid_returns_zero(self):
        self.assertEqual(_F("bad"), 0.0)
        self.assertEqual(_F(None), 0.0)


class IntHelperTests(unittest.TestCase):
    def test_I_truncates_float_string(self):
        self.assertEqual(_I("3.9"), 3)

    def test_I_handles_int(self):
        self.assertEqual(_I(7), 7)

    def test_I_invalid_returns_zero(self):
        self.assertEqual(_I("nope"), 0)
        self.assertEqual(_I(None), 0)


class BoolHelperTests(unittest.TestCase):
    def test_B_truthy_returns_one(self):
        self.assertEqual(_B(True), 1)
        self.assertEqual(_B(1), 1)
        self.assertEqual(_B("yes"), 1)

    def test_B_falsey_returns_zero(self):
        self.assertEqual(_B(False), 0)
        self.assertEqual(_B(0), 0)
        self.assertEqual(_B(""), 0)
        self.assertEqual(_B(None), 0)


class DatetimeHelperTests(unittest.TestCase):
    def test_DT_iso_z_suffix(self):
        v = _DT("2026-05-09T12:00:00Z")
        self.assertEqual(v, dt.datetime(2026, 5, 9, 12, 0, 0))
        self.assertIsNone(v.tzinfo)

    def test_DT_passthrough_datetime_strips_tz(self):
        aware = dt.datetime(2026, 1, 1, 0, tzinfo=dt.timezone.utc)
        self.assertIsNone(_DT(aware).tzinfo)

    def test_DT_returns_none_for_empty(self):
        self.assertIsNone(_DT(""))
        self.assertIsNone(_DT(None))

    def test_DT_returns_none_for_garbage(self):
        self.assertIsNone(_DT("not-a-date"))

    def test_DT_returns_none_for_non_string_non_dt(self):
        self.assertIsNone(_DT(42))


class JsonHelperTests(unittest.TestCase):
    def test_J_dict_roundtrip(self):
        out = _J({"a": 1, "b": [2, 3]})
        self.assertEqual(json.loads(out), {"a": 1, "b": [2, 3]})

    def test_J_str_passthrough(self):
        self.assertEqual(_J('{"k":1}'), '{"k":1}')

    def test_J_none_empty(self):
        self.assertEqual(_J(None), "")


if __name__ == "__main__":
    unittest.main()
