from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from experiments.checkpoint import (
    build_tick_summaries,
    estimate_context_chars,
    update_checkpoint,
)


class _StubAgent:
    def __init__(self, agent_id: int):
        self.agent_id = agent_id


class _StubSim:
    sim_id = "sim1"
    market_slug = "example-market"
    question = "Will example resolve YES?"
    market_resolved_yes = 1
    yes_mid = 0.62
    agents = [_StubAgent(0), _StubAgent(1)]

    def __init__(self):
        belief = {"yes_prob": 0.61, "confidence": 0.7, "rationale": "x"}
        self.actions_log = [
            (
                "sim1", 0, 0, "UPDATE_BELIEF", "", "", 0.61, 0.0,
                0.50, 0.50, 0.0, 0, "belief",
                json.dumps({"belief_update": belief}),
                0, "", dt.datetime.utcnow(),
            ),
            (
                "sim1", 0, 0, "LIMIT", "YES", "BUY", 0.60, 10.0,
                0.50, 0.62, 0.0, 1, "trade", "raw-response",
                0, "", dt.datetime.utcnow(),
            ),
        ]
        self.fills_log = [
            (
                "sim1", 0, 1, 2, 999999, 0, "YES", "SELL",
                0.60, 10.0, 6.0, dt.datetime.utcnow(),
            )
        ]


class CheckpointTest(unittest.TestCase):
    def test_build_tick_summary_and_handoff(self):
        sim = _StubSim()
        rows = build_tick_summaries(sim)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["tick"], 0)
        self.assertEqual(rows[0]["n_belief_updates"], 1)
        self.assertEqual(rows[0]["n_fills"], 1)
        self.assertAlmostEqual(rows[0]["belief_yes_prob_mean"], 0.61)
        self.assertGreater(estimate_context_chars(sim), 0)

        with tempfile.TemporaryDirectory() as d:
            result = update_checkpoint(
                Path(d), sim=sim, tick=0, n_ticks=1,
                force_handoff=True, reason="test",
            )
            self.assertTrue(Path(result["tick_summary"]).exists())
            self.assertTrue(Path(result["handoff"]).exists())
            text = Path(result["handoff"]).read_text()
            self.assertIn("market_slug: `example-market`", text)
            self.assertIn("toward 1.00", text)


if __name__ == "__main__":
    unittest.main()
