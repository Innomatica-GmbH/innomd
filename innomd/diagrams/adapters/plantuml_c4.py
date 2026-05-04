"""C4-PlantUML macro syntax → GraphIR.

C4-PlantUML is a heavy `!include`-based DSL on top of PlantUML, used in
the wild for architecture diagrams. The official `!include`d library
expands macros like ``Person(alias, "label", "desc")`` into raw
PlantUML primitives at render time. We can't (and don't want to)
resolve the includes, but the macro vocabulary is small and fixed
enough to parse directly into a `GraphIR` and render via our flowchart
renderer.

Supported macros:
    Person(alias, "label" [, "description"])           → round node
    Person_Ext(alias, "label" [, "description"])
    System(alias, "label" [, "description"])           → rect
    System_Ext(alias, "label" [, "description"])
    SystemDb(alias, "label" [, ...])                   → cylinder
    SystemQueue(alias, "label" [, ...])                → stadium
    Container(alias, "label", "tech" [, "description"]) → rect
    ContainerDb(alias, "label", "tech" [, ...])        → cylinder
    ContainerQueue(alias, "label", "tech" [, ...])     → stadium
    Component(alias, "label", "tech" [, ...])          → rect
    ComponentDb / ComponentQueue                        → cylinder / stadium
    Boundary, System_Boundary, Container_Boundary,
        Enterprise_Boundary(alias, "label") { ... }    → flattened, ignored

    Rel(from, to, "label" [, "tech"])                  → edge
    Rel_U/D/L/R/Up/Down/Left/Right(...)                → directional edge
    Rel_Back(from, to, ...)                            → reverse edge
    BiRel(from, to, ...)                               → bidirectional
    Lay_U/D/L/R(from, to)                              → layout-only edge (skipped)

Skipped silently:
    !include, !define, !theme, AddElementTag, AddRelTag, AddPersonTag,
    AddContainerTag, AddBoundaryTag, AddProperty, SetPropertyHeader,
    WithoutPropertyHeader, UpdateElementStyle, UpdateRelStyle,
    UpdateBoundaryStyle, LAYOUT_*, hide stereotype, left header, …
"""
from __future__ import annotations

import re

from ..errors import AdapterError
from ..ir import ArrowStyle, Direction, Edge, EdgeStyle, GraphIR, Node, NodeShape


_START_RE = re.compile(r"^\s*@startuml\b", re.I)
_END_RE = re.compile(r"^\s*@enduml\s*$", re.I)
_DIRECTION_RE = re.compile(
    r"^\s*(?:(top|left|right|bottom)\s+to\s+(top|left|right|bottom))\s+direction\s*$",
    re.I,
)

# Macro call: NAME(arg1, arg2, ...). Args are comma-separated and may be
# quoted strings (with optional escaped quotes). We split args manually
# to handle commas inside quotes.
_MACRO_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\((.*)\)\s*\{?\s*$")

# Plain PlantUML component-primitive declarations:
#   rectangle MyRect <<Stereotype>>
#   frame "Name" as alias <<Stereotype>>
#   interface IFoo as ifoo <<...>>
#   component Cmp <<...>>
_PRIMITIVE_KEYWORDS = (
    "rectangle", "frame", "interface", "component", "database", "queue",
    "actor", "cloud", "folder", "file", "node", "agent", "usecase",
    "boundary", "card", "stack", "storage", "control", "entity",
)
_PRIMITIVE_RE = re.compile(
    r"^\s*(" + "|".join(_PRIMITIVE_KEYWORDS) + r")\s+"
    r"(?:\"([^\"]+)\"|([A-Za-z_][A-Za-z0-9_]*))"
    r"(?:\s+as\s+([A-Za-z_][A-Za-z0-9_]*))?"
    r"(?:\s+<<[^>]+>>)?"
    r"\s*$",
    re.I,
)
# Plain arrows between primitive aliases:  A -down-> B   X -[hidden]-> Y   etc.
_ARROW_TOKEN = (
    r"-+(?:\[[^\]]*\][-.]*)?"
    r"(?:[a-zA-Z]+[-.]*)?>"
)
_PRIMITIVE_ARROW_RE = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s+"
    rf"({_ARROW_TOKEN})\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
    r"(?:\s*:\s*(.*))?\s*$"
)
_PRIMITIVE_SHAPE: dict[str, NodeShape] = {
    "rectangle": NodeShape.RECT,
    "frame":     NodeShape.RECT,
    "component": NodeShape.RECT,
    "node":      NodeShape.RECT,
    "card":      NodeShape.ROUND,
    "folder":    NodeShape.RECT,
    "file":      NodeShape.RECT,
    "stack":     NodeShape.RECT,
    "storage":   NodeShape.RECT,
    "control":   NodeShape.CIRCLE,
    "entity":    NodeShape.CIRCLE,
    "interface": NodeShape.CIRCLE,
    "database":  NodeShape.CIRCLE,
    "queue":     NodeShape.STADIUM,
    "actor":     NodeShape.ROUND,
    "cloud":     NodeShape.ROUND,
    "agent":     NodeShape.RECT,
    "usecase":   NodeShape.STADIUM,
    "boundary":  NodeShape.RECT,
}
_BOUNDARY_OPEN_RE = re.compile(
    r"^\s*(?:System_Boundary|Container_Boundary|Enterprise_Boundary|Boundary)"
    r"\s*\([^)]*\)\s*\{\s*$"
)
_BOUNDARY_CLOSE_RE = re.compile(r"^\s*\}\s*$")


