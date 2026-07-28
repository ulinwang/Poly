from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from agent.decision import Decision
from environment.env import PolyEnv
from runner import runner_stream
from tests._helpers import make_test_population


def test_exhausted_token_budget_skips_future_provider_calls(monkeypatch):
    meta = {
        "condition_id": "condition-1",
        "slug": "budget-regression",
        "question": "Q?",
        "description": "",
        "end_date_iso": "2027-01-01",
        "winning_idx": -1,
    }
    env = PolyEnv(
        market_meta=meta,
        population=make_test_population(1),
        n_ticks=3,
        sim_id="budget-regression",
    )
    obs = env.reset(seed=3)
    env.state.agents[0].token_budget = 5
    provider_calls = []

    def fake_decide(**kwargs):
        provider_calls.append(kwargs)
        return Decision(
            "LIMIT", "YES", "BUY", 0.40, 10.0, "trade", "", 1, "",
            prompt_tokens=3,
            completion_tokens=2,
        )

    monkeypatch.setattr(runner_stream, "decide", fake_decide)
    events = []
    runner_stream._run_tick_loop(
        env=env,
        obs=obs,
        meta=meta,
        priors={"tick_size": 0.01},
        n_ticks=3,
        start_tick=0,
        slug=meta["slug"],
        persona_set="test",
        seed=3,
        temperature=0.0,
        prev_yes_mid=env.state.yes_mid,
        api_key="unused",
        base_url=None,
        model=None,
        settings=SimpleNamespace(DEEPSEEK_TIMEOUT=1),
        on_event=lambda kind, payload: events.append((kind, payload)),
        cancel=None,
        pause=None,
        checkpoint_out=None,
        started_at=dt.datetime.utcnow(),
    )

    agent = env.state.agents[0]
    assert len(provider_calls) == 1
    assert agent.budget_exceeded is True
    assert agent.total_prompt_tokens + agent.total_completion_tokens == 5
    assert [row[3] for row in env.state.actions_log] == ["HOLD", "HOLD", "HOLD"]
    assert sum(kind == "agent_budget_hold" for kind, _ in events) == 2
