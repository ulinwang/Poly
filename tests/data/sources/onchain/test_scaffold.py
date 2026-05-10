"""v8 onchain modules are scaffolds — verify they raise as documented."""
from __future__ import annotations

import sys
import unittest
from unittest import mock

from data.sources.onchain import puller, decoder, schema


class OnchainPullerTests(unittest.TestCase):
    def test_main_raises_not_implemented(self):
        argv = ["data.sources.onchain.puller"]
        with mock.patch.object(sys, "argv", argv):
            with self.assertRaises(NotImplementedError):
                puller.main()


class OnchainDecoderTests(unittest.TestCase):
    def test_decode_log_raises(self):
        with self.assertRaises(NotImplementedError):
            decoder.decode_log({"topics": []}, "exchange")


class OnchainSchemaTests(unittest.TestCase):
    def test_order_filled_ddl_present(self):
        self.assertIn("CREATE TABLE", schema.ONCHAIN_ORDER_FILLED_DDL)
        self.assertIn("onchain_order_filled", schema.ONCHAIN_ORDER_FILLED_DDL)

    def test_module_exports_expected_ddl_constants(self):
        # The schema module is the home for v9 DDLs; at minimum
        # the OrderFilled DDL must exist as a string constant.
        self.assertIsInstance(schema.ONCHAIN_ORDER_FILLED_DDL, str)
        self.assertGreater(len(schema.ONCHAIN_ORDER_FILLED_DDL), 100)


if __name__ == "__main__":
    unittest.main()
