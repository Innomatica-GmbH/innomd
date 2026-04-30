"""PlantUML sequence diagrams (`@startuml … @enduml`) → SequenceIR.

Supported:
    @startuml
    @enduml
    participant X
    participant X as "Long name"
    actor X
    A -> B : text          (sync)
    A --> B : text         (async / dashed return)
    A ->> B : text         (mermaid-style sync, also accepted)
    A -->> B : text        (mermaid-style async, also accepted)
    A -> A : text          (self-message)

Skipped (silent):
    @startuml … (until @enduml is matched)
    note left/right/over of X : text
    activate X / deactivate X
    autonumber
    title text
    skinparam …, !theme, etc.

Block markers (rendered as labelled rules in the output):
    loop / alt / opt / par / critical / break  →  end
"""
from __future__ import annotations

import re

from ..errors import AdapterError
from ..ir_sequence import Block, Message, MessageStyle, Participant, SequenceIR


_START_RE = re.compile(r"^\s*@startuml\b", re.I)
_END_RE = re.compile(r"^\s*@enduml\s*$", re.I)
# `participant Alice as "Display name"`  or  `participant Alice as Display`
_PARTICIPANT_RE = re.compile(
    r'^\s*(?:participant|actor|boundary|control|entity|database|collections)\s+'
    r'([A-Za-z_][\w]*)'
    r'(?:\s+as\s+(?:"([^"]+)"|(.+?)))?\s*$',
    re.I,
)
# Message: `A -> B : text`. Identifiers can be alphanumeric; allow optional
# colon-separated label.
_MSG_RE = re.compile(
    r"^\s*([A-Za-z_][\w]*)\s*"
    r"(-->>|->>|-->|->|\.\.>|\.\.)"
    r"\s*([A-Za-z_][\w]*)"
    r"(?:\s*:\s*(.*))?\s*$"
)
_BLOCK_OPEN_RE = re.compile(
    r"^\s*(loop|alt|opt|par|critical|break|group)\b\s*(.*)$", re.I
)
_BLOCK_INNER_RE = re.compile(r"^\s*(?:else|and)\b", re.I)
_BLOCK_END_RE = re.compile(r"^\s*end\s*$", re.I)
_NOTE_RE = re.compile(r"^\s*note\b|^\s*hnote\b|^\s*rnote\b", re.I)
_SKIP_RE = re.compile(
    r"^\s*(?:activate|deactivate|destroy|create|autonumber|title|"
    r"skinparam|!theme|!include|!define|hide|show|footer|header|"
    r"caption|legend|center|left|right|return|...)\b",
    re.I,
)


_ARROW_TO_STYLE = {
    "->":   MessageStyle.SYNC,
    "->>":  MessageStyle.SYNC,
    "-->":  MessageStyle.ASYNC,
    "-->>": MessageStyle.ASYNC,
    "..>":  MessageStyle.DASHED,
    "..":   MessageStyle.DASHED,
}


def parse(text: str) -> SequenceIR:
    lines = text.splitlines()
    # Find @startuml.
    body_start = -1
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("'") or s.startswith("/'"):
            continue
        if _START_RE.match(ln):
            body_start = i + 1
            break
        raise AdapterError(f"expected '@startuml' header, got: {ln!r}")
    if body_start < 0:
        raise AdapterError("missing @startuml")

    declared: dict[str, Participant] = {}
    discovered: list[str] = []
    messages: list[Message] = []
    blocks: list[Block] = []
    open_blocks: list[tuple[str, str, int]] = []
    saw_end = False

    for raw in lines[body_start:]:
        # PlantUML line comments start with `'` at the start of a line
        # (after whitespace). Apostrophes mid-line (e.g. `[X]'s end`) are
        # NOT comment markers, so we only strip the line if it starts with
        # one — otherwise we keep the line verbatim.
        if raw.lstrip().startswith("'"):
            continue
        s = raw.strip()
        if not s:
            continue
        if _END_RE.match(s):
            saw_end = True
            break
        # Block markers.
        bm = _BLOCK_OPEN_RE.match(s)
        if bm:
            kind = bm.group(1).lower()
            label = bm.group(2).strip()
            open_blocks.append((kind, label, len(messages)))
            continue
        if _BLOCK_END_RE.match(s):
            if open_blocks:
                kind, label, start = open_blocks.pop()
                blocks.append(Block(kind=kind, label=label,
                                    msg_start=start, msg_end=len(messages)))
            continue
        if _BLOCK_INNER_RE.match(s):
            continue
        if _NOTE_RE.match(s) or _SKIP_RE.match(s):
            continue
        # Participant declaration.
        pm = _PARTICIPANT_RE.match(s)
        if pm:
            pid = pm.group(1)
            label = (pm.group(2) or pm.group(3) or pid).strip()
            declared[pid] = Participant(id=pid, label=label)
            if pid not in discovered:
                discovered.append(pid)
            continue
        # Message.
        mm = _MSG_RE.match(s)
        if mm:
            src, arrow, dst, text_ = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
            text_ = (text_ or "").strip()
            for who in (src, dst):
                if who not in discovered:
                    discovered.append(who)
            style = _ARROW_TO_STYLE.get(arrow, MessageStyle.SYNC)
            messages.append(Message(src=src, dst=dst, text=text_, style=style))
            continue
        # Anything else: skip leniently.

    # Close any unbalanced blocks.
    while open_blocks:
        kind, label, start = open_blocks.pop()
        blocks.append(Block(kind=kind, label=label,
                            msg_start=start, msg_end=len(messages)))

    if not discovered or not messages:
        raise AdapterError("no participants or messages found")

    participants_out: list[Participant] = []
    seen: set[str] = set()
    for pid in discovered:
        if pid in seen:
            continue
        seen.add(pid)
        if pid in declared:
            participants_out.append(declared[pid])
        else:
            participants_out.append(Participant(id=pid, label=pid))

    return SequenceIR(
        participants=tuple(participants_out),
        messages=tuple(messages),
        blocks=tuple(blocks),
    )
