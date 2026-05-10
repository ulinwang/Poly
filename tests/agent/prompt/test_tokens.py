from __future__ import annotations

import unittest

from agent.prompt.tokens import estimate_tokens, truncate_to_tokens


class TokensTest(unittest.TestCase):
    def test_estimate_grows_with_length(self):
        self.assertLess(
            estimate_tokens("hi"),
            estimate_tokens("hi " * 1000),
        )

    def test_truncate_preserves_marker(self):
        out = truncate_to_tokens("x " * 1000, max_tokens=10)
        self.assertIn("[truncated]", out)
        self.assertLess(len(out), len("x " * 1000))

    def test_passthrough_short(self):
        out = truncate_to_tokens("short", max_tokens=100)
        self.assertEqual(out, "short")


if __name__ == "__main__":
    unittest.main()
