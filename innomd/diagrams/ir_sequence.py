"""IR for sequence diagrams: lifelines + time-ordered messages.

Format-agnostic — populated by mermaid (and later PlantUML) adapters.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MessageStyle(Enum):
    SYNC = "sync"          # solid arrow `->>`
    ASYNC = "async"        # dashed arrow `-->>`
    LINE = "line"          # plain solid line `->` no arrowhead
    DASHED = "dashed"      # plain dashed `-->` no arrowhead


@dataclass(frozen=True)
class Participant:
    id: str                # used in messages
    label: str             # display name


@dataclass(frozen=True)
class Message:
    src: str               # participant id
    dst: str
    text: str              # message label
    style: MessageStyle = MessageStyle.SYNC


@dataclass(frozen=True)
class Block:
    """A wrapper around a contiguous range of messages.

    `kind` is the keyword (`loop`, `alt`, `opt`, `par`, `critical`,
    `break`); `label` is the descriptive text after it. `msg_start` is
    inclusive, `msg_end` exclusive — both index into `SequenceIR.messages`.
    """
    kind: str
    label: str
    msg_start: int
    msg_end: int


@dataclass(frozen=True)
class SequenceIR:
    participants: tuple[Participant, ...]
    messages: tuple[Message, ...]
    blocks: tuple[Block, ...] = ()
