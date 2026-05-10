"""Retry-with-backoff invariants — closes a v5-audit queued item."""
from __future__ import annotations

import unittest
import urllib.error

from agent.decision.retry import call_with_retry


class CallWithRetryTest(unittest.TestCase):
    def test_returns_first_success(self):
        out = call_with_retry(lambda: "ok", max_attempts=3)
        self.assertEqual(out, "ok")

    def test_retries_then_succeeds(self):
        attempts = {"n": 0}

        def flaky():
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise urllib.error.URLError("transient")
            return "ok"

        out = call_with_retry(flaky, max_attempts=3, backoff_base_s=1.0)
        self.assertEqual(out, "ok")
        self.assertEqual(attempts["n"], 2)

    def test_reraises_after_max_attempts(self):
        def always_fail():
            raise urllib.error.URLError("permanent")

        with self.assertRaises(urllib.error.URLError):
            call_with_retry(always_fail, max_attempts=2, backoff_base_s=1.0)

    def test_does_not_retry_unrelated_exception(self):
        def boom():
            raise RuntimeError("unrelated")

        with self.assertRaises(RuntimeError):
            call_with_retry(boom, max_attempts=3, backoff_base_s=1.0)


if __name__ == "__main__":
    unittest.main()
