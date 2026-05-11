"""v9.3 — per-tick concurrent decision dispatch.

Verifies:
1. _resolve_concurrency translates None / 0 / N → effective worker count.
2. _decide_all_agents preserves per-agent outputs across serial vs concurrent.
3. Concurrent path actually runs in parallel (latency < serial).
4. append_llm_call is thread-safe (no interleaved partial lines).
"""
from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from agent.decision.types import AgentSnapshot, Decision, MarketSnapshot
from agent.personas.persona import Persona
from experiments.parquet_sink import append_llm_call
from experiments.runner import _decide_all_agents, _resolve_concurrency


def _persona() -> Persona:
    return Persona("Calibrated", 0.5, 100.0, "test trader")


def _market() -> MarketSnapshot:
    return MarketSnapshot(0.4, 0.5, 0.45, 0.5, 0.6, 0.55,
                          [0.5, 0.48, 0.45], 10, 48)


def _agent_state(aid: int) -> AgentSnapshot:
    return AgentSnapshot(aid, 100.0, 0.0, 0.0, 0)


class _StubSim:
    def __init__(self, n_agents: int):
        # AgentRuntime-like duck-typing (only attrs the runner reads).
        class _A:
            def __init__(self, i):
                self.agent_id = i
                self.persona = _persona()
        self.agents = [_A(i) for i in range(n_agents)]
        self.sim_id = "stub_sim"


class ResolveConcurrencyTest(unittest.TestCase):
    def test_none_caps_at_16(self):
        self.assertEqual(_resolve_concurrency(None, 50), 16)
        self.assertEqual(_resolve_concurrency(None, 4), 4)

    def test_zero_is_serial(self):
        self.assertEqual(_resolve_concurrency(0, 10), 1)
        self.assertEqual(_resolve_concurrency(1, 10), 1)

    def test_explicit_clamped_to_n_agents(self):
        self.assertEqual(_resolve_concurrency(20, 5), 5)
        self.assertEqual(_resolve_concurrency(4, 10), 4)


class DecideAllAgentsTest(unittest.TestCase):
    """End-to-end with a slow stub LLM. Serial should take ~N×latency;
    concurrent should take ~latency. Also verifies output parity."""

    LATENCY_S = 0.15
    N_AGENTS = 6

    def _make_obs(self, sim):
        return {
            a.agent_id: (_market(), _agent_state(a.agent_id))
            for a in sim.agents
        }

    def _slow_decide(self, **kwargs):
        """Stub `decide()` directly: sleep LATENCY then return a MARKET Decision."""
        time.sleep(self.LATENCY_S)
        return Decision(
            order_type="MARKET", outcome="YES", side="BUY",
            price=0.0, size_usd=10.0, reasoning="stub",
            raw_response="{}", api_latency_ms=int(self.LATENCY_S * 1000),
            api_error="",
        )

    def _invoke(self, *, concurrency: int, out_dir: Path):
        sim = _StubSim(self.N_AGENTS)
        obs = self._make_obs(sim)
        meta = {"question": "Q?", "description": "R", "end_date_iso": "2026"}

        # Patch decide() at the runner's import site so _decide_all_agents
        # picks up the stub. The latency lives in the stub itself.
        with mock.patch("experiments.runner.decide",
                        side_effect=self._slow_decide):
            t0 = time.time()
            actions = _decide_all_agents(
                sim=sim, obs=obs, meta=meta, tick=0, n_ticks_eff=1,
                api_key="x", base_url="x", model="x", tick_size=0.01,
                temperature=0.0, timeout_s=10, max_attempts=1,
                concurrency=concurrency, out_dir=out_dir,
            )
            elapsed = time.time() - t0
        return actions, elapsed

    def test_serial_path_correct(self):
        with tempfile.TemporaryDirectory() as d:
            actions, elapsed = self._invoke(concurrency=1, out_dir=Path(d))
            self.assertEqual(len(actions), self.N_AGENTS)
            for aid, dec in actions.items():
                self.assertIsInstance(dec, Decision)
                self.assertEqual(dec.order_type, "MARKET")
            # Serial: ~N * latency
            self.assertGreaterEqual(elapsed, self.LATENCY_S * self.N_AGENTS * 0.8)

    def test_concurrent_path_correct_and_faster(self):
        with tempfile.TemporaryDirectory() as d:
            actions, elapsed = self._invoke(
                concurrency=self.N_AGENTS, out_dir=Path(d),
            )
            self.assertEqual(len(actions), self.N_AGENTS)
            for aid, dec in actions.items():
                self.assertIsInstance(dec, Decision)
                self.assertEqual(dec.order_type, "MARKET")
            # Concurrent: ~1 * latency + thread overhead.
            # Must be << serial.
            serial_lower = self.LATENCY_S * self.N_AGENTS * 0.8
            self.assertLess(elapsed, serial_lower)

    def test_llm_calls_jsonl_thread_safe(self):
        """All N entries land cleanly under concurrent appends."""
        with tempfile.TemporaryDirectory() as d:
            self._invoke(concurrency=self.N_AGENTS, out_dir=Path(d))
            lines = (Path(d) / "raw" / "llm_calls.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), self.N_AGENTS)
            # Every line is valid JSON (no interleaved bytes from racing writes)
            agent_ids = []
            for line in lines:
                obj = json.loads(line)
                agent_ids.append(obj["agent_id"])
            self.assertEqual(sorted(agent_ids), list(range(self.N_AGENTS)))


class AppendLlmCallLockTest(unittest.TestCase):
    """Direct hammer on append_llm_call to catch any concurrency bug."""

    def test_100_concurrent_writes_no_corruption(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            N = 100

            def w(i):
                append_llm_call(out, "s", 0, i,
                                 system_prompt="sys", user_prompt="u",
                                 response="r" * 200)

            threads = [threading.Thread(target=w, args=(i,)) for i in range(N)]
            for t in threads: t.start()
            for t in threads: t.join()

            lines = (out / "raw" / "llm_calls.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), N)
            # Every line is parseable — proves the lock prevented interleaving.
            ids = sorted(json.loads(l)["agent_id"] for l in lines)
            self.assertEqual(ids, list(range(N)))


if __name__ == "__main__":
    unittest.main()
