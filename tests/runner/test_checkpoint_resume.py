from __future__ import annotations

from agent.decision import Decision
from agent.multi_agent.forum_adapter import ForumInteractionAdapter
from environment.env import PolyEnv
from runner.checkpoint import load_checkpoint, rng_from_state, save_checkpoint
from tests._helpers import make_test_population


MARKET_META = {
    "condition_id": "condition-1",
    "slug": "seeded-regression",
    "question": "Will the seeded regression remain deterministic?",
    "description": "Test market",
    "end_date_iso": "2027-01-01",
    "winning_idx": -1,
}


def _make_env(*, seed: int, n_ticks: int = 4) -> PolyEnv:
    env = PolyEnv(
        market_meta=MARKET_META,
        population=make_test_population(3),
        n_ticks=n_ticks,
        taker_fee_bps=0.0,
        sim_id="seeded-regression",
    )
    env.reset(seed=seed)
    for agent in env.state.agents:
        agent.yes_shares = 20.0
    return env


def _actions() -> dict[int, Decision]:
    return {
        0: Decision("LIMIT", "YES", "SELL", 0.40, 4.0, "offer", "", 0, ""),
        1: Decision("LIMIT", "YES", "BUY", 0.50, 5.0, "bid", "", 0, ""),
        2: Decision("HOLD", "YES", "BUY", 0.50, 0.0, "wait", "", 0, ""),
    }


def _run_ticks(env: PolyEnv, start: int, stop: int) -> None:
    for _ in range(start, stop):
        env.step(_actions())


def _snapshot(env: PolyEnv) -> dict:
    sim = env.state
    return {
        "action_order": [(row[1], row[2], row[3]) for row in sim.actions_log],
        "fills": [
            (row[1], row[2], row[3], row[6], row[7], row[8], row[9], row[10])
            for row in sim.fills_log
        ],
        "agents": [
            (
                agent.agent_id,
                round(agent.cash, 8),
                round(agent.yes_shares, 8),
                round(agent.cash_reserved, 8),
                round(agent.yes_reserved, 8),
            )
            for agent in sim.agents
        ],
        "bids": [
            (order.agent_id, order.price, order.remaining)
            for order in sim.book_yes.bids
        ],
        "asks": [
            (order.agent_id, order.price, order.remaining)
            for order in sim.book_yes.asks
        ],
        "tick": env._tick,
        "rng_state": env._rng.getstate(),
    }


def test_seeded_end_to_end_event_order_and_balances_are_stable():
    first = _make_env(seed=17)
    second = _make_env(seed=17)

    _run_ticks(first, 0, 4)
    _run_ticks(second, 0, 4)

    assert _snapshot(first) == _snapshot(second)
    assert _snapshot(first)["action_order"] == [
        (0, 0, "LIMIT"), (0, 1, "LIMIT"), (0, 2, "HOLD"),
        (1, 0, "LIMIT"), (1, 2, "HOLD"), (1, 1, "LIMIT"),
        (2, 2, "HOLD"), (2, 0, "LIMIT"), (2, 1, "LIMIT"),
        (3, 0, "LIMIT"), (3, 1, "LIMIT"), (3, 2, "HOLD"),
    ]
    assert _snapshot(first)["agents"] == [
        (0, 1008.0, 0.0, 0.0, 0.0),
        (1, 992.0, 40.0, 10.0, 0.0),
        (2, 1000.0, 20.0, 0.0, 0.0),
    ]


def test_checkpoint_round_trip_resumes_with_identical_rng_and_state(tmp_path):
    uninterrupted = _make_env(seed=17)
    _run_ticks(uninterrupted, 0, 4)

    paused = _make_env(seed=17)
    _run_ticks(paused, 0, 2)
    paused.state.evaluation_schedules = [
        {"tick": 0, "decision_order": [0, 1, 2]},
        {"tick": 1, "decision_order": [0, 1, 2]},
    ]
    paused.state.evaluation_beliefs = [(0, 0.55), (1, 0.45)]
    paused.state.evaluation_prompt_versions = ["trade@1:abc123"]
    post = paused.state.forum.post(0, "checkpointed evidence", tick=1)
    ForumInteractionAdapter(
        run_id=paused.state.sim_id,
        agent_ids=(agent.agent_id for agent in paused.state.agents),
        transcript=paused.state.interaction_transcript,
    ).record("post", {
        "tick": 1,
        "author_id": 0,
        "post_id": post.id,
        "content": post.content,
    })
    checkpoint_path = tmp_path / "run.chk"
    save_checkpoint(
        checkpoint_path,
        sim=paused.state,
        rng=paused._rng,
        next_tick=2,
        n_ticks=4,
        slug=MARKET_META["slug"],
        persona_set="test",
        seed=17,
        temperature=0.0,
        market_meta=MARKET_META,
        priors={"taker_fee_bps": 0.0, "tick_size": 0.01},
        prev_yes_mid=paused.state.yes_mid,
    )

    payload = load_checkpoint(checkpoint_path)
    assert payload["sim"].interaction_transcript.to_records() == (
        paused.state.interaction_transcript.to_records()
    )
    assert payload["sim"].interaction_transcript._next_sequence == 1
    assert payload["sim"].evaluation_schedules == paused.state.evaluation_schedules
    assert payload["sim"].evaluation_beliefs == paused.state.evaluation_beliefs
    assert payload["sim"].evaluation_prompt_versions == ["trade@1:abc123"]
    resumed = PolyEnv(
        market_meta=payload["market_meta"],
        population=payload["sim"].agents,
        n_ticks=payload["n_ticks"],
        taker_fee_bps=payload["priors"]["taker_fee_bps"],
        sim_id="seeded-regression",
    )
    resumed.sim = payload["sim"]
    resumed._tick = payload["next_tick"]
    resumed._rng = rng_from_state(payload["rng_state"])
    _run_ticks(resumed, payload["next_tick"], payload["n_ticks"])

    assert payload["next_tick"] == 2
    assert _snapshot(resumed) == _snapshot(uninterrupted)
