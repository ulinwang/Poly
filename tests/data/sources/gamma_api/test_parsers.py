"""Unit tests for data.sources.gamma_api.puller — pure parser helpers."""
from __future__ import annotations

import datetime as dt
import json
import unittest

from data.sources.gamma_api.puller import (
    _parse_json_array, _parse_datetime, _to_float, _parse_arr_str,
    _parse_arr_float, _parse_json_blob, _parse_int, _parse_bool, _parse_str,
)


class ParseJsonArrayTests(unittest.TestCase):
    def test_passthrough_list(self):
        self.assertEqual(_parse_json_array([1, 2, 3]), [1, 2, 3])

    def test_decodes_json_string(self):
        self.assertEqual(_parse_json_array('["a","b"]'), ["a", "b"])

    def test_invalid_json_returns_empty(self):
        self.assertEqual(_parse_json_array("not json"), [])

    def test_non_array_json_returns_empty(self):
        self.assertEqual(_parse_json_array('{"a":1}'), [])

    def test_none_returns_empty(self):
        self.assertEqual(_parse_json_array(None), [])

    def test_unsupported_type_returns_empty(self):
        self.assertEqual(_parse_json_array(42), [])


class ParseDatetimeTests(unittest.TestCase):
    def test_iso_z_suffix(self):
        v = _parse_datetime("2026-05-09T12:00:00Z")
        self.assertEqual(v, dt.datetime(2026, 5, 9, 12, 0, 0))
        self.assertIsNone(v.tzinfo)

    def test_iso_with_offset_normalized_to_naive(self):
        v = _parse_datetime("2026-01-01T00:00:00+00:00")
        self.assertIsNone(v.tzinfo)

    def test_passthrough_datetime_strips_tz(self):
        aware = dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone.utc)
        self.assertIsNone(_parse_datetime(aware).tzinfo)

    def test_empty_returns_none(self):
        self.assertIsNone(_parse_datetime(""))
        self.assertIsNone(_parse_datetime(None))

    def test_garbage_returns_none(self):
        self.assertIsNone(_parse_datetime("not-a-date"))

    def test_non_string_non_datetime_returns_none(self):
        self.assertIsNone(_parse_datetime(42))


class ToFloatTests(unittest.TestCase):
    def test_handles_string(self):
        self.assertAlmostEqual(_to_float("1.5"), 1.5)

    def test_invalid_returns_default(self):
        self.assertEqual(_to_float("nope", default=-1.0), -1.0)

    def test_none_returns_default(self):
        self.assertEqual(_to_float(None), 0.0)


class ParseArrStrTests(unittest.TestCase):
    def test_coerces_each_to_str(self):
        self.assertEqual(_parse_arr_str([1, 2, 3]), ["1", "2", "3"])

    def test_handles_json_string(self):
        self.assertEqual(_parse_arr_str('["a", "b"]'), ["a", "b"])


class ParseArrFloatTests(unittest.TestCase):
    def test_handles_mixed_types(self):
        self.assertEqual(_parse_arr_float([1, "2.5", "bad"]), [1.0, 2.5, 0.0])

    def test_empty_for_none(self):
        self.assertEqual(_parse_arr_float(None), [])


class ParseJsonBlobTests(unittest.TestCase):
    def test_dict_serialized(self):
        out = _parse_json_blob({"a": 1, "b": [1, 2]})
        self.assertEqual(json.loads(out), {"a": 1, "b": [1, 2]})

    def test_str_passthrough(self):
        self.assertEqual(_parse_json_blob('{"k":1}'), '{"k":1}')

    def test_none_empty(self):
        self.assertEqual(_parse_json_blob(None), "")

    def test_unserializable_falls_back_to_default(self):
        # default=str will stringify any object
        out = _parse_json_blob({"d": dt.datetime(2026, 1, 1)})
        self.assertIn("2026", out)


class ParseIntTests(unittest.TestCase):
    def test_int_passthrough(self):
        self.assertEqual(_parse_int(7), 7)

    def test_floats_truncate(self):
        self.assertEqual(_parse_int(3.9), 3)

    def test_string_floats(self):
        self.assertEqual(_parse_int("4.7"), 4)

    def test_empty_string_zero(self):
        self.assertEqual(_parse_int(""), 0)

    def test_invalid_zero(self):
        self.assertEqual(_parse_int("nope"), 0)

    def test_none_zero(self):
        self.assertEqual(_parse_int(None), 0)


class ParseBoolTests(unittest.TestCase):
    def test_truthy_to_one(self):
        self.assertEqual(_parse_bool(True), 1)
        self.assertEqual(_parse_bool(1), 1)
        self.assertEqual(_parse_bool("yes"), 1)

    def test_falsey_to_zero(self):
        self.assertEqual(_parse_bool(False), 0)
        self.assertEqual(_parse_bool(0), 0)
        self.assertEqual(_parse_bool(""), 0)
        self.assertEqual(_parse_bool(None), 0)


class ParseStrTests(unittest.TestCase):
    def test_none_empty(self):
        self.assertEqual(_parse_str(None), "")

    def test_passthrough_string(self):
        self.assertEqual(_parse_str("hello"), "hello")

    def test_coerces_int_to_str(self):
        self.assertEqual(_parse_str(7), "7")


if __name__ == "__main__":
    unittest.main()
