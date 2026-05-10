from __future__ import annotations

import unittest

from agent.factory import AgentInit
from environment.env import ENV_MAKER_AGENT_ID, PolyEnv
from environment.seeders.from_clob_history import seed


def _agent(aid: int = 0) -> AgentInit:
    return AgentInit(
        wallet_addr=f"0x{aid:040x}",
        persona_type="Calibrated", capital_initial=100.0,
        profile_text="t",
        private_signal_mu=0.5, private_signal_sigma=0.2,
        risk_aversion=0.5,
        src_tx_count=0, src_maker_ratio=0.0,
        src_avg_position_usd=0.0, src_asset_diversity=0,
    )


class FromClobHistorySeederTest(unittest.TestCase):
    def test_seeds_book_with_priors(self):
        env = PolyEnv(
            market_meta={"condition_id": "0xCID", "winning_idx": 0},
            population=[_agent(0)], n_ticks=4, taker_fee_bps=0.0,
        )
        env.reset(seed=0)
        priors = {
            "bootstrap": {
                "anchor_yes": 0.6, "spread": 0.04,
                "depth_per_level": 100.0, "depth_levels": 2,
                "source": "clob_orderbook",
            },
        }
        seed(env.state, priors)
        # After seeding, both books should have ENV_MAKER_AGENT_ID orders.
        env_orders = [
            o for o in env.state.book_yes.bids + env.state.book_yes.asks
            if o.agent_id == ENV_MAKER_AGENT_ID
        ]
        self.assertGreater(len(env_orders), 0)

    def test_no_bootstrap_block_is_noop(self):
        env = PolyEnv(
            market_meta={"condition_id": "0xCID", "winning_idx": 0},
            population=[_agent(0)], n_ticks=4, taker_fee_bps=0.0,
        )
        env.reset(seed=0)
        seed(env.state, priors={})  # no-op
        # No env-maker orders.
        env_orders = [
            o for o in env.state.book_yes.bids + env.state.book_yes.asks
            if o.agent_id == ENV_MAKER_AGENT_ID
        ]
        self.assertEqual(len(env_orders), 0)


if __name__ == "__main__":
    unittest.main()
