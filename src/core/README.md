# `src/core/` — Step 1: Polymarket simulator engine

Pure-Python CLOB matching engine + simulation environment.
**Stateless except for the `OrderBook` / `Simulation` instances passed
in.** No I/O, no DB, no LLM calls — just the market microstructure
that mirrors Polymarket's actual exchange.

| File | Purpose |
|---|---|
| `orderbook.py` | Two-sided CLOB (bids + asks) with price-time priority matching, IOC market orders (v5 fix), self-match prevention (v5 fix), tick-size validation |
| `env.py` | `Simulation` dataclass holding two `OrderBook`s (YES + NO), agent runtimes (cash + reserved + inventory), action handlers (LIMIT / MARKET / SPLIT / MERGE / CANCEL / HOLD), settlement at resolution |

## Public API

```python
from src.core.orderbook import OrderBook, CancelInfo
from src.core.env import (
    Simulation, AgentRuntime, ENV_MAKER_AGENT_ID,
    make_sim, run_simulation, settle, seed_orderbook_liquidity,
    available_cash, available_shares,
)
```

## Design choices, audited

- **Polymarket-spec parity**: ConditionalToken Framework SPLIT/MERGE
  primitives are first-class; taker fee uses `f = C × rate × p ×
  (1−p)` (paper Table 7 / Polymarket fee spec); tick size is
  configurable (default 0.01).
- **No naked shorts**: `LIMIT SELL` requires unreserved inventory of
  the same outcome.
- **No over-commit**: cash / inventory reservations track every
  resting order; canceled orders release the reservation.
- **No artifacts**: `MARKET` orders drop unfilled residuals (v3-v4
  used to rest them at sweep price 1.0 / 0.0 — see
  `docs/V5_VALIDATION.md`).

See `tests/test_core_orderbook.py` (29 cases) and
`tests/test_core_env.py` (24 cases) for the executable contract.