# Per-macro mapping to (NodeShape, has_tech_arg).
_NODE_MACROS: dict[str, tuple[NodeShape, bool]] = {
    "Person":            (NodeShape.ROUND, False),
    "Person_Ext":        (NodeShape.ROUND, False),
    "System":            (NodeShape.RECT, False),
    "System_Ext":        (NodeShape.RECT, False),
    "SystemDb":          (NodeShape.CIRCLE, False),
    "SystemDb_Ext":      (NodeShape.CIRCLE, False),
    "SystemQueue":       (NodeShape.STADIUM, False),
    "SystemQueue_Ext":   (NodeShape.STADIUM, False),
    "Container":         (NodeShape.RECT, True),
    "Container_Ext":     (NodeShape.RECT, True),
    "ContainerDb":       (NodeShape.CIRCLE, True),
    "ContainerDb_Ext":   (NodeShape.CIRCLE, True),
    "ContainerQueue":    (NodeShape.STADIUM, True),
    "ContainerQueue_Ext":(NodeShape.STADIUM, True),
    "Component":         (NodeShape.RECT, True),
    "Component_Ext":     (NodeShape.RECT, True),
    "ComponentDb":       (NodeShape.CIRCLE, True),
    "ComponentDb_Ext":   (NodeShape.CIRCLE, True),
    "ComponentQueue":    (NodeShape.STADIUM, True),
    "ComponentQueue_Ext":(NodeShape.STADIUM, True),
    # C4-PlantUML alternative names
    "Component_Boundary":(NodeShape.RECT, True),
}

# Edge macros and their direction flag (we ignore direction for layout —
# Sugiyama figures it out — but treat `_Back` / `BiRel` specially).
_REL_MACROS: dict[str, tuple[bool, ArrowStyle]] = {
    # name           → (reverse, arrow style)
    "Rel":           (False, ArrowStyle.END),
    "Rel_U":         (False, ArrowStyle.END),
    "Rel_D":         (False, ArrowStyle.END),
    "Rel_L":         (False, ArrowStyle.END),
    "Rel_R":         (False, ArrowStyle.END),
    "Rel_Up":        (False, ArrowStyle.END),
    "Rel_Down":      (False, ArrowStyle.END),
    "Rel_Left":      (False, ArrowStyle.END),
    "Rel_Right":     (False, ArrowStyle.END),
    "Rel_Back":      (True,  ArrowStyle.END),
    "Rel_Back_U":    (True,  ArrowStyle.END),
    "Rel_Back_D":    (True,  ArrowStyle.END),
    "Rel_Back_L":    (True,  ArrowStyle.END),
    "Rel_Back_R":    (True,  ArrowStyle.END),
    "Rel_Neighbor":  (False, ArrowStyle.END),
    "BiRel":         (False, ArrowStyle.BOTH),
    "BiRel_U":       (False, ArrowStyle.BOTH),
    "BiRel_D":       (False, ArrowStyle.BOTH),
    "BiRel_L":       (False, ArrowStyle.BOTH),
    "BiRel_R":       (False, ArrowStyle.BOTH),
}

# Macros that are pure visual hints — silently ignored.
_SKIP_MACROS = frozenset({
    "AddElementTag", "AddRelTag", "AddPersonTag", "AddContainerTag",
    "AddBoundaryTag", "AddExternalPersonTag", "AddSystemTag",
    "AddProperty", "SetPropertyHeader", "WithoutPropertyHeader",
    "UpdateElementStyle", "UpdateRelStyle", "UpdateBoundaryStyle",
    "UpdateSystemBoundaryStyle", "RoundedBoxShape", "EightSidedShape",
    "DashedLine", "DottedLine", "BoldLine", "LEGEND", "Legend",
    "SHOW_LEGEND", "HIDE_STEREOTYPE", "title", "caption",
    "Lay_U", "Lay_D", "Lay_L", "Lay_R",
    "Lay_Up", "Lay_Down", "Lay_Left", "Lay_Right",
    "Lay_Distance",
})

# Lines that are not macros but should be skipped silently.
_LINE_SKIP_RE = re.compile(
    r"^\s*(?:!|hide\b|show\b|skinparam\b|left\s+header|right\s+header|"
    r"top\s+to\s+|left\s+to\s+|footer\b|caption\b|title\b|"
    r"scale\b|allowmixing\b)",
    re.I,
)


def _split_args(s: str) -> list[str]:
    """Split a macro arg list on commas, respecting double-quoted strings.

    Handles `Rel(a, b, "label, with comma", "tech")` correctly.
    """
    out: list[str] = []
    cur: list[str] = []
    in_str = False
    escape = False
    for ch in s:
        if escape:
            cur.append(ch)
            escape = False
            continue
        if ch == "\\":
            cur.append(ch)
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            cur.append(ch)
            continue
        if ch == "," and not in_str:
            out.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur).strip())
    return out


