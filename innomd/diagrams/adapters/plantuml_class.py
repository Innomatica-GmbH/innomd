"""PlantUML class diagrams (`@startuml … @enduml`) → ClassIR.

Supported:
    @startuml ... @enduml         (mandatory wrapper)
    Animal <|-- Dog                (inheritance)
    A --|> B                       (reverse inheritance)
    A *-- B                        (composition)
    A o-- B                        (aggregation)
    A --> B                        (association)
    A <-- B                        (reverse association)
    A ..> B                        (dependency, dashed)
    A --  B                        (plain link)
    A ..  B                        (dashed link)
    Animal <|-- Dog : extends      (edge label)

    class Foo {                    (class block with members)
      +int field
      -String name
      +method() : int
    }
    interface Bar
    abstract class Baz

    Foo : +int age                 (single-line member declaration,
                                    same as mermaid)

Skipped silently:
    skinparam, hide, show, !theme, namespace blocks, packages, notes,
    annotations (`<<interface>>`), generics in class names.
"""
from __future__ import annotations

import re

from ..errors import AdapterError
from ..ir_class import ClassEdge, ClassEdgeKind, ClassIR, ClassMember, ClassNode


_START_RE = re.compile(r"^\s*@startuml\b", re.I)
_END_RE = re.compile(r"^\s*@enduml\s*$", re.I)
_ID_RE = r"[A-Za-z_][\w]*"

_CLASS_BLOCK_OPEN_RE = re.compile(
    r"^\s*(?:abstract\s+)?(?:class|interface|enum|abstract)\s+"
    r"(" + _ID_RE + r")"
    r"(?:\s*<\s*[^>]+\s*>)?"             # ignore generics like <T>
    r"(?:\s+as\s+\S+)?"
    r"(?:\s+extends\s+\S+)?"
    r"(?:\s+implements\s+\S+)?"
    r"\s*\{?\s*$",
    re.I,
)
# Standalone class declaration (no `{` open).
_CLASS_DECL_RE = re.compile(
    r"^\s*(?:abstract\s+)?(?:class|interface|enum|abstract)\s+"
    r"(" + _ID_RE + r")\s*$",
    re.I,
)
_CLOSE_BRACE_RE = re.compile(r"^\s*\}\s*$")

# Edge connector + optional `: label` at the end.
_EDGE_RE = re.compile(
    r"^\s*(" + _ID_RE + r")\s+"
    r"(<\|--|--\|>|\*--|--\*|o--|--o|<-->|<--|-->|<\.\.|\.\.>|--|\.\.)"
    r"\s+(" + _ID_RE + r")"
    r"(?:\s*:\s*(.+?))?\s*$"
)
# `Foo : member text` (single-line member, mermaid-style; PlantUML accepts this too).
_MEMBER_RE = re.compile(
    r"^\s*(" + _ID_RE + r")\s*:\s*(.+?)\s*$"
)
_SKIP_RE = re.compile(
    r"^\s*(?:skinparam|hide|show|!theme|!include|!define|note\b|namespace\b|"
    r"package\b|left\b|right\b|center\b|footer|header|caption|title|legend|"
    r"end\s+(?:namespace|package|note))\b",
    re.I,
)


_CONNECTOR_TO_EDGE: dict[str, tuple[ClassEdgeKind, bool]] = {
    "<|--":  (ClassEdgeKind.INHERITANCE, False),  # A is parent
    "--|>":  (ClassEdgeKind.INHERITANCE, True),   # B is parent
    "*--":   (ClassEdgeKind.COMPOSITION, False),
    "--*":   (ClassEdgeKind.COMPOSITION, True),
    "o--":   (ClassEdgeKind.AGGREGATION, False),
    "--o":   (ClassEdgeKind.AGGREGATION, True),
    "<-->":  (ClassEdgeKind.BIDIRECTIONAL, False),
    "-->":   (ClassEdgeKind.ASSOCIATION, False),
    "<--":   (ClassEdgeKind.ASSOCIATION, True),
    "..>":   (ClassEdgeKind.DEPENDENCY, False),
    "<..":   (ClassEdgeKind.DEPENDENCY, True),
    "--":    (ClassEdgeKind.LINK, False),
    "..":    (ClassEdgeKind.DASHED_LINK, False),
}


def parse(text: str) -> ClassIR:
    lines = text.splitlines()
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

    members_by_class: dict[str, list[ClassMember]] = {}
    edges: list[ClassEdge] = []
    discovered: list[str] = []
    inside_class: str | None = None        # name of class whose `{` is open

    def remember(cid: str) -> None:
        if cid not in members_by_class:
            members_by_class[cid] = []
            discovered.append(cid)

    for raw in lines[body_start:]:
        if raw.lstrip().startswith("'"):
            continue
        s = raw.strip()
        if not s:
            continue
        if _END_RE.match(s):
            break
        # Inside a class block: every line is a member until `}`.
        if inside_class is not None:
            if _CLOSE_BRACE_RE.match(s):
                inside_class = None
                continue
            # Strip leading visibility markers `+`, `-`, `#`, `~`? Keep as-is.
            members_by_class[inside_class].append(ClassMember(text=s))
            continue
        # Class block opener.
        cm = _CLASS_BLOCK_OPEN_RE.match(s)
        if cm:
            cid = cm.group(1)
            remember(cid)
            if s.rstrip().endswith("{"):
                inside_class = cid
            continue
        cd = _CLASS_DECL_RE.match(s)
        if cd:
            remember(cd.group(1))
            continue
        if _SKIP_RE.match(s):
            continue
        # Edge.
        em = _EDGE_RE.match(s)
        if em:
            src, conn, dst, label = em.group(1), em.group(2), em.group(3), em.group(4)
            spec = _CONNECTOR_TO_EDGE.get(conn)
            if spec is None:
                continue
            kind, swap = spec
            if swap:
                src, dst = dst, src
            remember(src)
            remember(dst)
            edges.append(ClassEdge(src=src, dst=dst, kind=kind,
                                   label=(label.strip() if label else None)))
            continue
        # Single-line member declaration: `Foo : text`.
        mm = _MEMBER_RE.match(s)
        if mm:
            cid, text_ = mm.group(1), mm.group(2)
            remember(cid)
            members_by_class[cid].append(ClassMember(text=text_))
            continue

    if not discovered:
        raise AdapterError("no classes found")

    nodes = tuple(
        ClassNode(id=cid, name=cid, members=tuple(members_by_class[cid]))
        for cid in discovered
    )
    return ClassIR(nodes=nodes, edges=tuple(edges))
