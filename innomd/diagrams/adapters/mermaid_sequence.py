"""Mermaid sequenceDiagram subset → SequenceIR.

Supported:
    sequenceDiagram
    participant X
    participant X as Long Name
    A->>B: text       (sync arrow)
    A-->>B: text      (async arrow)
    A->B: text        (no arrowhead, solid)
    A-->B: text       (no arrowhead, dashed)
    A->>A: text       (self-message)

Skipped (rendered as plain inner messages):
    loop X ... end
    alt X / else X / end
    opt X ... end
    par X / and X / end

Skipped silently:
    Note left/right/over of X: text
    activate / deactivate
    autonumber
    title
"""
from __future__ import annotations

import re

from ..errors import AdapterError
from ..ir_sequence import (
    Activation, Block, Message, MessageStyle, Note, NoteSide,
    Participant, SequenceIR,
)


_HEADER_RE = re.compile(r"^\s*sequenceDiagram\s*$", re.I)
_PARTICIPANT_RE = re.compile(
    r"^\s*(?:participant|actor)\s+(\S+)(?:\s+as\s+(.+?))?\s*$", re.I
)
# Message: SRC ARROW DST : TEXT
# Arrows (longest first):  -->>, -->,  ->>, ->, ..>>, ..>
_MSG_RE = re.compile(
    r"^\s*(\S+?)\s*"
    r"(-->>|-->|->>|->|--x|-x|--\)|-\))"
    r"\s*(\S+?)\s*"
    r"(?::\s*(.*))?\s*$"
)
_BLOCK_OPEN_RE = re.compile(
    r"^\s*(loop|alt|opt|par|critical|break)\b\s*(.*)$", re.I
)
_BLOCK_INNER_RE = re.compile(r"^\s*(?:else|and|option)\b", re.I)
_BLOCK_END_RE = re.compile(r"^\s*end\s*$", re.I)
_NOTE_INLINE_RE = re.compile(
    r"^\s*Note\s+"
    r"(left|right|over)"
    r"(?:\s+of)?"
    r"\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)?)"
    r"\s*:\s*(.*?)\s*$",
    re.I,
)
_ACTIVATE_RE = re.compile(r"^\s*activate\s+([A-Za-z_]\w*)\s*$", re.I)
_DEACTIVATE_RE = re.compile(r"^\s*deactivate\s+([A-Za-z_]\w*)\s*$", re.I)
_SKIP_RE = re.compile(r"^\s*(?:autonumber|title|link)\b", re.I)


_ARROW_TO_STYLE = {
    "->>": MessageStyle.SYNC,
    "-->>": MessageStyle.ASYNC,
    "->":  MessageStyle.LINE,
    "-->": MessageStyle.DASHED,
    # Mermaid also has -x / --x for "lost" messages and -) / --) for async
    # open-ended; we map them to SYNC/ASYNC for now.
    "-x":  MessageStyle.SYNC,
    "--x": MessageStyle.ASYNC,
    "-)":  MessageStyle.SYNC,
    "--)": MessageStyle.ASYNC,
}


def parse(text: str) -> SequenceIR:
    lines = text.splitlines()
    # Find header.
    body_start = 0
    found = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("%%"):
            continue
        if _HEADER_RE.match(ln):
            body_start = i + 1
            found = True
            break
        raise AdapterError(f"expected 'sequenceDiagram' header, got: {ln!r}")
    if not found:
        raise AdapterError("empty diagram")

    declared: dict[str, Participant] = {}    # explicit `participant` lines
    discovered: list[str] = []               # order of first appearance
    messages: list[Message] = []
    blocks: list[Block] = []
    open_blocks: list[tuple[str, str, int]] = []   # (kind, label, msg_start_idx)
    notes: list[Note] = []
    activations_open: dict[str, int] = {}
    activations: list[Activation] = []

    for raw in lines[body_start:]:
        s = raw.split("%%", 1)[0].strip()
        if not s:
            continue
        # Block start: push onto stack.
        bm = _BLOCK_OPEN_RE.match(s)
        if bm:
            kind = bm.group(1).lower()
            label = bm.group(2).strip()
            open_blocks.append((kind, label, len(messages)))
            continue
        # Block end: pop the stack.
        if _BLOCK_END_RE.match(s):
            if open_blocks:
                kind, label, start = open_blocks.pop()
                blocks.append(Block(kind=kind, label=label,
                                    msg_start=start, msg_end=len(messages)))
            continue
        # `else` / `and` / `option` inside alt/par — skip silently for now.
        if _BLOCK_INNER_RE.match(s):
            continue
        nm = _NOTE_INLINE_RE.match(s)
        if nm:
            side = NoteSide(nm.group(1).lower())
            parts_ = tuple(p.strip() for p in nm.group(2).split(","))
            for p in parts_:
                if p not in discovered:
                    discovered.append(p)
            notes.append(Note(side=side, participants=parts_,
                              text=nm.group(3).strip(),
                              after_msg=len(messages) - 1))
            continue
        am = _ACTIVATE_RE.match(s)
        if am:
            who = am.group(1)
            if who not in discovered:
                discovered.append(who)
            activations_open[who] = len(messages)
            continue
        dm = _DEACTIVATE_RE.match(s)
        if dm:
            who = dm.group(1)
            start = activations_open.pop(who, None)
            if start is not None:
                activations.append(Activation(participant=who,
                                              msg_start=start,
                                              msg_end=len(messages) - 1))
            continue
        if _SKIP_RE.match(s):
            continue
        # Participant declaration.
        pm = _PARTICIPANT_RE.match(s)
        if pm:
            pid = pm.group(1)
            label = (pm.group(2) or pid).strip()
            declared[pid] = Participant(id=pid, label=label)
            if pid not in discovered:
                discovered.append(pid)
            continue
        # Message line.
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
        # Anything else is unsupported syntax — be lenient and skip.
        # (We don't raise here because real-world sequence diagrams have
        # many small directives we don't model yet.)

    # Final participant list: declared ones first (with their nice labels),
    # then auto-discovered ones in order of first appearance.
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

    if not participants_out:
        raise AdapterError("no participants found")
    if not messages:
        raise AdapterError("no messages found")

    # Close any blocks that were never explicitly closed (lenient parsing).
    while open_blocks:
        kind, label, start = open_blocks.pop()
        blocks.append(Block(kind=kind, label=label,
                            msg_start=start, msg_end=len(messages)))

    for who, start in activations_open.items():
        activations.append(Activation(participant=who, msg_start=start,
                                      msg_end=len(messages) - 1))

    return SequenceIR(
        participants=tuple(participants_out),
        messages=tuple(messages),
        blocks=tuple(blocks),
        activations=tuple(activations),
        notes=tuple(notes),
    )
