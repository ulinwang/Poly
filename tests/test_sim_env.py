from __future__ import annotations

import unittest

from src.sim import env
from src.sim.agent import Decision
from src.sim.personas import DEFAULT_PERSONAS, assign_personas


def _make_sim(n=2, n_ticks=1, fee_bps=0.0, resolved_yes=0):
    ps = assign_personas(n, DEFAULT_PERSONAS)
    return env.make_sim(
        market_id="m1", market_slug="test",
        question="will it happen?", description="rules",
        end_date_str="2026-06-30",
        market_resolved_yes=resolved_yes,
        personas=ps, n_ticks=n_ticks, taker_fee_bps=fee_bps,
    )


def _stub_decide(decisions):
    """Returns a fake decide_fn that yields the given Decisions in order."""
    it = iter(decisions)

    def fn(**kwargs):
        try:
            return next(it)
        except StopIteration:
            return Decision(
                order_type="HOLD", outcome="YES", side="BUY",
                price=0.5, size_usd=0.0, reasoning="end",
                raw_response="", api_latency_ms=0, api_error="",
            )
    return fn


class CloubEnvSmokeTest(unittest.TestCase):
    def test_make_sim_initializes_clean_books(self):
        sim = _make_sim(n=3)
        self.assertEqual(len(sim.agents), 3)
        self.assertEqual(sim.yes_mid, 0.5)
        self.assertEqual(sim.no_mid, 0.5)
        self.assertEqual(len(sim.book_yes.bids), 0)

    def test_buy_low_against_resting_ask_fills(self):
        # Pre-seed inventory so agent 0 can SELL legitimately.
        sim = _make_sim(n=2, n_ticks=2)
        sim.agents[0].yes_shares = 100.0
        # Tick 0: agent 0 LIMIT SELL YES @ 0.30, $30 worth
        # Tick 1: agent 1 LIMIT BUY  YES @ 0.40, $40 worth (crosses)
        decisions = [
            Decision("LIMIT", "YES", "SELL", 0.30, 30, "ask", "", 0, ""),
            Decision("HOLD",  "YES", "BUY",  0.0,  0,  "rest", "", 0, ""),
            Decision("HOLD",  "YES", "SELL", 0.0,  0,  "rest", "", 0, ""),
            Decision("LIMIT", "YES", "BUY",  0.40, 40, "cross", "", 0, ""),
        ]
        import random
        # Try multiple rng seeds; the test only requires that the
        # crossing pair eventually fills regardless of within-tick order.
        for seed in (0, 1, 42, 100):
            sim2 = _make_sim(n=2, n_ticks=2)
            sim2.agents[0].yes_shares = 100.0
            env.run_simulation(
                sim2, api_key="x", base_url="x", model="x",
                decide_fn=_stub_decide(list(decisions)),
                log_progress=False, rng=random.Random(seed),
            )
            if sim2.fills_log:
                # At least one fill at maker (0.30) price
                self.assertEqual(sim2.fills_log[0][8], 0.30)  # price column
                return
        self.fail("no fills across multiple rng seeds")

    def test_market_buy_eats_resting_ask(self):
        sim = _make_sim(n=2, n_ticks=2)
        # Pre-seed agent 0 with YES inventory so they can SELL.
        sim.agents[0].yes_shares = 100.0
        # Tick 0: agent 0 LIMIT SELL YES @ 0.40 $40
        # Tick 1: agent 1 MARKET BUY YES $30
        decisions = [
            Decision("LIMIT",  "YES", "SELL", 0.40, 40, "ask", "", 0, ""),
            Decision("HOLD",   "YES", "BUY",  0.0,  0,  "wait", "", 0, ""),
            Decision("HOLD",   "YES", "SELL", 0.0,  0,  "rest", "", 0, ""),
            Decision("MARKET", "YES", "BUY",  0.0,  30, "eat", "", 0, ""),
        ]
        import random
        for seed in (0, 1, 42, 100):
            sim2 = _make_sim(n=2, n_ticks=2)
            sim2.agents[0].yes_shares = 100.0
            env.run_simulation(
                sim2, api_key="x", base_url="x", model="x",
                decide_fn=_stub_decide(list(decisions)),
                log_progress=False, rng=random.Random(seed),
            )
            if sim2.fills_log:
                # Agent 1 (taker BUY) should now hold some YES
                self.assertGreater(sim2.agents[1].yes_shares, 0)
                return
        self.fail("no fills across multiple rng seeds")


class SettlementTest(unittest.TestCase):
    def test_settle_no_resolution_returns_empty(self):
        sim = _make_sim(n=2, resolved_yes=None)
        sim.market_resolved_yes = None
        self.assertEqual(env.settle(sim), {})

    def test_settle_pays_winners(self):
        sim = _make_sim(n=2, resolved_yes=1)  # YES wins
        # Manually grant agent 0 some YES shares; agent 1 some NO shares.
        sim.agents[0].yes_shares = 50.0
        sim.agents[0].cash -= 25.0   # paid $25 for them (avg 0.50)
        sim.agents[1].no_shares = 50.0
        sim.agents[1].cash -= 25.0
        pnl = env.settle(sim)
        # Agent 0 holds 50 YES, settlement pays 50 * $1 = $50; minus $25 cost = +$25
        self.assertAlmostEqual(pnl[0], 25.0)
        # Agent 1 holds 50 NO, NO pays $0; net -$25
        self.assertAlmostEqual(pnl[1], -25.0)


if __name__ == "__main__":
    unittest.main()
