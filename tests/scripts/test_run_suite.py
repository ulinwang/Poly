"""Tests for the multi-run driver (D4)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.run_experiment_suite import (
    _expand_b1_template, _run_one, discover_configs, run_suite,
)


REF_MARKET = "will-roman-roy-be-ceo-at-the-end-of-succession-s4"


def _write_cfg(path: Path, name: str, slug: str = REF_MARKET) -> None:
    path.write_text(yaml.safe_dump({
        "name": name,
        "market": {"slug": slug},
        "agent": {"population": "archetype", "n_agents": 5, "seed": 0},
    }, sort_keys=False))


class DiscoverConfigsTest(unittest.TestCase):
    def test_glob_returns_suite_files_only(self):
        with tempfile.TemporaryDirectory() as d:
            cd = Path(d)
            _write_cfg(cd / "b2_s0.yaml", "b2_s0")
            _write_cfg(cd / "b2_s1.yaml", "b2_s1")
            _write_cfg(cd / "b3_archetype_s0.yaml", "b3_archetype_s0")
            paths = discover_configs("b2", cd)
            self.assertEqual([p.name for p in paths],
                             ["b2_s0.yaml", "b2_s1.yaml"])

    def test_skips_markets_and_template_meta_files(self):
        with tempfile.TemporaryDirectory() as d:
            cd = Path(d)
            _write_cfg(cd / "b6_rumor_s0.yaml", "b6")
            (cd / "b6_markets.yaml").write_text("markets: []")
            (cd / "b6_template.yaml").write_text("name: t\nmarket:\n  slug: x")
            paths = discover_configs("b6", cd)
            self.assertEqual([p.name for p in paths],
                             ["b6_rumor_s0.yaml"])


class B1ExpansionTest(unittest.TestCase):
    def test_b1_template_expands_per_market(self):
        with tempfile.TemporaryDirectory() as d:
            cd = Path(d)
            tmpl = cd / "b1_template.yaml"
            tmpl.write_text(yaml.safe_dump({
                "name": "b1_replication",
                "market": {"slug": "{slug}"},
                "agent": {"population": "archetype",
                          "n_agents": 30, "seed": 0},
            }, sort_keys=False))
            mks = cd / "b1_markets.yaml"
            mks.write_text(yaml.safe_dump({
                "markets": [
                    {"slug": "mkt-a", "winning_idx": 1, "volume": 100.0},
                    {"slug": "mkt-b", "winning_idx": 0, "volume": 200.0},
                    {"slug": "mkt-c", "winning_idx": 1, "volume": 300.0},
                ],
            }, sort_keys=False))
            tmp = cd / "_tmp"
            paths = _expand_b1_template(tmpl, mks, tmp)
            self.assertEqual(len(paths), 3)
            slugs = []
            for p in paths:
                cfg = yaml.safe_load(p.read_text())
                slugs.append(cfg["market"]["slug"])
                self.assertNotIn("{slug}", cfg["market"]["slug"])
            self.assertEqual(sorted(slugs), ["mkt-a", "mkt-b", "mkt-c"])


class RunSuiteDryRunTest(unittest.TestCase):
    def test_sequential_dry_run_records_each_config(self):
        # Inject a stub runner so we don't need ClickHouse + data.
        called: list[str] = []

        def stub_runner(cfg_path, *, output_dir, dry_run):
            called.append(Path(cfg_path).name)
            assert dry_run, "expected dry_run=True"
            return f"exp-{Path(cfg_path).stem}"

        with tempfile.TemporaryDirectory() as d:
            cd = Path(d) / "cfgs"
            cd.mkdir()
            _write_cfg(cd / "btest_a.yaml", "a")
            _write_cfg(cd / "btest_b.yaml", "b")
            out = Path(d) / "out"
            idx = run_suite(
                "btest", config_dir=cd, output_dir=out,
                dry_run=True, runner_fn=stub_runner,
            )
            self.assertEqual(idx["n_runs"], 2)
            self.assertEqual(idx["n_ok"], 2)
            self.assertEqual(set(called), {"btest_a.yaml", "btest_b.yaml"})
            # index.json exists and is parseable
            self.assertTrue((out / "index.json").exists())
            j = json.loads((out / "index.json").read_text())
            self.assertEqual(j["n_runs"], 2)

    def test_failure_in_one_run_does_not_kill_suite(self):
        def stub_runner(cfg_path, *, output_dir, dry_run):
            if "fail" in str(cfg_path):
                raise RuntimeError("planted failure")
            return "exp-ok"

        with tempfile.TemporaryDirectory() as d:
            cd = Path(d) / "cfgs"
            cd.mkdir()
            _write_cfg(cd / "btest_ok.yaml", "ok")
            _write_cfg(cd / "btest_fail.yaml", "fail")
            out = Path(d) / "out"
            idx = run_suite(
                "btest", config_dir=cd, output_dir=out,
                dry_run=True, runner_fn=stub_runner,
            )
            self.assertEqual(idx["n_runs"], 2)
            self.assertEqual(idx["n_ok"], 1)
            self.assertEqual(idx["n_failed"], 1)
            failed = [r for r in idx["runs"] if r["status"] == "failed"]
            self.assertEqual(len(failed), 1)
            self.assertIn("planted failure", failed[0]["error"])


class RunOneTest(unittest.TestCase):
    def test_run_one_catches_systemexit(self):
        def stub(*a, **kw):
            raise SystemExit("priors not found")

        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.yaml"
            _write_cfg(cfg, "x")
            r = _run_one(cfg, Path(d), dry_run=True, runner_fn=stub)
            self.assertEqual(r["status"], "failed")
            self.assertIn("priors not found", r["error"])


if __name__ == "__main__":
    unittest.main()
