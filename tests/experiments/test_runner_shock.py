"""Tests for v13 B6 rumor-shock injection.

These tests cover (a) config parses with the new `experiment.shock`
block and (b) `apply_shock_if_due` mutates every agent's memory at
the right tick, and is a no-op at other ticks."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from experiments.config import parse_config, ShockConfig, ShockPayload
from experiments.runner import apply_shock_if_due


def _stub_sim(n_agents: int = 3, yes_mid: float = 0.5):
    """Build a duck-typed sim with N agents each with an empty memory
    list. Avoids spinning up PolyEnv."""
    agents = []
    for i in range(n_agents):
        agents.append(SimpleNamespace(
            agent_id=i, memory=[],
            persona=SimpleNamespace(persona_type="Test"),
        ))
    return SimpleNamespace(agents=agents, yes_mid=yes_mid)


class ShockConfigParseTest(unittest.TestCase):
    def test_parses_with_shock(self):
        cfg = parse_config({
            "name": "b6_test",
            "market": {"slug": "x"},
            "experiment": {
                "shock": {
                    "tick": 12,
                    "kind": "rumor",
                    "payload": {"text": "earnings beat expectations"},
                },
            },
        })
        self.assertIsNotNone(cfg.experiment.shock)
        self.assertEqual(cfg.experiment.shock.tick, 12)
        self.assertEqual(cfg.experiment.shock.kind, "rumor")
        self.assertEqual(
            cfg.experiment.shock.payload.text,
            "earnings beat expectations",
        )

    def test_parses_without_shock(self):
        cfg = parse_config({"name": "n", "market": {"slug": "x"}})
        self.assertIsNone(cfg.experiment.shock)

    def test_belief_update_flag_default_false(self):
        cfg = parse_config({"name": "n", "market": {"slug": "x"}})
        self.assertFalse(cfg.agent.belief_update_enabled)


class ApplyShockIfDueTest(unittest.TestCase):
    def test_fires_at_configured_tick(self):
        sim = _stub_sim(n_agents=4)
        shock = ShockConfig(
            tick=5, kind="rumor",
            payload=ShockPayload(text="[breaking] big news"),
        )
        n = apply_shock_if_due(sim, tick=5, shock_cfg=shock)
        self.assertEqual(n, 4)
        for a in sim.agents:
            self.assertEqual(len(a.memory), 1)
            entry = a.memory[0]
            self.assertEqual(entry["action"], "EXTERNAL_NEWS")
            self.assertEqual(entry["tick"], 5)
            self.assertIn("big news", entry["reasoning"])
            self.assertEqual(entry["kind"], "rumor")

    def test_no_op_at_other_ticks(self):
        sim = _stub_sim(n_agents=2)
        shock = ShockConfig(
            tick=5, kind="rumor",
            payload=ShockPayload(text="news"),
        )
        for t in (0, 3, 6, 47):
            self.assertEqual(
                apply_shock_if_due(sim, tick=t, shock_cfg=shock), 0,
            )
        for a in sim.agents:
            self.assertEqual(a.memory, [])

    def test_no_op_when_shock_none(self):
        sim = _stub_sim(n_agents=2)
        for t in (0, 12, 50):
            self.assertEqual(
                apply_shock_if_due(sim, tick=t, shock_cfg=None), 0,
            )
        for a in sim.agents:
            self.assertEqual(a.memory, [])

    def test_memory_visible_via_observe(self):
        """After injection, an observer's recent_decisions must
        include the shock entry (proxy for the LLM seeing it)."""
        from environment.observers.quote_only import observe
        from environment.env import make_sim
        from tests._helpers import make_test_personas

        sim = make_sim(
            market_id="cid", market_slug="s", question="?",
            description="", end_date_str="", market_resolved_yes=None,
            personas=make_test_personas(3), n_ticks=10,
            taker_fee_bps=0.0,
        )
        # Convert plain Persona personas into the runtime list the env uses.
        # make_sim handles that internally — we just call apply_shock.
        shock = ShockConfig(
            tick=3, kind="rumor",
            payload=ShockPayload(text="rumor body"),
        )
        n = apply_shock_if_due(sim, tick=3, shock_cfg=shock)
        self.assertEqual(n, 3)
        # The default MEMORY_DEPTH = 3; we appended exactly one entry,
        # so it must appear in recent_decisions.
        _, agent_snap = observe(sim, sim.agents[0].agent_id)
        rd = agent_snap.recent_decisions
        self.assertTrue(rd, "recent_decisions empty after shock")
        self.assertEqual(rd[-1]["action"], "EXTERNAL_NEWS")
        self.assertIn("rumor body", rd[-1]["reasoning"])


if __name__ == "__main__":
    unittest.main()
