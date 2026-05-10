from __future__ import annotations

import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from experiments.parquet_sink import (
    ACTION_COLUMNS, FILL_COLUMNS, POSITION_COLUMNS, PERSONA_COLUMNS,
    write_parquet, dump_simulation, append_llm_call, read_parquet,
)


class _StubSim:
    def __init__(self):
        self.sim_id = "abc"
        self.actions_log = [
            ("abc", 0, 1, "HOLD", "YES", "BUY", 0.0, 0.0,
             0.5, 0.5, 0.0, 0, "r", "", 0, "", dt.datetime.utcnow()),
        ]
        self.fills_log = []
        self.positions_log = [
            ("abc", 0, 1, 0.0, 0.0, 100.0, 0.0, 0.0),
        ]


class WriteParquetTest(unittest.TestCase):
    def test_writes_rows(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.parquet"
            n = write_parquet(
                [(1, 2, 3)], ["a", "b", "c"], p,
            )
            self.assertEqual(n, 1)
            self.assertTrue(p.exists())

    def test_empty_rows_writes_header_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "empty.parquet"
            n = write_parquet([], ["a", "b"], p)
            self.assertEqual(n, 0)
            self.assertTrue(p.exists())


class DumpSimulationTest(unittest.TestCase):
    def test_round_trip(self):
        sim = _StubSim()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "exp"
            res = dump_simulation(sim, out)
            self.assertEqual(res["agent_actions"], 1)
            self.assertEqual(res["agent_positions"], 1)
            self.assertEqual(res["agent_fills"], 0)
            df = read_parquet(out / "raw" / "agent_actions.parquet")
            self.assertEqual(len(df), 1)
            self.assertEqual(list(df.columns), ACTION_COLUMNS)

    def test_persona_rows_optional(self):
        sim = _StubSim()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "exp"
            personas = [(sim.sim_id, 1, "Calibrated", 0.5, 100.0, "p")]
            dump_simulation(sim, out, persona_rows=personas)
            self.assertTrue((out / "raw" / "agent_personas.parquet").exists())


class AppendLlmCallTest(unittest.TestCase):
    def test_appends_jsonl(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "exp"
            append_llm_call(out, "abc", 0, 1, "sys", "user", "resp")
            append_llm_call(out, "abc", 0, 2, "sys", "user", "resp2")
            lines = (out / "raw" / "llm_calls.jsonl").read_text().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[1])["agent_id"], 2)


if __name__ == "__main__":
    unittest.main()
