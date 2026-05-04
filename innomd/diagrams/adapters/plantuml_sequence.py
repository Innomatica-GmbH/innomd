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
from ..ir_sequence import (
    Activation, Block, Message, MessageStyle, Note, NoteSide,
    Participant, SequenceIR,
)


_START_RE = re.compile(r"^\s*@startuml\b", re.I)
_END_RE = re.compile(r"^\s*@enduml\s*$", re.I)
# `participant Alice as "Display name"`  or  `participant Alice as Display`
_PARTICIPANT_RE = re.compile(
    r'^\s*(?:participant|actor|boundary|control|entity|database|collections)\s+'
    r'([A-Za-z_][\w]*)'
    r'(?:\s+as\s+(?:"([^"]+)"|(\S+)))?'
    r'(?:\s+<<[^>]+>>)?'              # optional stereotype <<Person>>
    r'\s*$',
    re.I,
)
# Message: `A -> B : text`. PlantUML allows direction modifiers
# (`-down->`, `-up->`, `-left->`, `-right->`) and bracketed modifiers
# (`-[#red]->`, `-[#red,bold]->`) inside the arrow. The arrow regex is
# kept loose; classification happens in `_classify_arrow` after
# stripping the modifiers.
_ARROW_RE = (
    r"(?:[<>](?:[<>]|/|\\)?)?"      # optional opening shape: <, <<, </, <\
    r"[-.]+"                          # one or more dashes or dots
    r"(?:\[[^\]]*\][-.]*)?"           # optional [bracket] + more line chars
    r"(?:[a-zA-Z]+[-.]*)?"            # optional direction word + more chars
    r"(?:[<>](?:[<>]|/|\\|x|\)|o)?)?" # optional closing shape: >, >>, >\, x, ), o
)
_MSG_RE = re.compile(
    r"^\s*([A-Za-z_][\w]*)\s*"
    rf"({_ARROW_RE})"
    r"\s*([A-Za-z_][\w]*)"
    r"(?:\s*:\s*(.*))?\s*$"
)
_BLOCK_OPEN_RE = re.compile(
    r"^\s*(loop|alt|opt|par|critical|break|group)\b\s*(.*)$", re.I
)
_BLOCK_INNER_RE = re.compile(r"^\s*(?:else|and)\b", re.I)
_BLOCK_END_RE = re.compile(r"^\s*end\s*$", re.I)
_NOTE_INLINE_RE = re.compile(
    r"^\s*(?:note|hnote|rnote)\s+"
    r"(left|right|over)"
    r"(?:\s+of)?"
    r"\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)?)"
    r"\s*:\s*(.*?)\s*$",
    re.I,
)
_NOTE_BLOCK_OPEN_RE = re.compile(
    r"^\s*(?:note|hnote|rnote)\s+(left|right|over)"
    r"(?:\s+of)?\s+([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)?)\s*$",
    re.I,
)
_NOTE_BLOCK_END_RE = re.compile(r"^\s*end\s+(?:note|hnote|rnote)\s*$", re.I)
_ACTIVATE_RE = re.compile(r"^\s*activate\s+([A-Za-z_]\w*)\s*$", re.I)
_DEACTIVATE_RE = re.compile(r"^\s*deactivate\s+([A-Za-z_]\w*)\s*$", re.I)
_SKIP_RE = re.compile(
    r"^\s*(?:destroy|create|autonumber|title|"
    r"skinparam|hide|show|footer|header|"
    r"caption|legend|center|left|right|return|\.\.\.)\b|"
    r"^\s*!",   # any preprocessor directive: !include, !includeurl,
                # !define, !theme, !pragma, etc.
    re.I,
)


def _classify_arrow(arrow: str) -> tuple[MessageStyle, bool] | None:
    """Return (style, reverse) for a PlantUML arrow token, or None.

    `reverse=True` means src/dst should be swapped (the arrow points back
    at the left-hand identifier — e.g. `<-`, `<<--`).
    """
    s = arrow
    # Strip [bracket] modifiers along with one adjacent dash so that
    # `-[#red]->` collapses to `->` (sync), not `-->` (async).
    s = re.sub(r"-?\[[^\]]*\]-?", "-", s)
    # Strip direction keywords with one adjacent dash on each side, so
    # `-down->` collapses to `->`.
    s = re.sub(
        r"-?\b(?:up|down|left|right|u|d|l|r)\b-?",
        "-", s, flags=re.I,
    )
    # Detect reverse direction.
    reverse = s.startswith("<")
    if reverse:
        s = s[1:].rstrip("<")        # drop opening `<` (and any extras)
    s = s.lstrip("<")
    # Map remaining canonical form to style.
    if s in ("->", "->>"):
        return MessageStyle.SYNC, reverse
    if s in ("-->", "-->>"):
        return MessageStyle.ASYNC, reverse
    if s in ("..>", "..>>", "..->"):
        return MessageStyle.DASHED, reverse
    if s in ("--", "..", "-"):
        return MessageStyle.LINE, reverse
    return None


def parse(text: str) -> SequenceIR:
    lines = text.splitlines()
    # @startuml is conventional but not strictly required — accept naked
    # snippets too. Real-world docs sometimes show isolated lines like
    # `Bob -> Alice : hello` without the wrapper.
    body_start = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("'") or s.startswith("/'"):
            continue
        if _START_RE.match(ln):
            body_start = i + 1
        break

    declared: dict[str, Participant] = {}
    discovered: list[str] = []
    messages: list[Message] = []
    blocks: list[Block] = []
    open_blocks: list[tuple[str, str, int]] = []
    notes: list[Note] = []
    activations_open: dict[str, int] = {}    # participant → msg index when activated
    activations: list[Activation] = []
    in_note_block: tuple[NoteSide, tuple[str, ...]] | None = None
    note_block_lines: list[str] = []
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
        if in_note_block is not None:
            if _NOTE_BLOCK_END_RE.match(s):
                side, parts_ = in_note_block
                notes.append(Note(side=side, participants=parts_,
                                  text="\n".join(note_block_lines).strip(),
                                  after_msg=len(messages) - 1))
                in_note_block = None
                note_block_lines = []
            else:
                note_block_lines.append(s)
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
        nbo = _NOTE_BLOCK_OPEN_RE.match(s)
        if nbo:
            side = NoteSide(nbo.group(1).lower())
            parts_ = tuple(p.strip() for p in nbo.group(2).split(","))
            for p in parts_:
                if p not in discovered:
                    discovered.append(p)
            in_note_block = (side, parts_)
            note_block_lines = []
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
            label = (pm.group(2) or pm.group(3) or pid).strip()
            declared[pid] = Participant(id=pid, label=label)
            if pid not in discovered:
                discovered.append(pid)
            continue
        # Message.
        mm = _MSG_RE.match(s)
        if mm:
            src, arrow, dst, text_ = mm.group(1), mm.group(2), mm.group(3), mm.group(4)
            classified = _classify_arrow(arrow)
            if classified is None:
                continue
            style, reverse = classified
            if reverse:
                src, dst = dst, src
            text_ = (text_ or "").strip()
            for who in (src, dst):
                if who not in discovered:
                    discovered.append(who)
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

    # Close any still-open activations at the end.
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
