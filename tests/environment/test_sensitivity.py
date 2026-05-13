"""v13 (AGT-4) — within-tick ordering sensitivity probe.

Deterministic identity case (all HOLD → yes_mid_std = 0) and an
ordering-divergent case (two agents racing for the same liquidity
→ yes_mid_std > 0 if and only if order matters).
"""
from __future__ import annotations

import unittest

from agent.decision.types import Decision
from agent.factory import AgentInit
from environment.env import PolyEnv, seed_orderbook_liquidity, sensitivity_run


def _agent(agent_id: int, cap: float = 1000.0) -> AgentInit:
    return AgentInit(
        wallet_addr=f"0x{agent_id:040x}",
        persona_type="Calibrated", capital_initial=cap,
        profile_text="t", private_signal_mu=0.5, private_signal_sigma=0.2,
        risk_aversion=0.5, src_tx_count=10, src_maker_ratio=0.0,
        src_avg_position_usd=10.0, src_asset_diversity=2,
    )


def _market_meta() -> dict:
    return {
        "condition_id": "0xCID", "slug": "s", "question": "Q?",
        "description": "d", "end_date_iso": "2026-12-31T00:00:00",
        "winning_idx": 0,
    }


def _hold() -> Decision:
    return Decision("HOLD", "YES", "BUY", 0.0, 0.0, "h", "", 0, "")


def _market_buy(size_usd: float) -> Decision:
    return Decision("MARKET", "YES", "BUY", 0.0, size_usd, "t", "", 0, "")


def _market_sell(size_usd: float) -> Decision:
    return Decision("MARKET", "YES", "SELL", 0.0, size_usd, "t", "", 0, "")


def _limit_buy(price: float, size_usd: float) -> Decision:
    return Decision("LIMIT", "YES", "BUY", price, size_usd, "t", "", 0, "")


class WithinTickSensitivityTest(unittest.TestCase):
    def test_identity_case_zero_variance(self):
        env = PolyEnv(
            market_meta=_market_meta(),
            population=[_agent(0), _agent(1), _agent(2)],
            n_ticks=4, taker_fee_bps=0.0,
        )
        env.reset(seed=0)
        seed_orderbook_liquidity(env.state)
        actions = {0: _hold(), 1: _hold(), 2: _hold()}
        result = sensitivity_run(env, actions, n_orders=8)
        self.assertEqual(len(result["permutations"]), 8)
        self.assertEqual(result["yes_mid_std"], 0.0)
        self.assertEqual(result["n_fills_range"], 0)

    def test_ordering_divergent_case_has_variance(self):
        # Construct a case where within-tick order materially changes
        # the post-tick yes_mid.
        #   - Agent 0 places a LIMIT SELL at 0.45 (below the seeded
        #     best ask of 0.50, above the seeded best bid of 0.40).
        #   - Agent 1 fires a MARKET BUY of $20.
        # If A0 is processed first → its 0.45 ask is the new inside
        # offer; A1's market BUY eats it first at 0.45 before lifting
        # the 0.50 level → fewer 0.50 shares consumed → best_ask
        # remains at 0.50 with depth.
        # If A1 is processed first → it eats the 0.50 level directly;
        # then A0's 0.45 SELL rests, becoming the new best_ask = 0.45.
        # Result: best_ask, and therefore yes_mid, *differ* between
        # the two orderings.
        env = PolyEnv(
            market_meta=_market_meta(),
            population=[_agent(0, 1000.0), _agent(1, 1000.0)],
            n_ticks=4, taker_fee_bps=0.0,
        )
        env.reset(seed=0)
        env.state.book_yes.add_limit(999_998, "SELL", 0.50, 30.0, ts=-1)
        env.state.book_yes.add_limit(999_998, "SELL", 0.60, 30.0, ts=-1)
        env.state.book_yes.add_limit(999_998, "BUY", 0.40, 100.0, ts=-1)
        # Give A0 inventory so it can SELL.
        env.state.agents[0].yes_shares = 50.0
        actions = {
            0: Decision("LIMIT", "YES", "SELL", 0.45, 5.0,
                        "t", "", 0, ""),
            1: _market_buy(20.0),
        }
        result = sensitivity_run(env, actions, n_orders=12)
        self.assertGreater(
            result["yes_mid_std"] + result["n_fills_range"], 0,
            f"expected ordering to matter, got {result}",
        )

    def test_original_env_state_restored_after_probe(self):
        env = PolyEnv(
            market_meta=_market_meta(),
            population=[_agent(0), _agent(1)],
            n_ticks=4, taker_fee_bps=0.0,
        )
        env.reset(seed=0)
        seed_orderbook_liquidity(env.state)
        n_resting_before = len(env.state.book_yes.bids) + len(env.state.book_yes.asks)
        actions = {0: _hold(), 1: _hold()}
        sensitivity_run(env, actions, n_orders=3)
        # Book preserved
        n_resting_after = len(env.state.book_yes.bids) + len(env.state.book_yes.asks)
        self.assertEqual(n_resting_before, n_resting_after)
        # Tick counter not advanced (probe is non-mutating)
        self.assertEqual(env._tick, 0)


if __name__ == "__main__":
    unittest.main()
