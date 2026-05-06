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


class FeeFormulaTest(unittest.TestCase):
    """Polymarket fee spec: fee = C * feeRate * p * (1 - p).
    Symmetric around 0.5, ~0 at extremes."""

    def _run_taker_buy(self, *, fee_bps: float, price: float, size: float):
        """Set up agent 0 as resting SELL @ price, agent 1 takes it. Returns
        (filled_size, notional, fee_paid)."""
        decisions = [
            # tick 0: agent 0 SELL @ price, agent 1 HOLD
            Decision("LIMIT", "YES", "SELL", price, size * price, "ask", "", 0, ""),
            Decision("HOLD",  "YES", "BUY",  0.0,   0,            "wait", "", 0, ""),
            # tick 1: agent 0 HOLD, agent 1 BUY (crosses)
            Decision("HOLD",  "YES", "SELL", 0.0,   0,            "rest", "", 0, ""),
            Decision("LIMIT", "YES", "BUY",  price, size * price, "cross", "", 0, ""),
        ]
        import random
        for seed in (0, 1, 42, 100, 7):
            sim2 = _make_sim(n=2, n_ticks=2, fee_bps=fee_bps)
            sim2.agents[0].yes_shares = size + 10.0
            initial_taker_cash = sim2.agents[1].cash
            env.run_simulation(
                sim2, api_key="x", base_url="x", model="x",
                decide_fn=_stub_decide(list(decisions)),
                log_progress=False, rng=random.Random(seed),
            )
            if sim2.fills_log:
                filled_size = sum(row[9] for row in sim2.fills_log)
                notional = sum(row[10] for row in sim2.fills_log)
                taker_spent = initial_taker_cash - sim2.agents[1].cash
                fee_paid = taker_spent - notional
                return filled_size, notional, fee_paid
        self.fail("no fills produced across rng seeds")

    def test_fee_zero_at_extreme_prices(self):
        # 2% fee at p=0.01 -> fee per share = 0.02 * 0.01 * 0.99 ~ 0.000198
        size, _, fee = self._run_taker_buy(fee_bps=200, price=0.01, size=100.0)
        expected = size * 0.02 * 0.01 * 0.99
        self.assertAlmostEqual(fee, expected, places=6)
        self.assertLess(fee, 0.05)

    def test_fee_max_at_50_50(self):
        # 2% fee at p=0.50 -> fee per share = 0.02 * 0.5 * 0.5 = 0.005
        size, _, fee = self._run_taker_buy(fee_bps=200, price=0.50, size=100.0)
        expected = size * 0.02 * 0.25
        self.assertAlmostEqual(fee, expected, places=6)

    def test_fee_symmetric(self):
        s1, _, fee_30 = self._run_taker_buy(fee_bps=200, price=0.30, size=50.0)
        s2, _, fee_70 = self._run_taker_buy(fee_bps=200, price=0.70, size=50.0)
        self.assertAlmostEqual(s1, s2)
        self.assertAlmostEqual(fee_30, fee_70, places=6)


