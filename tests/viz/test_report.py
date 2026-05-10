"""build_report writes a complete HTML file with all key sections."""
from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from viz.report import build_for_latest, build_report


def _write_fixture(d: Path) -> None:
    """Lay out a minimal output/<exp_id>/ tree."""
    raw = d / "raw"
    raw.mkdir(parents=True)
    analysis = d / "analysis"
    analysis.mkdir(parents=True)
    figure = d / "figure"
    figure.mkdir(parents=True)

    (d / "meta.json").write_text(json.dumps({
        "exp_id": "T-baseline-abc-def",
        "config": {"name": "baseline", "description": "test fixture",
                    "market": {"slug": "test-market"}},
        "started_at": "2026-05-10T00:00:00Z",
        "ended_at": "2026-05-10T00:01:00Z",
        "git_sha": "abcdef0123456789",
        "sim_id": "deadbeef0123",
        "n_agents": 2, "n_ticks": 3,
        "priors_summary": {
            "signal_mu": 0.42, "n_ticks": 3,
            "tick_size": 0.01, "taker_fee_bps": 0.0,
            "bootstrap_source": "dataapi_trades_dispersion",
            "winning_idx": 1,
        },
    }))
    (analysis / "summary.json").write_text(json.dumps({
        "sim_id": "deadbeef0123", "n_agents": 2, "n_ticks": 3,
        "pnl_mean": -1.0, "pnl_min": -10.0, "pnl_max": 5.0,
        "priors": {},
    }))

    pd.DataFrame({
        "sim_id": ["s"] * 6, "tick_idx": [0, 0, 1, 1, 2, 2],
        "agent_id": [0, 1, 0, 1, 0, 1],
        "action_type": ["LIMIT", "HOLD", "MARKET", "CANCEL", "HOLD", "HOLD"],
        "outcome": ["YES"] * 6, "side": ["BUY"] * 6,
        "price": [0.5, 0.0, 0.0, 0.0, 0.0, 0.0],
        "size_usd": [50.0, 0.0, 30.0, 0.0, 0.0, 0.0],
        "yes_mid_before": [0.50, 0.50, 0.50, 0.50, 0.55, 0.55],
        "yes_mid_after":  [0.50, 0.50, 0.55, 0.55, 0.55, 0.55],
        "shares_taken": [0.0] * 6, "n_fills": [0] * 6,
        "reasoning": [""] * 6, "raw_response": [""] * 6,
        "api_latency_ms": [0] * 6, "api_error": [""] * 6,
        "fetched_at": [dt.datetime.utcnow()] * 6,
    }).to_parquet(raw / "agent_actions.parquet")

    pd.DataFrame({
        "sim_id": ["s"] * 6, "tick_idx": [0, 0, 1, 1, 2, 2],
        "agent_id": [0, 1, 0, 1, 0, 1],
        "yes_shares": [0.0, 0.0, 10.0, 0.0, 10.0, 0.0],
        "no_shares":  [0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
        "cash":       [100.0, 100.0, 95.0, 100.0, 95.0, 100.0],
        "realized_pnl":   [0.0] * 6,
        "unrealized_pnl": [0.0] * 6,
    }).to_parquet(raw / "agent_positions.parquet")

    pd.DataFrame({
        "sim_id": ["s"] * 2, "agent_id": [0, 1],
        "persona_type": ["Calibrated"] * 2,
        "risk_aversion": [0.5, 0.5],
        "capital_initial": [100.0, 100.0],
        "profile_text": ["alpha trader"] * 2,
    }).to_parquet(raw / "agent_personas.parquet")

    pd.DataFrame().to_parquet(raw / "agent_fills.parquet")

    # one llm call
    (raw / "llm_calls.jsonl").write_text(json.dumps({
        "sim_id": "s", "tick": 0, "agent_id": 0,
        "system": "...", "user": "...", "response": "{...}"
    }) + "\n")

    # One placeholder figure file so the static-figures section renders.
    (figure / "01_market_landscape.png").write_bytes(b"\x89PNG\r\n\x1a\n")


class BuildReportTest(unittest.TestCase):
    def test_full_render(self):
        with tempfile.TemporaryDirectory() as d:
            exp = Path(d) / "T-baseline-abc-def"
            _write_fixture(exp)
            html_path = build_report(exp)
            self.assertTrue(html_path.exists())
            html = html_path.read_text()

            # Header + outcome badge
            self.assertIn("test-market", html)
            self.assertIn("baseline", html)
            self.assertIn("badge no", html)        # winning_idx=1 → NO badge

            # Priors block
            self.assertIn("0.420", html)            # signal_mu
            self.assertIn("dataapi_trades_dispersion", html)

            # Charts
            self.assertIn("plotly", html.lower())
            self.assertIn("trajectory", html)

            # Personas table
            self.assertIn("alpha trader", html)

            # Static figures
            self.assertIn("01_market_landscape", html)

            # LLM calls
            self.assertIn("LLM calls", html)

    def test_missing_meta_raises(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                build_report(Path(d))

    def test_build_for_latest(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            exp = base / "20260510T120000-x-aaa-bbb"
            _write_fixture(exp)
            html_path = build_for_latest(base)
            self.assertTrue(html_path.exists())


if __name__ == "__main__":
    unittest.main()
