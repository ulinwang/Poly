"""Map the existing Forum actions into the generic interaction protocol."""
from __future__ import annotations

from typing import Iterable

from agent.multi_agent.protocol import (
    InteractionDelivery,
    InteractionKind,
    InteractionMessage,
    InteractionTranscript,
    InteractionVisibility,
)
from environment.forum import Forum


class ForumInteractionAdapter:
    """Append typed records while leaving Forum as the live state store."""

    def __init__(
        self,
        *,
        run_id: str,
        agent_ids: Iterable[int],
        transcript: InteractionTranscript,
    ) -> None:
        self.run_id = str(run_id)
        self.agent_ids = tuple(sorted(int(agent_id) for agent_id in agent_ids))
        self.transcript = transcript

    def record(self, kind: str, payload: dict) -> tuple[InteractionMessage, ...]:
        if kind == "post":
            return (self._record_post(payload),)
        if kind == "comment":
            return (self._record_comment(payload),)
        if kind == "follow":
            return (self._record_follow(payload),)
        if kind == "read":
            return self._record_reads(payload)
        raise ValueError(f"unsupported forum interaction: {kind}")

    def _public_delivery(self, tick: int) -> InteractionDelivery:
        return InteractionDelivery(
            visibility=InteractionVisibility.PUBLIC,
            recipient_ids=self.agent_ids,
            delivered_at_tick=int(tick),
        )

    def _record_post(self, payload: dict) -> InteractionMessage:
        tick = int(payload["tick"])
        post_id = int(payload["post_id"])
        source = f"forum:post:{post_id}"
        return self.transcript.append(
            run_id=self.run_id,
            tick=tick,
            channel="forum",
            kind=InteractionKind.POST,
            sender_id=int(payload["author_id"]),
            delivery=self._public_delivery(tick),
            content=str(payload.get("content", "")),
            topic="forum",
            correlation_id=source,
            source_ref=source,
            metadata={"post_id": post_id},
        )

    def _record_comment(self, payload: dict) -> InteractionMessage:
        tick = int(payload["tick"])
        post_id = int(payload["post_id"])
        comment_id = int(payload["comment_id"])
        parent = f"forum:post:{post_id}"
        return self.transcript.append(
            run_id=self.run_id,
            tick=tick,
            channel="forum",
            kind=InteractionKind.COMMENT,
            sender_id=int(payload["author_id"]),
            delivery=self._public_delivery(tick),
            content=str(payload.get("content", "")),
            topic=f"post:{post_id}",
            correlation_id=parent,
            source_ref=f"forum:comment:{comment_id}",
            metadata={"post_id": post_id, "comment_id": comment_id},
        )

    def _record_follow(self, payload: dict) -> InteractionMessage:
        tick = int(payload["tick"])
        follower = int(payload["agent_id"])
        target = int(payload["target_id"])
        return self.transcript.append(
            run_id=self.run_id,
            tick=tick,
            channel="forum",
            kind=InteractionKind.FOLLOW,
            sender_id=follower,
            delivery=InteractionDelivery(
                visibility=InteractionVisibility.DIRECT,
                recipient_ids=(target,),
                delivered_at_tick=tick,
            ),
            topic="follow",
            correlation_id=f"forum:follow:{follower}:{target}",
            source_ref=f"forum:follow:{follower}:{target}",
            metadata={"target_id": target},
        )

    def _record_reads(self, payload: dict) -> tuple[InteractionMessage, ...]:
        tick = int(payload["tick"])
        reader_id = int(payload["reader_id"])
        messages: list[InteractionMessage] = []
        for row in payload.get("posts", []):
            post_id = int(row["post_id"])
            followed = bool(row.get("followed"))
            source = f"forum:post:{post_id}"
            messages.append(self.transcript.append(
                run_id=self.run_id,
                tick=tick,
                channel="forum",
                kind=InteractionKind.READ,
                sender_id=int(row["author_id"]),
                delivery=InteractionDelivery(
                    visibility=InteractionVisibility.DIRECT,
                    recipient_ids=(reader_id,),
                    delivered_at_tick=tick,
                    priority=1 if followed else 0,
                ),
                content=str(row.get("content", "")),
                topic=str(payload.get("topic", "")),
                correlation_id=source,
                source_ref=source,
                metadata={
                    "post_id": post_id,
                    "reader_id": reader_id,
                    "followed": followed,
                    "post_tick": int(row.get("tick", tick)),
                },
            ))
        return tuple(messages)


def replay_forum(records: Iterable[dict]) -> Forum:
    """Rebuild Forum state solely from typed transcript records."""
    transcript = InteractionTranscript.from_records(records)
    forum = Forum()
    for message in transcript.messages:
        if message.channel != "forum":
            continue
        if message.kind == InteractionKind.POST:
            post = forum.post(message.sender_id, message.content, message.tick)
            expected = int(message.metadata["post_id"])
            if post.id != expected:
                raise ValueError("forum post ids are not replayable in sequence")
        elif message.kind == InteractionKind.COMMENT:
            comment = forum.comment(
                message.sender_id,
                int(message.metadata["post_id"]),
                message.content,
                message.tick,
            )
            if (
                comment is None
                or comment.id != int(message.metadata["comment_id"])
            ):
                raise ValueError("forum comment cannot be replayed")
        elif message.kind == InteractionKind.FOLLOW:
            forum.follow(message.sender_id, int(message.metadata["target_id"]))
        # READ is a delivery record and does not mutate Forum state.
    return forum
