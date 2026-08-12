from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from agent.decision import Decision
from agent.multi_agent.scheduler import TickSchedule
from agent.multi_agent.forum_adapter import replay_forum
from environment.env import PolyEnv
from runner import runner_stream
from tests._helpers import make_test_population


META = {
    "condition_id": "condition-scheduler",
    "slug": "scheduler-regression",
    "question": "Does scheduling preserve outcomes?",
    "description": "",
    "end_date_iso": "2027-01-01",
    "winning_idx": -1,
}


class ReverseScheduler:
    def schedule(self, *, tick: int, agent_ids: tuple[int, ...]) -> TickSchedule:
        return TickSchedule(tick, tuple(reversed(agent_ids)), "reverse-test")


class MissingAgentScheduler:
    def schedule(self, *, tick: int, agent_ids: tuple[int, ...]) -> TickSchedule:
        return TickSchedule(tick, agent_ids[:-1], "missing-test")


def _env() -> PolyEnv:
    env = PolyEnv(
        market_meta=META,
        population=make_test_population(3),
        n_ticks=1,
        taker_fee_bps=0.0,
        sim_id="scheduler-regression",
    )
    env.reset(seed=17)
    for agent in env.state.agents:
        agent.yes_shares = 20.0
    return env


def _decision(agent_id: int) -> Decision:
    if agent_id == 0:
        return Decision("LIMIT", "YES", "SELL", 0.40, 4.0, "offer", "", 0, "")
    if agent_id == 1:
        return Decision("LIMIT", "YES", "BUY", 0.50, 5.0, "bid", "", 0, "")
    return Decision("HOLD", "YES", "BUY", 0.50, 0.0, "wait", "", 0, "")


def _run(monkeypatch, scheduler=None):
    env = _env()
    obs = env._observations()
    provider_order: list[int] = []
    events: list[tuple[str, dict]] = []

    def fake_decide(**kwargs):
        agent_id = kwargs["agent"].agent_id
        provider_order.append(agent_id)
        return _decision(agent_id)

    monkeypatch.setattr(runner_stream, "decide", fake_decide)
    runner_stream._run_tick_loop(
        env=env,
        obs=obs,
        meta=META,
        priors={"tick_size": 0.01},
        n_ticks=1,
        start_tick=0,
        slug=META["slug"],
        persona_set="test",
        seed=17,
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
        agent_scheduler=scheduler,
    )
    snapshot = {
        "mids": (env.state.yes_mid, env.state.no_mid),
        "actions": [row[1:12] for row in env.state.actions_log],
        "agents": [
            (agent.agent_id, agent.cash, agent.yes_shares, agent.cash_reserved)
            for agent in env.state.agents
        ],
    }
    return provider_order, events, snapshot


def test_scheduler_changes_decision_call_order_without_changing_market(monkeypatch):
    default_order, default_events, default_snapshot = _run(monkeypatch)
    reverse_order, reverse_events, reverse_snapshot = _run(
        monkeypatch, ReverseScheduler(),
    )

    assert default_order == [0, 1, 2]
    assert reverse_order == [2, 1, 0]
    assert default_snapshot == reverse_snapshot
    default_schedule = next(
        payload for kind, payload in default_events if kind == "agent_schedule"
    )
    reverse_schedule = next(
        payload for kind, payload in reverse_events if kind == "agent_schedule"
    )
    assert default_schedule["scheduler"] == "sequential"
    assert default_schedule["decision_order"] == [0, 1, 2]
    assert reverse_schedule["scheduler"] == "reverse-test"
    assert reverse_schedule["decision_order"] == [2, 1, 0]
    assert reverse_schedule["execution_order"] == "environment_seeded_shuffle"
    agent_scores = [payload for kind, payload in default_events
                    if kind == "agent_scores"]
    run_scores = [payload for kind, payload in default_events
                  if kind == "run_scores"]
    assert len(agent_scores) == 3
    assert all(payload["decision_id"] for payload in agent_scores)
    assert len(run_scores) == 1
    assert all(score["passed"] for score in run_scores[0]["scores"]
               if score["hard"])


def test_runner_persists_and_streams_typed_forum_interactions(monkeypatch):
    env = _env()
    obs = env._observations()
    events: list[tuple[str, dict]] = []

    def fake_decide(**kwargs):
        agent_id = kwargs["agent"].agent_id
        if agent_id == 0:
            post = kwargs["forum"].post(agent_id, "typed evidence", kwargs["tick"])
            kwargs["on_forum_action"]("post", {
                "tick": kwargs["tick"],
                "author_id": agent_id,
                "post_id": post.id,
                "content": post.content,
            })
        elif agent_id == 1:
            feed = kwargs["forum"].get_feed_for(agent_id)
            kwargs["on_forum_action"]("read", {
                "tick": kwargs["tick"],
                "reader_id": agent_id,
                "topic": "typed",
                "posts": [{
                    "tick": post.tick,
                    "post_id": post.id,
                    "author_id": post.author_id,
                    "content": post.content,
                    "followed": False,
                } for post in feed],
            })
        return Decision("HOLD", "YES", "BUY", 0.5, 0.0, "wait", "", 0, "")

    monkeypatch.setattr(runner_stream, "decide", fake_decide)
    runner_stream._run_tick_loop(
        env=env,
        obs=obs,
        meta=META,
        priors={"tick_size": 0.01},
        n_ticks=1,
        start_tick=0,
        slug=META["slug"],
        persona_set="test",
        seed=17,
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

    records = env.state.interaction_transcript.to_records()
    assert [record["kind"] for record in records] == ["post", "read"]
    assert records[0]["sender_id"] == 0
    assert records[0]["delivery"]["recipient_ids"] == (0, 1, 2)
    assert records[1]["sender_id"] == 0
    assert records[1]["delivery"]["recipient_ids"] == (1,)
    assert records[1]["correlation_id"] == "forum:post:0"
    streamed = [payload for kind, payload in events
                if kind == "multi_agent_interaction"]
    assert streamed == records
    assert replay_forum(records).posts == env.state.forum.posts


def test_invalid_scheduler_stops_before_provider_calls(monkeypatch):
    env = _env()
    calls: list[int] = []
    events: list[tuple[str, dict]] = []

    def fake_decide(**kwargs):
        calls.append(kwargs["agent"].agent_id)
        return _decision(kwargs["agent"].agent_id)

    monkeypatch.setattr(runner_stream, "decide", fake_decide)
    runner_stream._run_tick_loop(
        env=env,
        obs=env._observations(),
        meta=META,
        priors={"tick_size": 0.01},
        n_ticks=1,
        start_tick=0,
        slug=META["slug"],
        persona_set="test",
        seed=17,
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
        agent_scheduler=MissingAgentScheduler(),
    )

    assert calls == []
    error = next(payload for kind, payload in events if kind == "error")
    assert error["where"] == "agent_scheduler"
    assert "every agent" in error["message"]
    assert env.state.actions_log == []
