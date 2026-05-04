"""PlantUML *activity* diagrams (`@startuml … @enduml`) → GraphIR.

Activity diagrams describe control flow rather than entity relationships.
Each `:label;` becomes a process node; `start`/`stop` mark entry/exit;
`if (cond) then (yes) … else (no) … endif` produces a diamond decision
with two outgoing branches that re-merge after the `endif`. Loops
(`while`/`repeat`) are flattened into back-edges.

Supported:
    @startuml ... @enduml
    start                    → start node (circle)
    stop / end               → stop node (double-circle)
    :Action label;           → rect action node
    if (cond) then (yes-label)
    elseif (cond2) then (yes2)
    else (no-label)
    endif
    while (cond) is (yes-label)
    endwhile
    repeat
    repeat while (cond)
    note left|right : ...    (skipped)

Implementation: the parser maintains a stack of "open contexts" and a
single "current node" pointer. Each statement either appends a new node
edged from the current one, or splits/merges paths in the case of
control-flow keywords.
"""
from __future__ import annotations

import re

from ..errors import AdapterError
from ..ir import ArrowStyle, Direction, Edge, EdgeStyle, GraphIR, Node, NodeShape


_START_RE = re.compile(r"^\s*@startuml\b", re.I)
_END_RE = re.compile(r"^\s*@enduml\s*$", re.I)
_ACTIVITY_START_RE = re.compile(r"^\s*start\s*$", re.I)
_ACTIVITY_STOP_RE = re.compile(r"^\s*(?:stop|end)\s*$", re.I)
# An `:label;` action — the label may run over multiple lines, but we
# expect a single-line form for now.
_ACTION_RE = re.compile(r"^\s*:\s*(.*?)\s*;\s*$")
# `if (cond) then (yes-label)` — yes-label optional.
_IF_RE = re.compile(
    r"^\s*if\s*\((.+?)\)\s*then\s*(?:\(([^)]*)\))?\s*$", re.I
)
_ELSEIF_RE = re.compile(
    r"^\s*elseif\s*\((.+?)\)\s*then\s*(?:\(([^)]*)\))?\s*$", re.I
)
# `else` may have its own label `(no)` or be bare.
_ELSE_RE = re.compile(r"^\s*else\s*(?:\(([^)]*)\))?\s*$", re.I)
_ENDIF_RE = re.compile(r"^\s*endif\s*$", re.I)
_WHILE_RE = re.compile(
    r"^\s*while\s*\((.+?)\)\s*(?:is\s*\(([^)]*)\))?\s*$", re.I
)
_ENDWHILE_RE = re.compile(r"^\s*endwhile\s*(?:\(([^)]*)\))?\s*$", re.I)
_REPEAT_RE = re.compile(r"^\s*repeat\s*$", re.I)
_REPEAT_WHILE_RE = re.compile(
    r"^\s*repeat\s+while\s*\((.+?)\)\s*(?:is\s*\(([^)]*)\))?\s*$", re.I
)
_FORK_RE = re.compile(r"^\s*fork\s*$", re.I)
_FORK_AGAIN_RE = re.compile(r"^\s*fork\s+again\s*$", re.I)
_END_FORK_RE = re.compile(r"^\s*end\s+fork\s*$", re.I)
_PARTITION_RE = re.compile(r'^\s*partition\s+(?:"([^"]+)"|(\S+))\s*\{?\s*$', re.I)
_DETACH_RE = re.compile(r"^\s*detach\s*$", re.I)
_LINE_SKIP_RE = re.compile(
    r"^\s*(?:!|note\b|skinparam\b|hide\b|show\b|"
    r"title\b|footer\b|header\b|caption\b)",
    re.I,
)


