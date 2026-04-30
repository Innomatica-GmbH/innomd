"""Public entry point — dispatches by diagram type to the right pipeline.

Architecture is intentionally pluggable so a future PlantUML adapter can
slot in next to the mermaid ones: each adapter parses a source-format
subset into one of the format-agnostic IRs (GraphIR / SequenceIR /
ClassIR / GanttIR), and each IR has its own renderer.
"""
from __future__ import annotations

import re


# Detect the diagram type from the first non-blank, non-frontmatter line.
# We look at the leading keyword and dispatch accordingly. Anything not in
# this map falls through and the caller renders the source as a code block.
_HEADER_TO_TYPE = (
    (re.compile(r"^\s*(?:graph|flowchart)\b", re.I), "flowchart"),
    (re.compile(r"^\s*sequenceDiagram\b", re.I),     "sequence"),
    (re.compile(r"^\s*classDiagram\b", re.I),        "class"),
    (re.compile(r"^\s*gantt\b", re.I),               "gantt"),
)


def _strip_frontmatter(text: str) -> str:
    """Drop a leading ``---\\n...\\n---`` block, if present."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if i < len(lines) and lines[i].strip() == "---":
        j = i + 1
        while j < len(lines):
            if lines[j].strip() == "---":
                return "\n".join(lines[j + 1:])
            j += 1
    return text


def _detect_type(text: str) -> str | None:
    body = _strip_frontmatter(text)
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("%%"):
            continue
        for pat, kind in _HEADER_TO_TYPE:
            if pat.match(s):
                return kind
        return None  # first content line didn't match any known type
    return None


def render_mermaid(text: str, width: int, *, ascii_only: bool = False) -> list[str] | None:
    """Render a mermaid block to a list of terminal lines.

    Returns None on any pipeline failure so the caller can fall back to
    rendering the original code block. Never raises.
    """
    kind = _detect_type(text)
    if kind is None:
        return None
    try:
        if kind == "flowchart":
            return _render_flowchart(text, width, ascii_only)
        if kind == "sequence":
            return _render_sequence(text, width, ascii_only)
        if kind == "class":
            return _render_class(text, width, ascii_only)
        if kind == "gantt":
            return _render_gantt(text, width, ascii_only)
    except Exception:
        # Defensive: never let a diagram bug crash the markdown renderer.
        return None
    return None


# --- Per-type pipelines (lazy imports keep startup light) -----------------

def _render_flowchart(text, width, ascii_only):
    from .adapters import mermaid as adapter
    from .errors import DiagramError
    from .layout.grandalf import compute_layout
    from .render.ascii import render
    try:
        ir = adapter.parse(text)
        layout = compute_layout(ir)
        return render(layout, width=width, ascii_only=ascii_only)
    except DiagramError:
        return None


def _render_sequence(text, width, ascii_only):
    from .adapters import mermaid_sequence as adapter
    from .errors import DiagramError
    from .render.sequence import render
    try:
        ir = adapter.parse(text)
        return render(ir, width=width, ascii_only=ascii_only)
    except DiagramError:
        return None


def _render_class(text, width, ascii_only):
    from .adapters import mermaid_class as adapter
    from .errors import DiagramError
    from .layout.grandalf import compute_layout_class
    from .render.class_ import render
    try:
        ir = adapter.parse(text)
        layout = compute_layout_class(ir)
        return render(layout, width=width, ascii_only=ascii_only)
    except DiagramError:
        return None


def _render_gantt(text, width, ascii_only):
    from .adapters import mermaid_gantt as adapter
    from .errors import DiagramError
    from .render.gantt import render
    try:
        ir = adapter.parse(text)
        return render(ir, width=width, ascii_only=ascii_only)
    except DiagramError:
        return None
