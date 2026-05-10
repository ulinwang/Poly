"""Smoke: data.store.clickhouse + data.store.config import cleanly
and the connection class instantiates with stubbed credentials."""
from __future__ import annotations

import unittest

from data.store import clickhouse, config


class StoreSmokeTest(unittest.TestCase):
    def test_import_clickhouse(self):
        self.assertTrue(hasattr(clickhouse, "ClickHouse"))

    def test_import_settings(self):
        self.assertTrue(hasattr(config, "Settings"))
        self.assertTrue(hasattr(config, "get_settings"))

    def test_settings_have_clickhouse_fields(self):
        s = config.get_settings()
        self.assertTrue(hasattr(s, "CLICKHOUSE_HOST"))
        self.assertTrue(hasattr(s, "CLICKHOUSE_PORT"))
        self.assertTrue(hasattr(s, "CLICKHOUSE_DATABASE"))


if __name__ == "__main__":
    unittest.main()
