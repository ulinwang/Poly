from __future__ import annotations

import unittest
from unittest import mock

from data.analysis import coverage_report


class CoverageReportTest(unittest.TestCase):
    def test_gather_handles_missing_tables(self):
        ch = mock.MagicMock()
        # First execute() returns count, second returns max(fetched_at).
        # Pretend every table has 0 rows for simplicity.
        ch.client.execute.side_effect = lambda *a, **kw: [(0,)]
        out = coverage_report.gather(ch=ch)
        self.assertEqual(len(out), len(coverage_report.TABLES))
        for r in out:
            self.assertIn("table", r)
            self.assertIn("rows", r)


if __name__ == "__main__":
    unittest.main()
