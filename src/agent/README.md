# `src/agent/` — Step 2: Agent ↔ market interaction

Per-tick LLM-driven decision logic. An "agent" here is a function
mapping `(market_state, agent_state) → Decision`; the simulator
calls `decide()` once per agent per tick.

| File | Purpose |
|---|---|
| `decision.py` | `decide()`, `parse_decision()`, `MarketSnapshot`, `AgentSnapshot`, `Decision` dataclasses; CLOB action schema (LIMIT/MARKET/CANCEL/HOLD/SPLIT/MERGE); JSON-mode prompt; tick rounding |
| `persona.py` | `Persona` dataclass + `build_system_prompt()` template |
| `llm_client.py` | Thin DeepSeek chat-completions wrapper (`call_deepseek`); also used by `src.population.persona_generator` |

## Public API

```python
from src.agent.decision import (
    Decision, MarketSnapshot, AgentSnapshot,
    decide, parse_decision, round_to_tick,
)
from src.agent.persona import Persona, build_system_prompt
from src.agent.llm_client import call_deepseek
```

## v7 changes

- **Hardcoded archetypes deleted** (SkepticalEngineer, LotteryPlayer,
  HerdFollower, MarketMaker). Calibrated agents get `Persona`
  instances built dynamically from real wallet features by
  `src.population.persona_generator`. Roles emerge post-hoc via
  `src.analysis.serd`, not from prompt labels.
- **`call_deepseek` extracted** into its own module so persona
  generation and per-tick decision share one HTTP code path.

## Design

- The Decision JSON schema is enforced by `parse_decision()`. Output
  goes through tick-size rounding before reaching the orderbook,
  preventing `0.555` from being silently rejected.
- The system prompt template (in `persona.py`) is the **only**
  place where natural-language persona text reaches the LLM.

See `tests/test_agent_decision.py` and `tests/test_agent_persona.py`.