_NAMED_ARG_RE = re.compile(r"^\$[A-Za-z_]\w*\s*=")


def _split_positional(args: list[str]) -> list[str]:
    """Drop named args (`$tags=...`, `$sprite=...`) — keep only positional.

    C4-PlantUML mixes positional `(alias, "label", "tech")` with named
    decorators like `$tags="customer"`. We don't render styling, so we
    just strip them and keep the positional sequence intact.
    """
    return [a for a in args if not _NAMED_ARG_RE.match(a)]


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1]
    # PlantUML allows `\n` as an in-string newline marker; convert it to
    # an actual newline so the label-wrapper sees multi-line text instead
    # of literal backslash-n.
    return s.replace("\\n", "\n")


def parse(text: str) -> GraphIR:
    lines = text.splitlines()
    body_start = -1
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("'"):
            continue
        if _START_RE.match(ln):
            body_start = i + 1
            break
        raise AdapterError(f"expected '@startuml' header, got: {ln!r}")
    if body_start < 0:
        raise AdapterError("missing @startuml")

    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    direction = Direction.TD     # default; overridden by `left to right direction`
    boundary_depth = 0           # we flatten boundaries; just track open/close

    for raw in lines[body_start:]:
        if raw.lstrip().startswith("'"):
            continue
        s = raw.strip()
        if not s:
            continue
        if _END_RE.match(s):
            break
        if _BOUNDARY_CLOSE_RE.match(s):
            boundary_depth = max(0, boundary_depth - 1)
            continue
        if _BOUNDARY_OPEN_RE.match(s):
            boundary_depth += 1
            continue
        m = _DIRECTION_RE.match(s)
        if m:
            a, b = m.group(1).lower(), m.group(2).lower()
            if (a, b) in (("left", "right"), ("right", "left")):
                direction = Direction.LR
            elif (a, b) in (("top", "bottom"), ("bottom", "top")):
                direction = Direction.TD
            continue
        if _LINE_SKIP_RE.match(s):
            continue
        # Plain-PlantUML primitive declaration:  rectangle Foo <<Stereotype>>
        pm = _PRIMITIVE_RE.match(s)
        if pm:
            kind = pm.group(1).lower()
            quoted_label = pm.group(2)
            bare_id = pm.group(3)
            alias = pm.group(4) or bare_id or quoted_label
            label = quoted_label or bare_id or alias
            shape = _PRIMITIVE_SHAPE.get(kind, NodeShape.RECT)
            if alias and alias not in nodes:
                nodes[alias] = Node(id=alias, label=label, shape=shape)
            continue
        # Plain arrow: A -direction-> B [: label]
        am = _PRIMITIVE_ARROW_RE.match(s)
        if am:
            src, raw_arrow, dst, label = am.group(1), am.group(2), am.group(3), am.group(4)
            # Skip layout-only `[hidden]` arrows.
            if "hidden" in raw_arrow.lower():
                continue
            for who in (src, dst):
                if who not in nodes:
                    nodes[who] = Node(id=who, label=who, shape=NodeShape.RECT)
            edges.append(Edge(src=src, dst=dst,
                              label=(label.strip() if label else None),
                              style=EdgeStyle.SOLID, arrow=ArrowStyle.END))
            continue
        mm = _MACRO_RE.match(s)
        if not mm:
            continue
        name, raw_args = mm.group(1), mm.group(2)
        if name in _SKIP_MACROS:
            continue
        # Drop named-arg decorators (`$tags="…"`, `$sprite="…"`) and keep
        # only the positional sequence — `Person(alias, "label", $tags="x")`
        # still parses as alias + label.
        positional = _split_positional(_split_args(raw_args))
        args = [_unquote(a) for a in positional]
        if not args:
            continue
        # Node macro?
        if name in _NODE_MACROS:
            shape, _has_tech = _NODE_MACROS[name]
            alias = args[0].strip()
            label = args[1] if len(args) >= 2 else alias
            if not alias:
                continue
            # Avoid duplicates; first definition wins.
            if alias not in nodes:
                nodes[alias] = Node(id=alias, label=label or alias, shape=shape)
            continue
        # Edge macro?
        if name in _REL_MACROS:
            reverse, arrow = _REL_MACROS[name]
            if len(args) < 2:
                continue
            src = args[0].strip()
            dst = args[1].strip()
            label = args[2] if len(args) >= 3 else None
            if reverse:
                src, dst = dst, src
            for who in (src, dst):
                if who not in nodes:
                    nodes[who] = Node(id=who, label=who, shape=NodeShape.RECT)
            edges.append(Edge(src=src, dst=dst, label=label,
                              style=EdgeStyle.SOLID, arrow=arrow))
            continue
        # Anything else: skip leniently.

    if not nodes:
        raise AdapterError("no C4 nodes found")
    return GraphIR(direction=direction,
                   nodes=tuple(nodes.values()),
                   edges=tuple(edges))
