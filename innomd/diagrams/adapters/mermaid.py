"""Mermaid flowchart subset → GraphIR.

Supported:
    graph|flowchart [TD|LR|BT|RL]
    A                    -- bare id, default rect
    A[Text]              -- rect
    B(Text)              -- round
    B([Text])            -- stadium
    C((Text))            -- circle
    D{Text}              -- diamond
    "quoted with spaces" -- inside any of the bracket forms
Edges:
    A --> B
    A --- B              (solid, no arrow)
    A -.-> B             (dashed)
    A ==> B              (thick)
    A -- label --> B
    A -->|label| B

Anything outside this subset raises AdapterError; the caller falls back
to rendering the original code block.
"""
from __future__ import annotations

import re

from ..errors import AdapterError
from ..ir import ArrowStyle, Direction, Edge, EdgeStyle, GraphIR, Node, NodeShape


_HEADER_RE = re.compile(r"^\s*(?:graph|flowchart)\s+([A-Za-z]{2})\s*;?\s*$")

# A node "atom": either bare ID or ID followed by a shape-bracketed label.
# Shapes (longest-first ordering matters for the regex):
#   ((text)) circle
#   ([text]) stadium
#   (text)   round
#   [text]   rect
#   {text}   diamond
# Quoted labels: any "..." inside the brackets keep their content verbatim.
_ID_RE = r"[A-Za-z_][A-Za-z0-9_]*"

# Each entry: (opener, [(closer, shape), ...], strip_leading_trailing_slashes)
# When an opener admits multiple closers (e.g. ``[/...]/`` and ``[/...\]``),
# we pick whichever closer appears earliest in the input — that's the
# unambiguous choice mermaid itself makes.
# Order of openers matters: longer/more-specific openers must come before
# shorter ones that share a prefix, so ``(((`` is tested before ``((``.
_SHAPE_DEFS: tuple[tuple[str, tuple[tuple[str, NodeShape], ...], bool], ...] = (
    ("(((", ((")))",   NodeShape.CIRCLE),),         False),  # double-circle (stop)
    ("((",  (("))",    NodeShape.CIRCLE),),         False),  # circle
    ("([",  (("])",    NodeShape.STADIUM),),        False),  # stadium / pill
    ("[(",  ((")]",    NodeShape.CIRCLE),),         False),  # cylinder / database → circle
    ("[[",  (("]]",    NodeShape.RECT),),           False),  # subroutine → rect
    ("[/",  (("/]",    NodeShape.PARALLELOGRAM),
             ("\\]",   NodeShape.TRAPEZOID)),       True),   # right-lean parallelogram OR bottom-wider trapezoid
    ("[\\", (("\\]",   NodeShape.PARALLELOGRAM_ALT),
             ("/]",    NodeShape.TRAPEZOID_INV)),   True),   # left-lean parallelogram OR top-wider trapezoid
    ("(",   ((")",     NodeShape.ROUND),),          False),
    ("[",   (("]",     NodeShape.RECT),),           False),
    ("{{",  (("}}",    NodeShape.HEXAGON),),        False),  # hexagon `{{ }}`
    ("{",   (("}",     NodeShape.DIAMOND),),        False),  # decision diamond
    (">",   (("]",     NodeShape.RECT),),           True),   # asymmetric flag → rect
)


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def _consume_node(line: str, pos: int) -> tuple[Node | None, str, int]:
    """Read a node atom starting at line[pos]. Returns (Node|None, id, end_pos).

    Returns Node=None when the atom is just a bare id (caller decides whether
    to treat it as an inline definition or a reference to an existing node).
    """
    m = re.match(_ID_RE, line[pos:])
    if not m:
        raise AdapterError(f"expected node id at column {pos + 1}: {line!r}")
    nid = m.group(0)
    pos += len(nid)
    rest = line[pos:]
    for opener, closer_specs, strip_slashes in _SHAPE_DEFS:
        if not rest.startswith(opener):
            continue
        inner_start = pos + len(opener)
        # Pick the closer that appears earliest in the input — that is the
        # unambiguous match, mirroring mermaid's behavior.
        best: tuple[int, str, NodeShape] | None = None
        for closer, shape in closer_specs:
            idx = line.find(closer, inner_start)
            if idx == -1:
                continue
            if best is None or idx < best[0]:
                best = (idx, closer, shape)
        if best is None:
            raise AdapterError(
                f"unclosed {opener!r} for node {nid!r}: {line!r}"
            )
        close_idx, closer, shape = best
        inner = line[inner_start:close_idx]
        if strip_slashes:
            # Leading/trailing / or \ inside `[]` denote parallelogram or
            # trapezoid shape variants — syntax, not visible label.
            if inner.startswith(("/", "\\")):
                inner = inner[1:]
            if inner.endswith(("/", "\\")):
                inner = inner[:-1]
        label = _strip_quotes(inner)
        return Node(id=nid, label=label, shape=shape), nid, close_idx + len(closer)
    return None, nid, pos