class SplitMergeTest(unittest.TestCase):
    """SPLIT: $X cash -> X YES + X NO. MERGE: X YES + X NO -> $X cash."""

    def _agent_with_cash(self, cash: float, yes: float = 0.0, no: float = 0.0):
        sim = _make_sim(n=1, n_ticks=1)
        sim.agents[0].cash = cash
        sim.agents[0].yes_shares = yes
        sim.agents[0].no_shares = no
        return sim

    def test_split_creates_both_outcomes(self):
        sim = self._agent_with_cash(1000.0)
        agent = sim.agents[0]
        decision = Decision(
            order_type="SPLIT", outcome="YES", side="BUY",
            price=0.0, size_usd=200.0,
            reasoning="fund", raw_response="", api_latency_ms=0, api_error="",
        )
        fills, shares, err = env._execute_decision(sim, agent, decision, tick=0)
        self.assertEqual(err, "")
        self.assertEqual(fills, [])
        self.assertAlmostEqual(shares, 200.0)
        self.assertAlmostEqual(agent.cash, 800.0)
        self.assertAlmostEqual(agent.yes_shares, 200.0)
        self.assertAlmostEqual(agent.no_shares, 200.0)

    def test_merge_destroys_both(self):
        sim = self._agent_with_cash(400.0, yes=50.0, no=50.0)
        agent = sim.agents[0]
        decision = Decision(
            order_type="MERGE", outcome="YES", side="SELL",
            price=0.0, size_usd=30.0,
            reasoning="redeem", raw_response="", api_latency_ms=0, api_error="",
        )
        fills, pairs, err = env._execute_decision(sim, agent, decision, tick=0)
        self.assertEqual(err, "")
        self.assertEqual(fills, [])
        self.assertAlmostEqual(pairs, 30.0)
        self.assertAlmostEqual(agent.cash, 430.0)
        self.assertAlmostEqual(agent.yes_shares, 20.0)
        self.assertAlmostEqual(agent.no_shares, 20.0)

    def test_split_capped_by_cash(self):
        sim = self._agent_with_cash(50.0)
        agent = sim.agents[0]
        decision = Decision(
            order_type="SPLIT", outcome="YES", side="BUY",
            price=0.0, size_usd=200.0,
            reasoning="want more than I have", raw_response="",
            api_latency_ms=0, api_error="",
        )
        _, shares, err = env._execute_decision(sim, agent, decision, tick=0)
        self.assertEqual(err, "")
        self.assertAlmostEqual(shares, 50.0)
        self.assertAlmostEqual(agent.cash, 0.0)
        self.assertAlmostEqual(agent.yes_shares, 50.0)
        self.assertAlmostEqual(agent.no_shares, 50.0)

    def test_merge_capped_by_min_held(self):
        sim = self._agent_with_cash(0.0, yes=10.0, no=50.0)
        agent = sim.agents[0]
        decision = Decision(
            order_type="MERGE", outcome="YES", side="SELL",
            price=0.0, size_usd=40.0,
            reasoning="redeem all I can", raw_response="",
            api_latency_ms=0, api_error="",
        )
        _, pairs, err = env._execute_decision(sim, agent, decision, tick=0)
        self.assertEqual(err, "")
        self.assertAlmostEqual(pairs, 10.0)
        self.assertAlmostEqual(agent.cash, 10.0)
        self.assertAlmostEqual(agent.yes_shares, 0.0)
        self.assertAlmostEqual(agent.no_shares, 40.0)

    def test_split_zero_cash_returns_error(self):
        sim = self._agent_with_cash(0.0)
        agent = sim.agents[0]
        decision = Decision(
            order_type="SPLIT", outcome="YES", side="BUY",
            price=0.0, size_usd=100.0,
            reasoning="broke", raw_response="", api_latency_ms=0, api_error="",
        )
        _, shares, err = env._execute_decision(sim, agent, decision, tick=0)
        self.assertEqual(err, "insufficient_cash")
        self.assertEqual(shares, 0.0)

    def test_merge_no_inventory_returns_error(self):
        sim = self._agent_with_cash(100.0, yes=0.0, no=10.0)
        agent = sim.agents[0]
        decision = Decision(
            order_type="MERGE", outcome="YES", side="SELL",
            price=0.0, size_usd=5.0,
            reasoning="no yes", raw_response="", api_latency_ms=0, api_error="",
        )
        _, pairs, err = env._execute_decision(sim, agent, decision, tick=0)
        self.assertEqual(err, "insufficient_pairs")
        self.assertEqual(pairs, 0.0)


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


