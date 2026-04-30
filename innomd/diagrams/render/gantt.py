"""GanttIR → list[str] (terminal lines).

Layout:
  - Title row (optional).
  - Date axis: shows month/day ticks across the available width.
  - For each task: a label column on the left + a horizontal bar.
  - Tasks are grouped by section (if any), with section headers between.

Bar glyphs by state:
  DONE      ━━━ (heavy line, "completed")
  ACTIVE    ▓▓▓ (shaded, "in progress")
  CRITICAL  ▒▒▒ (lighter shade — fallback for crit)
  FUTURE    ░░░ (light shade)

ASCII fallback uses #, @, *, .
"""
from __future__ import annotations

from datetime import date, timedelta

from ..errors import RenderError
from ..ir_gantt import GanttIR, Task, TaskState
from .box import ASCII, UNICODE, Glyphs


_PADDING = 1
_LABEL_PAD = 2          # spaces between label column and bar area


def render(ir: GanttIR, *, width: int, ascii_only: bool = False) -> list[str]:
    glyphs = ASCII if ascii_only else UNICODE
    if not ir.tasks:
        raise RenderError("no tasks")

    # 1. Compute the time range.
    start = min(t.start for t in ir.tasks)
    end = max(t.end for t in ir.tasks)
    total_days = max(1, (end - start).days)

    # 2. Compute label-column width (longest task name).
    label_w = max(len(t.name) for t in ir.tasks) + _LABEL_PAD
    # 3. Bar area width = remaining canvas after labels and padding.
    bar_w = width - label_w - 2 * _PADDING
    if bar_w < 10:
        raise RenderError(
            f"gantt needs at least {label_w + 12} cols, only {width} available"
        )

    days_per_col = total_days / bar_w     # may be < 1 (each day = several cols)

    def x_for_date(d: date) -> int:
        return int(round((d - start).days / days_per_col))

    # 4. Header rows.
    rows: list[str] = []
    if ir.title:
        rows.append(" " * _PADDING + ir.title.center(width - 2 * _PADDING))
        rows.append("")
    # Date axis.
    rows.extend(_render_axis(start, end, label_w, bar_w, glyphs, ascii_only))
    rows.append("")

    # 5. Task rows, grouped by section.
    last_section: str | None = None
    for t in ir.tasks:
        if t.section != last_section and t.section is not None:
            rows.append("")
            rows.append(" " * _PADDING + _bold(t.section, ascii_only))
            last_section = t.section
        elif last_section is None and t.section is not None:
            last_section = t.section
        rows.append(_render_task(t, label_w, bar_w, x_for_date, glyphs, ascii_only))

    return rows


def _bold(s: str, ascii_only: bool) -> str:
    # Sections are emphasized with surrounding lines in plain text; ANSI bold
    # gets stripped by tests, so we use a visual underline instead.
    return s if ascii_only else s    # leave plain — innomd's pager renders bold


def _render_axis(start: date, end: date, label_w: int, bar_w: int,
                 g: Glyphs, ascii_only: bool) -> list[str]:
    """Render header rows for the date axis.

    Layout:
        Row 0: year label, only at the leftmost tick AND wherever the year
               changes mid-axis. Otherwise blank.
        Row 1: MM-DD ticks across the available width.
        Row 2: horizontal axis line with ┬ markers at each tick.
    """
    days = max(1, (end - start).days)
    tick_step_days = max(1, days // 8)
    year_chars = [" "] * bar_w
    label_chars = [" "] * bar_w
    axis_chars = [g.h] * bar_w if not ascii_only else ["-"] * bar_w
    last_year: int | None = None
    d = start
    while d <= end:
        col = int(round((d - start).days / days * (bar_w - 1)))
        # MM-DD on row 1.
        text = d.strftime("%m-%d")
        for i, ch in enumerate(text):
            tgt = col + i
            if 0 <= tgt < bar_w:
                label_chars[tgt] = ch
        # Year on row 0, only when it changes (or at first tick).
        if d.year != last_year:
            year_text = str(d.year)
            for i, ch in enumerate(year_text):
                tgt = col + i
                if 0 <= tgt < bar_w:
                    year_chars[tgt] = ch
            last_year = d.year
        # Tick on the axis row.
        if 0 <= col < bar_w:
            axis_chars[col] = "┬" if not ascii_only else "+"
        d += timedelta(days=tick_step_days)
    prefix = " " * (_PADDING + label_w)
    return [
        prefix + "".join(year_chars).rstrip(),
        prefix + "".join(label_chars),
        prefix + "".join(axis_chars),
    ]


def _render_task(t: Task, label_w: int, bar_w: int,
                 x_for_date, g: Glyphs, ascii_only: bool) -> str:
    label = t.name.ljust(label_w)
    bar_chars = [" "] * bar_w
    glyph = _bar_glyph(t.state, ascii_only)
    x_start = max(0, min(bar_w - 1, x_for_date(t.start)))
    x_end = max(0, min(bar_w - 1, x_for_date(t.end) - 1))
    if x_end < x_start:
        x_end = x_start
    for x in range(x_start, x_end + 1):
        bar_chars[x] = glyph
    return " " * _PADDING + label + "".join(bar_chars)


def _bar_glyph(state: TaskState, ascii_only: bool) -> str:
    if ascii_only:
        return {
            TaskState.DONE: "#",
            TaskState.ACTIVE: "@",
            TaskState.CRITICAL: "*",
            TaskState.FUTURE: ".",
        }[state]
    return {
        TaskState.DONE: "█",
        TaskState.ACTIVE: "▓",
        TaskState.CRITICAL: "▒",
        TaskState.FUTURE: "░",
    }[state]
