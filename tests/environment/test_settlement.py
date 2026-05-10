from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from typing import Optional

from environment.settlement import settle


@dataclass
class _Persona:
    capital_initial: float


@dataclass
class _Agent:
    agent_id: int
    cash: float = 0.0
    yes_shares: float = 0.0
    no_shares: float = 0.0
    persona: _Persona = field(default_factory=lambda: _Persona(100.0))


@dataclass
class _Sim:
    market_resolved_yes: Optional[int]
    agents: list[_Agent]


class SettleTest(unittest.TestCase):
    def test_unresolved_returns_empty(self):
        sim = _Sim(None, [_Agent(0, cash=50)])
        self.assertEqual(settle(sim), {})

    def test_yes_winner_pays_yes_shares(self):
        sim = _Sim(1, [_Agent(0, cash=50, yes_shares=10, no_shares=20,
                              persona=_Persona(100.0))])
        pnl = settle(sim)
        # Final value: 50 cash + 10 YES * $1 + 20 NO * $0 = 60. PnL = 60 - 100 = -40
        self.assertEqual(pnl[0], -40.0)

    def test_no_winner_pays_no_shares(self):
        sim = _Sim(0, [_Agent(0, cash=50, yes_shares=10, no_shares=20,
                              persona=_Persona(100.0))])
        pnl = settle(sim)
        # Final value: 50 + 10*0 + 20*1 = 70 ; PnL = 70-100 = -30
        self.assertEqual(pnl[0], -30.0)


if __name__ == "__main__":
    unittest.main()
