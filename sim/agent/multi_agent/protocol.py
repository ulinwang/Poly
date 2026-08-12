"""Typed, replayable records for interactions between simulation agents."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping


PROTOCOL_VERSION = "1"


class InteractionKind(str, Enum):
    POST = "post"
    COMMENT = "comment"
    FOLLOW = "follow"
    READ = "read"


class InteractionVisibility(str, Enum):
    PUBLIC = "public"
    DIRECT = "direct"


@dataclass(frozen=True)
class InteractionBudget:
    """Per-agent, per-tick limits for non-terminal social tools."""

    max_forum_reads: int = 2
    max_social_actions: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.max_forum_reads, int) or isinstance(
            self.max_forum_reads, bool,
        ):
            raise TypeError("max_forum_reads must be an integer")
        if not isinstance(self.max_social_actions, int) or isinstance(
            self.max_social_actions, bool,
        ):
            raise TypeError("max_social_actions must be an integer")
        if self.max_forum_reads < 0 or self.max_social_actions < 0:
            raise ValueError("interaction budgets must be non-negative")


DEFAULT_INTERACTION_BUDGET = InteractionBudget()


@dataclass(frozen=True)
class InteractionDelivery:
    """Who can receive an interaction and how it became visible."""

    visibility: InteractionVisibility
    recipient_ids: tuple[int, ...]
    delivered_at_tick: int
    priority: int = 0


@dataclass(frozen=True)
class InteractionMessage:
    """One immutable entry in the collaboration transcript."""

    message_id: str
    run_id: str
    tick: int
    sequence: int
    channel: str
    kind: InteractionKind
    sender_id: int
    delivery: InteractionDelivery
    content: str = ""
    topic: str = ""
    correlation_id: str = ""
    source_ref: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    protocol_version: str = PROTOCOL_VERSION

    def to_record(self) -> dict[str, Any]:
        record = asdict(self)
        record["kind"] = self.kind.value
        record["delivery"]["visibility"] = self.delivery.visibility.value
        record["metadata"] = dict(self.metadata)
        return record

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> "InteractionMessage":
        delivery = record.get("delivery") or {}
        return cls(
            message_id=str(record["message_id"]),
            run_id=str(record["run_id"]),
            tick=int(record["tick"]),
            sequence=int(record["sequence"]),
            channel=str(record.get("channel", "forum")),
            kind=InteractionKind(str(record["kind"])),
            sender_id=int(record["sender_id"]),
            delivery=InteractionDelivery(
                visibility=InteractionVisibility(str(delivery["visibility"])),
                recipient_ids=tuple(
                    int(x) for x in delivery.get("recipient_ids", ())
                ),
                delivered_at_tick=int(
                    delivery.get("delivered_at_tick", record["tick"])
                ),
                priority=int(delivery.get("priority", 0)),
            ),
            content=str(record.get("content", "")),
            topic=str(record.get("topic", "")),
            correlation_id=str(record.get("correlation_id", "")),
            source_ref=str(record.get("source_ref", "")),
            metadata=dict(record.get("metadata") or {}),
            protocol_version=str(record.get("protocol_version", PROTOCOL_VERSION)),
        )


@dataclass
class InteractionTranscript:
    """Append-only transcript with checkpoint-safe monotonic sequencing."""

    messages: list[InteractionMessage] = field(default_factory=list)
    _next_sequence: int = 0

    def append(
        self,
        *,
        run_id: str,
        tick: int,
        channel: str,
        kind: InteractionKind,
        sender_id: int,
        delivery: InteractionDelivery,
        content: str = "",
        topic: str = "",
        correlation_id: str = "",
        source_ref: str = "",
        metadata: Mapping[str, Any] | None = None,
    ) -> InteractionMessage:
        sequence = self._next_sequence
        message = InteractionMessage(
            message_id=f"{run_id}:interaction:{sequence}",
            run_id=str(run_id),
            tick=int(tick),
            sequence=sequence,
            channel=str(channel),
            kind=kind,
            sender_id=int(sender_id),
            delivery=delivery,
            content=str(content),
            topic=str(topic),
            correlation_id=str(correlation_id),
            source_ref=str(source_ref),
            metadata=dict(metadata or {}),
        )
        self.messages.append(message)
        self._next_sequence += 1
        return message

    def to_records(self) -> list[dict[str, Any]]:
        return [message.to_record() for message in self.messages]

    @classmethod
    def from_records(
        cls, records: Iterable[Mapping[str, Any]],
    ) -> "InteractionTranscript":
        messages = sorted(
            (InteractionMessage.from_record(record) for record in records),
            key=lambda message: message.sequence,
        )
        sequences = [message.sequence for message in messages]
        if len(sequences) != len(set(sequences)):
            raise ValueError("interaction sequence values must be unique")
        transcript = cls(messages=messages)
        transcript._next_sequence = (max(sequences) + 1) if sequences else 0
        return transcript
