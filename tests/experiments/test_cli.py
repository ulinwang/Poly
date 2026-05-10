"""Unit tests for experiments.cli — argparse dispatch + meta listing."""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from experiments import cli


class CmdRunTests(unittest.TestCase):
    def test_calls_run_experiment_and_prints_id(self):
        ns = mock.Mock(config="cfg.yaml", output_dir="output", dry_run=False)
        buf = io.StringIO()
        with mock.patch.object(cli, "run_experiment", return_value="exp_x") as r, \
             contextlib.redirect_stdout(buf):
            cli.cmd_run(ns)
        r.assert_called_once_with("cfg.yaml", output_dir="output", dry_run=False)
        self.assertIn("exp_id: exp_x", buf.getvalue())


class CmdListTests(unittest.TestCase):
    def test_no_output_dir_message(self):
        with tempfile.TemporaryDirectory() as t:
            missing = Path(t) / "nope"
            ns = mock.Mock(output_dir=str(missing))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli.cmd_list(ns)
            self.assertIn("(no experiments under", buf.getvalue())

    def test_skips_dirs_without_meta_json(self):
        with tempfile.TemporaryDirectory() as t:
            outd = Path(t)
            (outd / "exp1").mkdir()
            (outd / "exp1" / "meta.json").write_text(
                json.dumps({"config": {"name": "exp_one"}, "n_agents": 5})
            )
            (outd / "exp2_no_meta").mkdir()
            ns = mock.Mock(output_dir=str(outd))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli.cmd_list(ns)
            out = buf.getvalue()
            self.assertIn("exp1", out)
            self.assertIn("exp_one", out)
            self.assertNotIn("exp2_no_meta", out)

    def test_no_meta_at_all_message(self):
        with tempfile.TemporaryDirectory() as t:
            (Path(t) / "exp_no_meta").mkdir()
            ns = mock.Mock(output_dir=str(t))
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli.cmd_list(ns)
            self.assertIn("(no meta.json under", buf.getvalue())


class CmdShowTests(unittest.TestCase):
    def test_missing_meta_raises_systemexit(self):
        with tempfile.TemporaryDirectory() as t:
            ns = mock.Mock(output_dir=t, exp_id="nope")
            with self.assertRaises(SystemExit):
                cli.cmd_show(ns)

    def test_prints_meta_contents(self):
        with tempfile.TemporaryDirectory() as t:
            outd = Path(t)
            (outd / "exp1").mkdir()
            content = '{"hello": "world"}'
            (outd / "exp1" / "meta.json").write_text(content)
            ns = mock.Mock(output_dir=str(outd), exp_id="exp1")
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                cli.cmd_show(ns)
            self.assertIn("hello", buf.getvalue())


class MainTests(unittest.TestCase):
    def test_main_dispatches_run_subcommand(self):
        argv = ["experiments", "run", "cfg.yaml"]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(cli, "run_experiment", return_value="EID") as r:
            cli.main()
        r.assert_called_once()


if __name__ == "__main__":
    unittest.main()
