"""Mermaid classDiagram subset → ClassIR.

Supported edges (longest-prefix order):
    A <|-- B     B inherits from A
    A --|> B     A inherits from B
    A *-- B      A composed of B
    A --* B      B composed of A
    A o-- B      A aggregates B
    A --o B      B aggregates A
    A <--> B     bidirectional
    A --> B      A → B  (association)
    A <-- B      B → A
    A ..> B      A → B  dashed (dependency)
    A <.. B      B → A  dashed
    A ..  B      dashed link (no arrow)
    A --  B      plain link (no arrow)

Members:
    ClassName : member text
    (everything after the colon becomes one member line)

Skipped (not yet supported):
    class block syntax `class Foo { ... }`
    namespace declarations
    annotations  `<<interface>>`
"""
from __future__ import annotations

import re

from ..errors import AdapterError
from ..ir_class import ClassEdge, ClassEdgeKind, ClassIR, ClassMember, ClassNode


_HEADER_RE = re.compile(r"^\s*classDiagram(?:-v\d+)?\s*$", re.I)
_ID_RE = r"[A-Za-z_][A-Za-z0-9_]*"

# (source-shape, line-style, target-shape) → kind, plus arrow-style flag.
# We parse the connector by splitting around `--` or `..` and inspecting
# what's on each side.
_CONNECTOR_RE = re.compile(
    r"^\s*("                # 1: connector
    r"<\|--|--\|>|"
    r"\*--|--\*|"
    r"o--|--o|"
    r"<-->|"
    r"<--|-->|"
    r"<\.\.|\.\.>|"
    r"--|\.\."
    r")\s*$"
)

_EDGE_LINE_RE = re.compile(
    r"^\s*(" + _ID_RE + r")\s+"             # 1: src
    r"(<\|--|--\|>|\*--|--\*|o--|--o|<-->|<--|-->|<\.\.|\.\.>|--|\.\.)"  # 2: connector
    r"\s+(" + _ID_RE + r")"                  # 3: dst
    r"(?:\s*:\s*(.*))?\s*$"                  # 4: optional label
)

# Member line:  ClassName : member text
_MEMBER_RE = re.compile(
    r"^\s*(" + _ID_RE + r")\s*:\s*(.+?)\s*$"
)


_CONNECTOR_TO_EDGE: dict[str, tuple[ClassEdgeKind, bool]] = {
    # connector → (kind, swap_src_dst)
    # IR convention: src is the "top" / "whole" / "parent" / source-of-arrow.
    # So for inheritance the parent is src; for composition/aggregation the
    # whole is src; for plain associations the source-of-arrow is src.
    "<|--":  (ClassEdgeKind.INHERITANCE, False),  # `A <|-- B`: A is parent → src=A
    "--|>":  (ClassEdgeKind.INHERITANCE, True),   # `A --|> B`: B is parent → src=B
    "*--":   (ClassEdgeKind.COMPOSITION, False),  # whole=A
    "--*":   (ClassEdgeKind.COMPOSITION, True),   # whole=B
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
        raise AdapterError(f"expected 'classDiagram' header, got: {ln!r}")
    if not found:
        raise AdapterError("empty diagram")

    members_by_class: dict[str, list[ClassMember]] = {}
    edges: list[ClassEdge] = []
    discovered: list[str] = []

    def remember(cid: str) -> None:
        if cid not in members_by_class:
            members_by_class[cid] = []
            discovered.append(cid)

    for raw in lines[body_start:]:
        s = raw.split("%%", 1)[0].strip()
        if not s:
            continue
        # Try edge first (more constrained pattern).
        em = _EDGE_LINE_RE.match(s)
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
        # Member declaration.
        mm = _MEMBER_RE.match(s)
        if mm:
            cid, text_ = mm.group(1), mm.group(2)
            remember(cid)
            members_by_class[cid].append(ClassMember(text=text_))
            continue
        # Anything else: skip leniently. Real-world classDiagrams have
        # many directives we don't model (annotations, namespaces, etc.).

    if not discovered:
        raise AdapterError("no classes found")

    nodes = tuple(
        ClassNode(id=cid, name=cid, members=tuple(members_by_class[cid]))
        for cid in discovered
    )
    return ClassIR(nodes=nodes, edges=tuple(edges))
