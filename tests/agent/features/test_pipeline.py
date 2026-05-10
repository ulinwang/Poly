"""Smoke: build_features orchestrator + asof guardrails."""
from __future__ import annotations

import unittest

from agent.features import pipeline


class BuildFeaturesAsofTest(unittest.TestCase):
    def test_unsupported_asof_raises(self):
        with self.assertRaises(NotImplementedError):
            pipeline.build_features("anything", asof="end_of_day")


if __name__ == "__main__":
    unittest.main()