# Edge tokens (ordered longest-first to avoid prefix collisions).
# Each entry: (regex, EdgeStyle, ArrowStyle, has_arrow_glyph_before_label?).
# We split label handling into two flavors:
#   inline:    A -- label --> B   or  A -. label .-> B  or A == label ==> B
#   piped:     A --> B|label|     -- mermaid form is A -->|label| B
_EDGE_PATTERNS: tuple[tuple[re.Pattern[str], EdgeStyle, ArrowStyle], ...] = (
    # thick with arrow:    ==>   or with label   == lbl ==>
    (re.compile(r"\s*==(?:[ \t]+([^=\n|]*?)[ \t]+==)?\s*>\s*"), EdgeStyle.THICK,  ArrowStyle.END),
    # dashed with arrow:   -.->  or with label   -. lbl .->
    (re.compile(r"\s*-\.(?:[ \t]+([^.\n|]*?)[ \t]+\.)?-\s*>\s*"), EdgeStyle.DASHED, ArrowStyle.END),
    # solid with arrow + inline label:  -- label -->
    (re.compile(r"\s*--[ \t]+([^-\n|][^-\n|]*?)[ \t]+--\s*>\s*"), EdgeStyle.SOLID,  ArrowStyle.END),
    # solid with arrow:    -->
    (re.compile(r"\s*--+\s*>\s*"),                                EdgeStyle.SOLID,  ArrowStyle.END),
    # solid no arrow:      ---
    (re.compile(r"\s*---+\s*"),                                   EdgeStyle.SOLID,  ArrowStyle.NONE),
)


def _consume_edge(line: str, pos: int) -> tuple[EdgeStyle, ArrowStyle, str | None, int] | None:
    """If an edge connector starts at line[pos], consume it.

    Returns (style, arrow, label, end_pos) or None.
    """
    for pat, style, arrow in _EDGE_PATTERNS:
        m = pat.match(line, pos)
        if m:
            label = None
            if m.lastindex:
                grp = m.group(1)
                if grp is not None:
                    label = grp.strip()
            return style, arrow, label, m.end()
    return None


_PIPE_LABEL_RE = re.compile(r"\s*\|([^|\n]*)\|\s*")


def _skip_frontmatter(lines: list[str], start: int) -> int:
    """If a YAML frontmatter block starts at `start`, return the index just
    after its closing `---`. Otherwise return `start` unchanged.

    Mermaid v10+ wraps optional config in a `---\\n...\\n---` block:

        ---
        title: My diagram
        config:
          flowchart:
            htmlLabels: false
        ---
        flowchart TD
          A --> B
    """
    # Find first non-blank, non-comment line.
    i = start
    while i < len(lines):
        s = lines[i].strip()
        if s and not s.startswith("%%"):
            break
        i += 1
    if i >= len(lines) or lines[i].strip() != "---":
        return start
    # Consume until matching closing ---.
    j = i + 1
    while j < len(lines):
        if lines[j].strip() == "---":
            return j + 1
        j += 1
    # Unclosed frontmatter — treat as no frontmatter (caller will fail at
    # the header check) rather than swallowing the whole document.
    return start


def parse(text: str) -> GraphIR:
    """Parse a mermaid flowchart string into a GraphIR.

    Raises AdapterError on any unsupported construct so the caller can fall back.
    """
    lines = [ln for ln in text.splitlines()]
    direction: Direction | None = None

    # Skip an optional YAML frontmatter block, then find the header.
    body_start = _skip_frontmatter(lines, 0)
    for i, ln in enumerate(lines[body_start:], start=body_start):
        stripped = ln.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        m = _HEADER_RE.match(ln)
        if not m:
            raise AdapterError(
                f"expected 'graph TD/LR/BT/RL' or 'flowchart ...' header, got: {ln!r}"
            )
        try:
            direction = Direction(m.group(1).upper())
        except ValueError:
            raise AdapterError(f"unknown direction {m.group(1)!r}")
        body_start = i + 1
        break

    if direction is None:
        raise AdapterError("empty diagram")

    nodes_by_id: dict[str, Node] = {}
    edges: list[Edge] = []

    def remember(node: Node | None, nid: str) -> None:
        if node is not None:
            # Most recent inline definition wins; mermaid behaves the same way.
            nodes_by_id[nid] = node
        elif nid not in nodes_by_id:
            nodes_by_id[nid] = Node(id=nid, label=nid, shape=NodeShape.RECT)

    for raw in lines[body_start:]:
        line = raw.split("%%", 1)[0].rstrip()  # strip mermaid comments
        if not line.strip():
            continue

        pos = 0
        # leading whitespace
        while pos < len(line) and line[pos] in " \t":
            pos += 1
        if pos >= len(line):
            continue

        # Read the first node.
        first_node, first_id, pos = _consume_node(line, pos)
        remember(first_node, first_id)
        prev_id = first_id

        # Then zero or more edge → node sequences.
        while pos < len(line) and line[pos] in " \t-=.<>|":
            edge = _consume_edge(line, pos)
            if edge is None:
                # Allow trailing semicolon or whitespace.
                rest = line[pos:].strip()
                if rest in ("", ";"):
                    break
                raise AdapterError(f"unexpected characters near col {pos + 1}: {line!r}")
            style, arrow, label, pos = edge

            # Optional pipe label after arrow:  --> |label|
            pm = _PIPE_LABEL_RE.match(line, pos)
            if pm and label is None:
                label = pm.group(1).strip() or None
                pos = pm.end()

            # Skip whitespace
            while pos < len(line) and line[pos] in " \t":
                pos += 1
            if pos >= len(line):
                raise AdapterError(f"edge missing target node: {line!r}")

            next_node, next_id, pos = _consume_node(line, pos)
            remember(next_node, next_id)
            edges.append(Edge(src=prev_id, dst=next_id, label=label,
                              style=style, arrow=arrow))
            prev_id = next_id

            # Allow trailing whitespace / semicolon
            while pos < len(line) and line[pos] in " \t":
                pos += 1
            if pos < len(line) and line[pos] == ";":
                pos += 1
                break

    # Preserve insertion order of nodes for deterministic layout.
    nodes_tuple = tuple(nodes_by_id.values())
    return GraphIR(direction=direction, nodes=nodes_tuple, edges=tuple(edges))
