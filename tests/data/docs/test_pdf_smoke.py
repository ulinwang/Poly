"""Import-only smoke tests for data.docs PDF generators.

Each module depends on reportlab (and the CH-bound dictionaries also
bind a `clickhouse_driver.Client` inside `main()`). We don't run them
end-to-end here — that would require a real CH and a binary-PDF
inspection pass. Instead we verify the modules are importable and
expose the documented entry points. If reportlab is not installed in
the dev environment, these tests skip cleanly so the rest of the suite
still passes.
"""
from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


HAS_REPORTLAB = importlib.util.find_spec("reportlab") is not None


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class PdfDictionarySmokeTests(unittest.TestCase):
    def test_clob_dictionary_imports_and_exposes_main(self):
        from data.docs import clob_dictionary
        self.assertTrue(hasattr(clob_dictionary, "main"))

    def test_data_dictionary_imports_and_exposes_main(self):
        from data.docs import data_dictionary
        self.assertTrue(hasattr(data_dictionary, "main"))

    def test_dataapi_dictionary_imports_and_exposes_main(self):
        from data.docs import dataapi_dictionary
        self.assertTrue(hasattr(dataapi_dictionary, "main"))


@unittest.skipUnless(HAS_REPORTLAB, "reportlab not installed")
class OutcomePricesPdfTests(unittest.TestCase):
    """outcome_prices.py is the only PDF generator with no CH dependency."""

    def test_main_writes_pdf_to_out_path(self):
        from data.docs import outcome_prices
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "explained.pdf"
            with mock.patch.object(sys, "argv",
                                    ["outcome_prices", "--out", str(out)]):
                outcome_prices.main()
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 1000)


if __name__ == "__main__":
    unittest.main()