def parse(text: str) -> GraphIR:
    lines = text.splitlines()
    # @startuml is conventionally required, but real-world docs sometimes
    # show isolated activity snippets without the wrapper. If we don't
    # find a header within the first few non-blank lines, parse from the
    # top.
    body_start = 0
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("'"):
            continue
        if _START_RE.match(ln):
            body_start = i + 1
        # Either way, stop scanning after the first non-blank line —
        # @startuml has to be the very first content line if present.
        break

    nodes: list[Node] = []
    edges: list[Edge] = []
    next_id = [0]

    def new_id() -> str:
        next_id[0] += 1
        return f"n{next_id[0]}"

    def add_node(label: str, shape: NodeShape) -> str:
        nid = new_id()
        nodes.append(Node(id=nid, label=label, shape=shape))
        return nid

    def add_edge(src: str | None, dst: str, label: str | None = None) -> None:
        if src is None or src == dst:
            return
        edges.append(Edge(src=src, dst=dst, label=label,
                          style=EdgeStyle.SOLID, arrow=ArrowStyle.END))

    # `current` is the id of the previous node — every plain action edges
    # forward from it. None means "no current node" (start hasn't run, or
    # we're at a merge point waiting for the next statement).
    current: str | None = None
    # Stack of open IF contexts. Each entry tracks:
    #   diamond_id     — id of the if-diamond
    #   merge_pending  — list of node ids that should edge into the merge
    #   else_seen      — bool
    #   current_label  — label for the next outgoing edge from the diamond
    if_stack: list[dict] = []
    # Stack of open WHILE contexts. Each entry: {diamond_id, exit_pending, ...}
    while_stack: list[dict] = []
    # Stack of REPEAT contexts: {body_start_id}
    repeat_stack: list[str] = []

    for raw in lines[body_start:]:
        if raw.lstrip().startswith("'"):
            continue
        s = raw.strip()
        if not s:
            continue
        if _END_RE.match(s):
            break
        if _LINE_SKIP_RE.match(s):
            continue

        if _ACTIVITY_START_RE.match(s):
            current = add_node("●", NodeShape.CIRCLE)
            continue
        if _ACTIVITY_STOP_RE.match(s):
            stop = add_node("◉", NodeShape.CIRCLE)
            add_edge(current, stop)
            current = None
            continue
        m = _ACTION_RE.match(s)
        if m:
            nid = add_node(m.group(1), NodeShape.RECT)
            if if_stack and if_stack[-1].get("pending_label"):
                # First action after `if/then (label)` or `else (label)`.
                add_edge(if_stack[-1]["diamond_id"], nid,
                         label=if_stack[-1].pop("pending_label"))
            else:
                add_edge(current, nid)
            current = nid
            continue
        m = _IF_RE.match(s)
        if m:
            cond, yes_label = m.group(1).strip(), (m.group(2) or "").strip()
            diamond = add_node(cond, NodeShape.DIAMOND)
            add_edge(current, diamond)
            if_stack.append({
                "diamond_id": diamond,
                "merge_pending": [],
                "else_seen": False,
                "pending_label": yes_label or None,
            })
            current = diamond
            continue
        m = _ELSE_RE.match(s)
        if m and if_stack:
            ctx = if_stack[-1]
            # End of the previous branch — record it as merging.
            if current and current != ctx["diamond_id"]:
                ctx["merge_pending"].append(current)
            ctx["else_seen"] = True
            ctx["pending_label"] = (m.group(1) or "").strip() or "no"
            current = ctx["diamond_id"]
            continue
        m = _ELSEIF_RE.match(s)
        if m and if_stack:
            # Conservative: treat as nested-if; the renderer just flattens.
            ctx = if_stack[-1]
            if current and current != ctx["diamond_id"]:
                ctx["merge_pending"].append(current)
            cond, yes_label = m.group(1).strip(), (m.group(2) or "").strip()
            sub_diamond = add_node(cond, NodeShape.DIAMOND)
            add_edge(ctx["diamond_id"], sub_diamond, label="elseif")
            ctx["diamond_id"] = sub_diamond
            ctx["pending_label"] = yes_label or None
            current = sub_diamond
            continue
        if _ENDIF_RE.match(s) and if_stack:
            ctx = if_stack.pop()
            # Final branch (the one we're on) merges in too.
            if current and current != ctx["diamond_id"]:
                ctx["merge_pending"].append(current)
            # If the if had no else, the diamond itself merges in.
            if not ctx["else_seen"]:
                ctx["merge_pending"].append(ctx["diamond_id"])
            # De-duplicate merge sources (a branch that ended with `stop`
            # leaves no live tail, so we'd double-count otherwise).
            seen = set()
            sources = []
            for sid in ctx["merge_pending"]:
                if sid not in seen:
                    seen.add(sid)
                    sources.append(sid)
            if not sources:
                # All branches dead-ended (e.g. both had `stop`). No merge
                # node is needed; the next statement starts fresh.
                current = None
            elif len(sources) == 1:
                # Only one branch survived the `endif`. No merge needed —
                # propagate that branch's tail as the new current.
                current = sources[0]
            else:
                merge = add_node("", NodeShape.CIRCLE)
                for src in sources:
                    add_edge(src, merge)
                current = merge
            continue
        m = _WHILE_RE.match(s)
        if m:
            cond, yes_label = m.group(1).strip(), (m.group(2) or "").strip()
            diamond = add_node(cond, NodeShape.DIAMOND)
            add_edge(current, diamond)
            while_stack.append({
                "diamond_id": diamond,
                "exit_label": None,
                "pending_label": yes_label or None,
            })
            current = diamond
            continue
        m = _ENDWHILE_RE.match(s)
        if m and while_stack:
            ctx = while_stack.pop()
            if current and current != ctx["diamond_id"]:
                add_edge(current, ctx["diamond_id"], label="loop")
            current = ctx["diamond_id"]   # exit edge from diamond is "no"
            continue
        if _REPEAT_RE.match(s):
            anchor = add_node("⟲", NodeShape.CIRCLE)
            add_edge(current, anchor)
            repeat_stack.append(anchor)
            current = anchor
            continue
        m = _REPEAT_WHILE_RE.match(s)
        if m and repeat_stack:
            anchor = repeat_stack.pop()
            cond = m.group(1).strip()
            diamond = add_node(cond, NodeShape.DIAMOND)
            add_edge(current, diamond)
            add_edge(diamond, anchor, label="yes")
            current = diamond
            continue
        if _FORK_RE.match(s):
            # Treat fork as creating a parallel split — for ASCII we
            # flatten and continue. (Render correctness is best-effort.)
            continue
        if _FORK_AGAIN_RE.match(s) or _END_FORK_RE.match(s):
            continue
        if _PARTITION_RE.match(s):
            continue
        if _DETACH_RE.match(s):
            current = None
            continue
        # Unknown line — skip leniently.

    if not nodes:
        raise AdapterError("no activity steps found")
    return GraphIR(direction=Direction.TD,
                   nodes=tuple(nodes),
                   edges=tuple(edges))
