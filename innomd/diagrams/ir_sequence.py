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
class Activation:
    """A range of messages during which a participant is "active".

    PlantUML / mermaid mark this with `activate X` / `deactivate X`.
    Visually rendered as a thin vertical bar overlaid on the lifeline
    between the activation start and end.
    """
    participant: str
    msg_start: int      # message index AFTER which the activation starts
    msg_end: int        # message index AFTER which it ends (inclusive of last)


class NoteSide(Enum):
    LEFT = "left"
    RIGHT = "right"
    OVER = "over"        # spans one or more lifelines


@dataclass(frozen=True)
class Note:
    """An annotation tied to a participant (or pair) at a position in the
    message stream.

    `participants` is a tuple of one or two participant ids (one for
    left/right, one or two for over). `after_msg` is the index AFTER
    which the note appears (-1 = before the first message).
    """
    side: NoteSide
    participants: tuple[str, ...]
    text: str
    after_msg: int


@dataclass(frozen=True)
class SequenceIR:
    participants: tuple[Participant, ...]
    messages: tuple[Message, ...]
    blocks: tuple[Block, ...] = ()
    activations: tuple[Activation, ...] = ()
    notes: tuple[Note, ...] = ()
