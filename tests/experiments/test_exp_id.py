from __future__ import annotations

import datetime as dt
import unittest

from experiments.config import parse_config
from experiments.runner import compute_exp_id, _config_hash


class ExpIdTest(unittest.TestCase):
    def test_format(self):
        cfg = parse_config({"market": {"slug": "x"}})
        eid = compute_exp_id(cfg, now=dt.datetime(2026, 5, 10),
                              git_sha="0123456789abcdef")
        # exp_id = <ts>-<name>-<git_sha8>-<cfg_hash8>
        parts = eid.split("-")
        # name "baseline" splits but git/cfg-hash come after — they're 8 chars.
        self.assertTrue(eid.startswith("20260510T000000-baseline-01234567-"))
        self.assertEqual(len(parts[-1]), 8)

    def test_same_config_different_ts_different_id(self):
        cfg = parse_config({"market": {"slug": "x"}})
        a = compute_exp_id(cfg, now=dt.datetime(2026, 5, 10, 0, 0, 0),
                            git_sha="abc")
        b = compute_exp_id(cfg, now=dt.datetime(2026, 5, 10, 0, 0, 1),
                            git_sha="abc")
        self.assertNotEqual(a, b)

    def test_different_config_different_hash(self):
        c1 = parse_config({"market": {"slug": "x"}})
        c2 = parse_config({"market": {"slug": "x"}, "agent": {"seed": 1}})
        self.assertNotEqual(_config_hash(c1), _config_hash(c2))

    def test_same_config_same_hash(self):
        c1 = parse_config({"market": {"slug": "x"}})
        c2 = parse_config({"market": {"slug": "x"}})
        self.assertEqual(_config_hash(c1), _config_hash(c2))


if __name__ == "__main__":
    unittest.main()