class V4PopulationTest(unittest.TestCase):
    def test_make_sim_accepts_population(self):
        from src.sim.initialization import AgentInit
        pop = [
            AgentInit(
                wallet_addr="0xabc", persona_type="Calibrated",
                capital_initial=500.0, profile_text="You trade carefully.",
                private_signal_mu=0.4, private_signal_sigma=0.15,
                risk_aversion=0.6, src_tx_count=20, src_maker_ratio=0.5,
                src_avg_position_usd=25.0, src_asset_diversity=4,
            ),
            AgentInit(
                wallet_addr="0xdef", persona_type="Calibrated",
                capital_initial=200.0, profile_text="You take long shots.",
                private_signal_mu=0.7, private_signal_sigma=0.25,
                risk_aversion=0.2, src_tx_count=10, src_maker_ratio=0.1,
                src_avg_position_usd=15.0, src_asset_diversity=2,
            ),
        ]
        sim = env.make_sim(
            market_id="m1", market_slug="t", question="?", description="",
            end_date_str="2026-12-31", market_resolved_yes=0,
            population=pop, n_ticks=2, taker_fee_bps=0.0,
        )
        self.assertEqual(len(sim.agents), 2)
        self.assertEqual(sim.agents[0].cash, 500.0)
        self.assertEqual(sim.agents[0].private_signal_mu, 0.4)
        self.assertEqual(sim.agents[0].src_wallet_addr, "0xabc")
        self.assertEqual(sim.agents[1].private_signal_sigma, 0.25)

    def test_make_sim_rejects_both_or_neither(self):
        from src.sim.personas import DEFAULT_PERSONAS, assign_personas
        with self.assertRaises(ValueError):
            env.make_sim(
                market_id="m1", market_slug="t", question="?", description="",
                end_date_str="x", market_resolved_yes=0, n_ticks=1,
                taker_fee_bps=0.0,
                personas=assign_personas(2, DEFAULT_PERSONAS),
                population=[],
            )
        with self.assertRaises(ValueError):
            env.make_sim(
                market_id="m1", market_slug="t", question="?", description="",
                end_date_str="x", market_resolved_yes=0, n_ticks=1,
                taker_fee_bps=0.0,
            )


class SeedLiquidityTest(unittest.TestCase):
    def test_seed_creates_two_sided_books(self):
        sim = _make_sim(n=2, n_ticks=1)
        env.seed_orderbook_liquidity(sim)
        self.assertGreater(len(sim.book_yes.bids), 0)
        self.assertGreater(len(sim.book_yes.asks), 0)
        self.assertGreater(len(sim.book_no.bids), 0)
        self.assertGreater(len(sim.book_no.asks), 0)
        for o in sim.book_yes.bids + sim.book_yes.asks:
            self.assertEqual(o.agent_id, env.ENV_MAKER_AGENT_ID)
        # symmetric seed → mid near 0.5
        self.assertAlmostEqual(sim.yes_mid, 0.5, places=2)

    def test_seed_respects_anchors(self):
        sim = _make_sim(n=1, n_ticks=1)
        env.seed_orderbook_liquidity(sim, yes_anchor=0.30, no_anchor=0.70)
        # Best YES bid below anchor 0.30; best ask above
        self.assertLess(sim.book_yes.best_bid(), 0.30)
        self.assertGreater(sim.book_yes.best_ask(), 0.30)


