"""Gym-style contract: reset → step → settle.

Drives PolyEnv with a tiny calibrated population (no LLM) and a few
hand-crafted decisions, verifying state evolves correctly and the
observer never leaks full-book info."""
from __future__ import annotations

import unittest

from agent.factory import AgentInit
from agent.decision.types import Decision
from environment.env import PolyEnv


def _agent(agent_id: int = 0, cap: float = 100.0) -> AgentInit:
    return AgentInit(
        wallet_addr=f"0x{agent_id:040x}",
        persona_type="Calibrated", capital_initial=cap,
        profile_text="test trader",
        private_signal_mu=0.5, private_signal_sigma=0.2,
        risk_aversion=0.5,
        src_tx_count=10, src_maker_ratio=0.0,
        src_avg_position_usd=10.0, src_asset_diversity=2,
    )


def _market_meta() -> dict:
    return {
        "condition_id": "0xCID",
        "slug": "test-market",
        "question": "Will it work?",
        "description": "Resolves Yes if it works.",
        "end_date_iso": "2026-12-31T00:00:00",
        "winning_idx": 0,
    }


class PolyEnvContractTest(unittest.TestCase):
    def setUp(self):
        self.env = PolyEnv(
            market_meta=_market_meta(),
            population=[_agent(0, 100.0), _agent(1, 200.0)],
            n_ticks=4, taker_fee_bps=0.0,
        )

    def test_reset_returns_obs_per_agent(self):
        obs = self.env.reset(seed=42)
        self.assertEqual(set(obs), {0, 1})
        market, agent = obs[0]
        self.assertEqual(agent.cash, 100.0)
        # quote_only observer must NOT expose full bids/asks
        self.assertFalse(hasattr(market, "all_bids"))
        self.assertFalse(hasattr(market, "all_asks"))

    def test_step_advances_tick_and_logs(self):
        self.env.reset(seed=0)
        actions = {
            0: Decision("HOLD", "YES", "BUY", 0.0, 0.0, "h", "", 0, ""),
            1: Decision("HOLD", "YES", "BUY", 0.0, 0.0, "h", "", 0, ""),
        }
        obs, info = self.env.step(actions)
        self.assertEqual(info["tick"], 1)
        self.assertEqual(info["n_fills"], 0)
        self.assertEqual(len(self.env.state.actions_log), 2)
        self.assertEqual(len(self.env.state.positions_log), 2)

    def test_state_snapshot_is_simulation(self):
        self.env.reset(seed=0)
        from environment.env import Simulation
        self.assertIsInstance(self.env.state, Simulation)
        self.assertEqual(len(self.env.state.agents), 2)

    def test_step_before_reset_raises(self):
        env2 = PolyEnv(
            market_meta=_market_meta(), population=[_agent(0)],
            n_ticks=1, taker_fee_bps=0.0,
        )
        with self.assertRaises(RuntimeError):
            env2.step({})

    def test_settle_after_reset_returns_pnl(self):
        self.env.reset(seed=0)
        actions = {
            0: Decision("HOLD", "YES", "BUY", 0.0, 0.0, "", "", 0, ""),
            1: Decision("HOLD", "YES", "BUY", 0.0, 0.0, "", "", 0, ""),
        }
        for _ in range(self.env.n_ticks):
            self.env.step(actions)
        pnl = self.env.settle()
        # No trades happened; PnL = cash - capital_initial = 0 for both.
        self.assertEqual(pnl[0], 0.0)
        self.assertEqual(pnl[1], 0.0)


if __name__ == "__main__":
    unittest.main()
