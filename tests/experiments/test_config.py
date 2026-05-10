from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from experiments.config import ExperimentConfig, parse_config
from experiments.runner import load_config


class ConfigDefaultsTest(unittest.TestCase):
    def test_minimal_config_uses_defaults(self):
        c = parse_config({"market": {"slug": "x"}})
        self.assertEqual(c.name, "baseline")
        self.assertEqual(c.agent.population, "calibrated")
        self.assertEqual(c.environment.observer, "quote_only")
        self.assertEqual(c.llm.temperature, 0.0)
        self.assertEqual(c.output.parquet_compression, "zstd")
        self.assertTrue(c.output.dual_write_clickhouse)

    def test_invalid_observer_raises(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            parse_config({"market": {"slug": "x"},
                          "environment": {"observer": "x-ray"}})

    def test_negative_temperature_passes(self):
        # No constraint on temperature in v8; pydantic accepts.
        c = parse_config({"market": {"slug": "x"},
                          "llm": {"temperature": -0.1}})
        self.assertEqual(c.llm.temperature, -0.1)


class LoadConfigTest(unittest.TestCase):
    def test_yaml_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "exp.yaml"
            yaml.safe_dump({
                "name": "demo",
                "market": {"slug": "abc"},
                "agent": {"seed": 42},
            }, p.open("w"))
            cfg = load_config(p)
            self.assertEqual(cfg.name, "demo")
            self.assertEqual(cfg.market.slug, "abc")
            self.assertEqual(cfg.agent.seed, 42)


if __name__ == "__main__":
    unittest.main()
