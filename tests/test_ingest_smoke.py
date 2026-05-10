"""Smoke tests: the user-authored ingest modules import cleanly
after the v7 move into src/ingest/. Network calls are NOT exercised
here — only that the module-level code (imports, constants, function
defs) loads."""
from __future__ import annotations

import unittest


class IngestImportTest(unittest.TestCase):
    def test_clob_api_imports(self):
        from src.ingest import clob_api
        self.assertTrue(hasattr(clob_api, "CLOB_BASE"))

    def test_data_api_imports(self):
        from src.ingest import data_api
        self.assertTrue(hasattr(data_api, "DATA_API_BASE"))

    def test_gamma_full_imports(self):
        from src.ingest import gamma_full
        self.assertTrue(hasattr(gamma_full, "iter_all_markets"))
        self.assertTrue(hasattr(gamma_full, "_to_float"))


if __name__ == "__main__":
    unittest.main()
