"""Public entry point — dispatches by diagram type to the right pipeline.

Each input format (mermaid, plantuml, …) has its own adapter that parses
into one of the format-agnostic IRs (GraphIR / SequenceIR / ClassIR /
GanttIR). The renderer for each IR is shared across input formats.
"""
from __future__ import annotations

import re


# Mermaid uses a leading keyword on the first content line. PlantUML uses
# `@startXxx` markers and (for the generic `@startuml`) needs a peek at
# the body to figure out which diagram type it actually is. We handle
# both with a two-tier detection: header pattern + optional body sniff.
_MERMAID_HEADER_TO_TYPE = (
    (re.compile(r"^\s*(?:graph|flowchart)\b", re.I), "flowchart"),
    (re.compile(r"^\s*sequenceDiagram\b", re.I),     "sequence"),
    (re.compile(r"^\s*classDiagram\b", re.I),        "class"),
    (re.compile(r"^\s*gantt\b", re.I),               "gantt"),
)

_PLANTUML_GANTT_RE = re.compile(r"^\s*@startgantt\b", re.I)
_PLANTUML_GENERIC_RE = re.compile(r"^\s*@startuml\b", re.I)
_PLANTUML_END_RE = re.compile(r"^\s*@end\w+\s*$", re.I)

# Body sniffers for `@startuml` (which can be sequence, class, or activity).
# Order matters — most specific first.
_SNIFF_SEQUENCE = re.compile(
    r"\b(?:participant|actor)\b|->>?|-->|<<-|<--",  # arrow heuristics
    re.I,
)
_SNIFF_CLASS = re.compile(
    r"\bclass\s+\w+\s*[{\s]|<\|--|--\|>|\*--|--\*|o--|--o|"
    r"\binterface\b|\babstract\b",
    re.I,
)
# Distinctive activity-diagram tokens. `end` alone is too ambiguous —
# it's also used by sequence diagrams to close a `loop` / `alt` block —
# so we look only at activity-only markers here.
_SNIFF_ACTIVITY = re.compile(
    r"^\s*(?:start\s*$|stop\s*$|:[^;]+;|if\s*\(|while\s*\(|repeat\b)",
    re.I | re.MULTILINE,
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


def _detect(text: str) -> tuple[str | None, str | None]:
    """Return (source_format, diagram_type) from the source text.

    `source_format` is "mermaid" or "plantuml" (or None if unrecognized).
    `diagram_type` is one of: flowchart, sequence, class, gantt.
    """
    body = _strip_frontmatter(text)
    # Find the first non-comment content line to use as the header signal.
    first_line: str | None = None
    for line in body.splitlines():
        s = line.strip()
        if not s or s.startswith("%%") or s.startswith("'"):
            continue
        first_line = s
        break
    if first_line is None:
        return None, None

    # Mermaid header keywords.
    for pat, kind in _MERMAID_HEADER_TO_TYPE:
        if pat.match(first_line):
            return "mermaid", kind

    # PlantUML markers.
    if _PLANTUML_GANTT_RE.match(first_line):
        return "plantuml", "gantt"
    if _PLANTUML_GENERIC_RE.match(first_line):
        # `@startuml` is generic — sniff the body to find out which kind.
        return "plantuml", _sniff_plantuml(body)

    return None, None


def _sniff_plantuml(body: str) -> str | None:
    """Decide which kind of `@startuml` block we're looking at."""
    # Class is the most distinctive (specific keywords/connectors).
    if _SNIFF_CLASS.search(body):
        return "class"
    # Activity uses block keywords + `:label;` syntax — detect before
    # sequence because activity also uses `->`.
    if _SNIFF_ACTIVITY.search(body):
        return None  # not yet supported — fall back to code block
    # Default for `@startuml` with arrows: sequence.
    if _SNIFF_SEQUENCE.search(body):
        return "sequence"
    return None


def render_mermaid(text: str, width: int, *, ascii_only: bool = False) -> list[str] | None:
    """Render a mermaid OR plantuml block to a list of terminal lines.

    The function name is kept for backward compat with v0.4.x; despite
    the name it dispatches to whichever input-format adapter matches the
    source. Returns None on any pipeline failure so the caller can fall
    back to rendering the original code block. Never raises.
    """
    fmt, kind = _detect(text)
    if fmt is None or kind is None:
        return None
    try:
        if fmt == "mermaid":
            if kind == "flowchart": return _render_flowchart(text, width, ascii_only)
            if kind == "sequence":  return _render_sequence(text, width, ascii_only)
            if kind == "class":     return _render_class(text, width, ascii_only)
            if kind == "gantt":     return _render_gantt(text, width, ascii_only)
        elif fmt == "plantuml":
            if kind == "sequence":  return _render_plantuml_sequence(text, width, ascii_only)
            if kind == "class":     return _render_plantuml_class(text, width, ascii_only)
            if kind == "gantt":     return _render_plantuml_gantt(text, width, ascii_only)
    except Exception:
        # Defensive: never let a diagram bug crash the markdown renderer.
        return None
    return None


# Backward-compatible alias — the public function will be renamed to
# render_diagram in a later release; for now both names point at the
# same dispatch.
render_diagram = render_mermaid


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


# --- PlantUML pipelines (same renderers; only the adapter differs) -------

def _render_plantuml_sequence(text, width, ascii_only):
    from .adapters import plantuml_sequence as adapter
    from .errors import DiagramError
    from .render.sequence import render
    try:
        ir = adapter.parse(text)
        return render(ir, width=width, ascii_only=ascii_only)
    except DiagramError:
        return None


def _render_plantuml_class(text, width, ascii_only):
    from .adapters import plantuml_class as adapter
    from .errors import DiagramError
    from .layout.grandalf import compute_layout_class
    from .render.class_ import render
    try:
        ir = adapter.parse(text)
        layout = compute_layout_class(ir)
        return render(layout, width=width, ascii_only=ascii_only)
    except DiagramError:
        return None


def _render_plantuml_gantt(text, width, ascii_only):
    from .adapters import plantuml_gantt as adapter
    from .errors import DiagramError
    from .render.gantt import render
    try:
        ir = adapter.parse(text)
        return render(ir, width=width, ascii_only=ascii_only)
    except DiagramError:
        return None