class V5ReservationTest(unittest.TestCase):
    """C4 / C5: LIMIT placement reserves cash (BUY) or inventory
    (SELL) so a single agent cannot over-commit. CANCEL releases the
    reservation; fills also release as the reservation is realized."""

    def _basic_sim_with(self, **agent_kwargs):
        sim = _make_sim(n=1, n_ticks=1)
        a = sim.agents[0]
        for k, v in agent_kwargs.items():
            setattr(a, k, v)
        return sim, a

    def test_limit_buy_reserves_cash(self):
        sim, a = self._basic_sim_with(cash=1000.0)
        decision = Decision(
            order_type="LIMIT", outcome="YES", side="BUY",
            price=0.30, size_usd=300.0,
            reasoning="bid", raw_response="", api_latency_ms=0, api_error="",
        )
        env._execute_decision(sim, a, decision, tick=0)
        self.assertAlmostEqual(a.cash, 1000.0)            # cash itself unchanged
        self.assertAlmostEqual(a.cash_reserved, 300.0)    # reserved
        self.assertAlmostEqual(env.available_cash(a), 700.0)

    def test_double_limit_buy_capped_by_available(self):
        sim, a = self._basic_sim_with(cash=500.0)
        d1 = Decision("LIMIT", "YES", "BUY", 0.50, 300.0, "1", "", 0, "")
        d2 = Decision("LIMIT", "YES", "BUY", 0.40, 400.0, "2", "", 0, "")
        env._execute_decision(sim, a, d1, tick=0)
        env._execute_decision(sim, a, d2, tick=0)
        # First reserved $300; available was $200 for the second; the
        # second order rests for $200 worth of shares at 0.40.
        self.assertAlmostEqual(a.cash_reserved, 500.0, places=4)
        self.assertAlmostEqual(env.available_cash(a), 0.0, places=4)

    def test_limit_sell_reserves_inventory(self):
        sim, a = self._basic_sim_with(cash=0.0, yes_shares=100.0)
        d1 = Decision("LIMIT", "YES", "SELL", 0.30, 30.0, "1", "", 0, "")
        d2 = Decision("LIMIT", "YES", "SELL", 0.31, 30.0, "2", "", 0, "")
        env._execute_decision(sim, a, d1, tick=0)
        env._execute_decision(sim, a, d2, tick=0)
        # First reserves 100 (size_usd 30 / 0.30 = 100 shares),
        # exactly filling the inventory; second has nothing to reserve.
        self.assertAlmostEqual(a.yes_reserved, 100.0, places=4)
        self.assertAlmostEqual(env.available_shares(a, "YES"), 0.0, places=4)

    def test_cancel_unreserves_cash(self):
        sim, a = self._basic_sim_with(cash=1000.0)
        place = Decision("LIMIT", "YES", "BUY", 0.30, 300.0, "1", "", 0, "")
        cancel = Decision("CANCEL", "YES", "BUY", 0.0, 0.0, "go", "", 0, "")
        env._execute_decision(sim, a, place, tick=0)
        self.assertAlmostEqual(a.cash_reserved, 300.0)
        env._execute_decision(sim, a, cancel, tick=1)
        self.assertAlmostEqual(a.cash_reserved, 0.0)
        self.assertAlmostEqual(env.available_cash(a), 1000.0)

    def test_cancel_unreserves_inventory(self):
        sim, a = self._basic_sim_with(cash=0.0, yes_shares=100.0)
        place = Decision("LIMIT", "YES", "SELL", 0.30, 30.0, "1", "", 0, "")
        cancel = Decision("CANCEL", "YES", "SELL", 0.0, 0.0, "go", "", 0, "")
        env._execute_decision(sim, a, place, tick=0)
        self.assertAlmostEqual(a.yes_reserved, 100.0)
        env._execute_decision(sim, a, cancel, tick=1)
        self.assertAlmostEqual(a.yes_reserved, 0.0)

    def test_self_match_releases_reservation(self):
        # Single agent BUY then SELL crossing → resting BUY cancelled
        # by self-match prevention; its cash reservation must be freed.
        sim, a = self._basic_sim_with(cash=1000.0, yes_shares=100.0)
        buy  = Decision("LIMIT", "YES", "BUY",  0.40, 40.0, "1", "", 0, "")
        sell = Decision("LIMIT", "YES", "SELL", 0.30, 30.0, "2", "", 0, "")
        env._execute_decision(sim, a, buy, tick=0)
        self.assertAlmostEqual(a.cash_reserved, 40.0)
        env._execute_decision(sim, a, sell, tick=1)
        # Buy got cancelled by self-match; new sell rests at 0.30.
        # Cash reservation should be 0 (BUY freed); inventory
        # reservation should be 100 (SELL is for 30/0.30 = 100 shares).
        self.assertAlmostEqual(a.cash_reserved, 0.0)
        self.assertAlmostEqual(a.yes_reserved, 100.0)


if __name__ == "__main__":
    unittest.main()
