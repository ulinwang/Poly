from __future__ import annotations

import unittest

from data.query import holders as q
from tests.data._stub_ch import StubCH


class GetBiosTest(unittest.TestCase):
    def test_strips_and_maps(self):
        ch = StubCH({
            "FROM polymetl.dataapi_holders": [
                ("0xabc", "alice", "  loves NBA  "),
                ("0xdef", "  ", None),
            ],
        })
        out = q.get_bios("0xCID", ch=ch)
        self.assertEqual(out["0xabc"]["bio"], "loves NBA")
        self.assertEqual(out["0xabc"]["display_name"], "alice")
        self.assertEqual(out["0xdef"]["bio"], "")
        self.assertEqual(out["0xdef"]["display_name"], "")


class GetTopHoldersTest(unittest.TestCase):
    def test_ordering_pass_through(self):
        ch = StubCH({
            "FROM polymetl.dataapi_holders": [
                ("0xa", 0, 1500.0, "Alice"),
                ("0xb", 1, 800.0, "Bob"),
            ],
        })
        rows = q.get_top_holders("0xCID", k=2, ch=ch)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][0], "0xa")


if __name__ == "__main__":
    unittest.main()
