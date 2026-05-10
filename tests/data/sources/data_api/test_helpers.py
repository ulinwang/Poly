"""Unit tests for data.sources.data_api.puller — _fmt_* helpers."""
from __future__ import annotations

import unittest

from data.sources.data_api.puller import _fmt_str, _fmt_int, _fmt_float, _fmt_bool


class FmtStrTests(unittest.TestCase):
    def test_none_empty(self):
        self.assertEqual(_fmt_str(None), "")

    def test_passthrough(self):
        self.assertEqual(_fmt_str("hi"), "hi")

    def test_int_coerced(self):
        self.assertEqual(_fmt_str(7), "7")


class FmtIntTests(unittest.TestCase):
    def test_floors_floatstr(self):
        self.assertEqual(_fmt_int("3.9"), 3)

    def test_invalid_zero(self):
        self.assertEqual(_fmt_int("nope"), 0)

    def test_none_zero(self):
        self.assertEqual(_fmt_int(None), 0)


class FmtFloatTests(unittest.TestCase):
    def test_handles_strings(self):
        self.assertAlmostEqual(_fmt_float("1.25"), 1.25)

    def test_invalid_zero(self):
        self.assertEqual(_fmt_float("bad"), 0.0)
        self.assertEqual(_fmt_float(None), 0.0)


class FmtBoolTests(unittest.TestCase):
    def test_truthy(self):
        self.assertEqual(_fmt_bool(True), 1)
        self.assertEqual(_fmt_bool("yes"), 1)
        self.assertEqual(_fmt_bool(1), 1)

    def test_falsey(self):
        self.assertEqual(_fmt_bool(False), 0)
        self.assertEqual(_fmt_bool(""), 0)
        self.assertEqual(_fmt_bool(None), 0)


if __name__ == "__main__":
    unittest.main()
