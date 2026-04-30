"""PlantUML gantt diagrams (`@startgantt … @endgantt`) → GanttIR.

Supported:
    @startgantt ... @endgantt
    project starts <date>           project anchor (used when a task has
                                    no explicit start)
    title <text>                    diagram title
    [Task name] lasts N day(s)|week(s)
    [Task name] starts <date>
    [Task name] starts at [Other]'s end
    [Task name] starts at <date>
    [Task name] ends <date>
    [Task name] requires N days     (alias for `lasts`)
    [Task name] is colored in <color>   (treated as state hint:
                                         red/crit → CRITICAL, etc.)
    [Task name] is done             → TaskState.DONE
    [Task name] is 100% completed    → TaskState.DONE
                                       (>=100% complete)
    [Task name] is X% completed      → TaskState.ACTIVE if 0<X<100
    -- <Section name> --             section divider

Skipped silently:
    skinparam, language, header/footer, !theme, etc.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..errors import AdapterError
from ..ir_gantt import GanttIR, Task, TaskState


_START_RE = re.compile(r"^\s*@startgantt\b", re.I)
_END_RE = re.compile(r"^\s*@endgantt\s*$", re.I)
_TITLE_RE = re.compile(r"^\s*title\s+(.+?)\s*$", re.I)
_PROJECT_STARTS_RE = re.compile(
    r"^\s*project\s+starts\s+(?:on\s+)?(\S+)\s*$", re.I
)
_SECTION_RE = re.compile(r"^\s*--\s+(.+?)\s+--\s*$")
_DURATION_PHRASE_RE = re.compile(
    r"\[(.+?)\]\s+(?:lasts|requires)\s+(\d+)\s*(day|days|week|weeks|d|w)\b",
    re.I,
)
_STARTS_AT_DATE_RE = re.compile(
    r"\[(.+?)\]\s+starts(?:\s+at)?\s+(?:on\s+)?(\d{4}-\d{2}-\d{2})", re.I
)
_STARTS_AT_END_RE = re.compile(
    r"\[(.+?)\]\s+starts\s+at\s+\[(.+?)\]'?s?\s+end", re.I
)
_ENDS_RE = re.compile(
    r"\[(.+?)\]\s+ends?(?:\s+on)?\s+(\d{4}-\d{2}-\d{2})", re.I
)
_DONE_RE = re.compile(r"\[(.+?)\]\s+is\s+done\b", re.I)
_PERCENT_RE = re.compile(
    r"\[(.+?)\]\s+is\s+(\d+)%\s+completed?\b", re.I
)
_COLOR_RE = re.compile(
    r"\[(.+?)\]\s+is\s+colored?\s+in\s+(\w+)\b", re.I
)


def _to_date(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def parse(text: str) -> GanttIR:
    lines = text.splitlines()
    body_start = -1
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s or s.startswith("'"):
            continue
        if _START_RE.match(ln):
            body_start = i + 1
            break
        raise AdapterError(f"expected '@startgantt' header, got: {ln!r}")
    if body_start < 0:
        raise AdapterError("missing @startgantt")

    title: str | None = None
    project_start: date | None = None
    section: str | None = None

    # Per-task accumulators — PlantUML often spreads a task across multiple
    # lines (`[X] lasts 5 days`, `[X] starts at [Y]'s end`, …), so we
    # collect attributes first and resolve at the end.
    class _TaskAcc:
        __slots__ = ("name", "start", "end", "duration_days", "after_id",
                     "state", "section")
        def __init__(self, name):
            self.name = name
            self.start: date | None = None
            self.end: date | None = None
            self.duration_days: int | None = None
            self.after_id: str | None = None
            self.state = TaskState.FUTURE
            self.section = section

    tasks_by_name: dict[str, _TaskAcc] = {}
    order: list[str] = []

    def get(name: str) -> _TaskAcc:
        if name not in tasks_by_name:
            t = _TaskAcc(name)
            tasks_by_name[name] = t
            order.append(name)
            return t
        return tasks_by_name[name]

    for raw in lines[body_start:]:
        if raw.lstrip().startswith("'"):
            continue
        s = raw.strip()
        if not s:
            continue
        if _END_RE.match(s):
            break
        if (m := _TITLE_RE.match(s)):
            title = m.group(1)
            continue
        if (m := _PROJECT_STARTS_RE.match(s)):
            d = _to_date(m.group(1))
            if d is not None:
                project_start = d
            continue
        if (m := _SECTION_RE.match(s)):
            section = m.group(1)
            continue
        if (m := _DURATION_PHRASE_RE.match(s)):
            name, n, unit = m.group(1), int(m.group(2)), m.group(3).lower()
            t = get(name)
            t.duration_days = n * 7 if unit.startswith("w") else n
            continue
        if (m := _STARTS_AT_DATE_RE.match(s)):
            d = _to_date(m.group(2))
            if d is not None:
                get(m.group(1)).start = d
            continue
        if (m := _STARTS_AT_END_RE.match(s)):
            get(m.group(1)).after_id = m.group(2)
            continue
        if (m := _ENDS_RE.match(s)):
            d = _to_date(m.group(2))
            if d is not None:
                get(m.group(1)).end = d
            continue
        if (m := _DONE_RE.match(s)):
            get(m.group(1)).state = TaskState.DONE
            continue
        if (m := _PERCENT_RE.match(s)):
            pct = int(m.group(2))
            t = get(m.group(1))
            t.state = TaskState.DONE if pct >= 100 else (
                TaskState.ACTIVE if pct > 0 else TaskState.FUTURE
            )
            continue
        if (m := _COLOR_RE.match(s)):
            color = m.group(2).lower()
            if color in ("red", "crit", "critical"):
                get(m.group(1)).state = TaskState.CRITICAL
            elif color in ("green", "done"):
                get(m.group(1)).state = TaskState.DONE
            continue
        # Anything else: skip leniently.

    # Resolve dates: walk in order, using project_start / `after` deps.
    resolved: list[Task] = []
    for name in order:
        t = tasks_by_name[name]
        if t.start is None and t.after_id and t.after_id in tasks_by_name:
            ref = tasks_by_name[t.after_id]
            if ref.start is not None and ref.duration_days is not None:
                ref_end = ref.end or (ref.start + timedelta(days=ref.duration_days))
                t.start = ref_end
            elif ref.end is not None:
                t.start = ref.end
        if t.start is None and project_start is not None:
            t.start = project_start
        if t.start is None:
            continue   # cannot place — skip
        if t.end is None:
            if t.duration_days is not None:
                t.end = t.start + timedelta(days=t.duration_days)
            else:
                t.end = t.start + timedelta(days=1)
        resolved.append(Task(
            id=name, name=name, section=t.section,
            state=t.state, start=t.start, end=t.end,
        ))

    if not resolved:
        raise AdapterError("no tasks resolved")
    return GanttIR(title=title, tasks=tuple(resolved))
