"""Smoke tests: every data/sources/<name>/ sub-package imports
cleanly. Network calls are NOT exercised — only the module-level
code (imports, constants, function defs) loads.
"""
from __future__ import annotations

import unittest


class IngestImportTest(unittest.TestCase):
    def test_clob_api_imports(self):
        from data.sources import clob_api
        from data.sources.clob_api import schema, parsers
        self.assertTrue(hasattr(clob_api, "CLOB_BASE"))
        self.assertTrue(hasattr(schema, "ensure_clob_schemas"))
        self.assertTrue(hasattr(parsers, "market_to_row"))

    def test_data_api_imports(self):
        from data.sources import data_api
        from data.sources.data_api import schema, parsers
        self.assertTrue(hasattr(data_api, "DATA_API_BASE"))
        self.assertTrue(hasattr(schema, "ensure_dataapi_schemas"))
        self.assertTrue(hasattr(parsers, "trade_to_row"))

    def test_gamma_api_imports(self):
        from data.sources import gamma_api
        from data.sources.gamma_api import schema, parsers
        self.assertTrue(hasattr(gamma_api, "iter_all_markets"))
        self.assertTrue(hasattr(parsers, "_to_float"))
        self.assertTrue(hasattr(schema, "ensure_markets_full_schema"))

    def test_onchain_scaffold_imports(self):
        # v8 scaffold; puller raises NotImplementedError but module loads.
        from data.sources import onchain
        self.assertTrue(hasattr(onchain, "main"))


if __name__ == "__main__":
    unittest.main()
