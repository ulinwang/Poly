from __future__ import annotations

import pickle

import pytest

from agent.multi_agent.forum_adapter import ForumInteractionAdapter, replay_forum
from agent.multi_agent.protocol import (
    InteractionBudget,
    InteractionKind,
    InteractionTranscript,
    InteractionVisibility,
)
from agent.multi_agent.scheduler import (
    SequentialAgentScheduler,
    TickSchedule,
    validate_schedule,
)
from environment.forum import Forum


def test_sequential_schedule_preserves_order_and_validation_is_strict():
    scheduler = SequentialAgentScheduler()
    schedule = scheduler.schedule(tick=4, agent_ids=(7, 2, 9))

    assert schedule.decision_order == (7, 2, 9)
    assert validate_schedule(
        schedule, (7, 2, 9), expected_tick=4,
    ) == schedule

    with pytest.raises(ValueError, match="duplicate"):
        validate_schedule(
            TickSchedule(4, (7, 7, 9), "broken"),
            (7, 2, 9),
            expected_tick=4,
        )
    with pytest.raises(ValueError, match="every agent"):
        validate_schedule(
            TickSchedule(4, (7, 2), "broken"),
            (7, 2, 9),
            expected_tick=4,
        )
    with pytest.raises(ValueError, match="requested tick"):
        validate_schedule(
            TickSchedule(3, (7, 2, 9), "broken"),
            (7, 2, 9),
            expected_tick=4,
        )


def test_forum_adapter_round_trip_rebuilds_state_and_delivery_history():
    forum = Forum()
    transcript = InteractionTranscript()
    adapter = ForumInteractionAdapter(
        run_id="sim-social",
        agent_ids=(0, 1, 2),
        transcript=transcript,
    )

    post = forum.post(0, "Evidence favors YES", tick=0)
    adapter.record("post", {
        "tick": 0,
        "author_id": 0,
        "post_id": post.id,
        "content": post.content,
    })
    comment = forum.comment(1, post.id, "I agree", tick=1)
    assert comment is not None
    adapter.record("comment", {
        "tick": 1,
        "author_id": 1,
        "post_id": post.id,
        "comment_id": comment.id,
        "content": comment.content,
    })
    assert forum.follow(2, 0) is True
    adapter.record("follow", {
        "tick": 1,
        "agent_id": 2,
        "target_id": 0,
    })
    adapter.record("read", {
        "tick": 2,
        "reader_id": 2,
        "topic": "evidence",
        "posts": [{
            "tick": post.tick,
            "post_id": post.id,
            "author_id": post.author_id,
            "content": post.content,
            "followed": True,
        }],
    })

    assert [message.sequence for message in transcript.messages] == [0, 1, 2, 3]
    assert [message.kind for message in transcript.messages] == [
        InteractionKind.POST,
        InteractionKind.COMMENT,
        InteractionKind.FOLLOW,
        InteractionKind.READ,
    ]
    read = transcript.messages[-1]
    assert transcript.messages[0].correlation_id == "forum:post:0"
    assert read.sender_id == 0
    assert read.delivery.recipient_ids == (2,)
    assert read.delivery.visibility == InteractionVisibility.DIRECT
    assert read.delivery.priority == 1
    assert read.correlation_id == "forum:post:0"

    records = transcript.to_records()
    restored = InteractionTranscript.from_records(records)
    assert restored.to_records() == records
    assert pickle.loads(pickle.dumps(transcript)).to_records() == records

    replayed = replay_forum(records)
    assert replayed.posts == forum.posts
    assert replayed.comments == forum.comments
    assert replayed.follows == forum.follows


def test_transcript_rejects_duplicate_sequences():
    transcript = InteractionTranscript()
    adapter = ForumInteractionAdapter(
        run_id="sim-duplicate",
        agent_ids=(0, 1),
        transcript=transcript,
    )
    adapter.record("follow", {"tick": 0, "agent_id": 0, "target_id": 1})
    records = transcript.to_records()

    with pytest.raises(ValueError, match="unique"):
        InteractionTranscript.from_records(records + records)


def test_interaction_budget_requires_non_negative_integers():
    with pytest.raises(ValueError, match="non-negative"):
        InteractionBudget(max_forum_reads=-1)
    with pytest.raises(TypeError, match="integer"):
        InteractionBudget(max_social_actions=1.5)  # type: ignore[arg-type]
