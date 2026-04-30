"""Mermaid gantt subset → GanttIR.

Supported:
    gantt
    title <text>
    dateFormat YYYY-MM-DD
    section <name>
    Task name : [state,] id, start, end-or-duration

States:
    done, active, crit  (anything else → future)

Start can be:
    YYYY-MM-DD          absolute date
    after <id>          start = end of task `id`

End can be:
    YYYY-MM-DD          absolute end date
    Nd / Nw / Nh / Nm   duration (days/weeks/hours/minutes; we only
                        treat days; weeks → 7d; hours/minutes → 1d
                        rounded up since our axis is day-resolution)

Skipped silently:
    excludes <weekday/date>
    todayMarker
    axisFormat
    weekday <day>
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from ..errors import AdapterError
from ..ir_gantt import GanttIR, Task, TaskState


_HEADER_RE = re.compile(r"^\s*gantt\s*$", re.I)
_TITLE_RE = re.compile(r"^\s*title\s+(.+?)\s*$", re.I)
_DATEFMT_RE = re.compile(r"^\s*dateFormat\s+(\S+)\s*$", re.I)
_SECTION_RE = re.compile(r"^\s*section\s+(.+?)\s*$", re.I)
_DURATION_RE = re.compile(r"^(\d+)\s*([dwhm])$", re.I)


_STATE_MAP = {
    "done": TaskState.DONE,
    "active": TaskState.ACTIVE,
    "crit": TaskState.CRITICAL,
}


def _parse_date(s: str, fmt: str) -> date | None:
    # Mermaid's dateFormat is similar to strptime. We translate the most
    # common pattern; everything else falls back to ISO.
    py_fmt = fmt.replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
    try:
        return datetime.strptime(s, py_fmt).date()
    except ValueError:
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None


def _parse_duration(s: str) -> timedelta | None:
    m = _DURATION_RE.match(s.strip())
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    if unit == "d": return timedelta(days=n)
    if unit == "w": return timedelta(weeks=n)
    if unit == "h": return timedelta(days=max(1, (n + 23) // 24))
    if unit == "m": return timedelta(days=1)
    return None


def parse(text: str) -> GanttIR:
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
        raise AdapterError(f"expected 'gantt' header, got: {ln!r}")
    if not found:
        raise AdapterError("empty diagram")

    title: str | None = None
    date_fmt = "%Y-%m-%d"
    current_section: str | None = None
    tasks: list[Task] = []
    by_id: dict[str, Task] = {}

    for raw in lines[body_start:]:
        s = raw.split("%%", 1)[0].strip()
        if not s:
            continue
        if (m := _TITLE_RE.match(s)):
            title = m.group(1)
            continue
        if (m := _DATEFMT_RE.match(s)):
            date_fmt = m.group(1).replace("YYYY", "%Y").replace("MM", "%m").replace("DD", "%d")
            continue
        if (m := _SECTION_RE.match(s)):
            current_section = m.group(1)
            continue
        # Skip directives we don't model.
        if re.match(r"^\s*(?:excludes|todayMarker|axisFormat|weekday)\b", s, re.I):
            continue
        # Task line:  Name : [state,] id, start, end-or-duration
        if ":" not in s:
            continue
        name, _, fields_blob = s.partition(":")
        name = name.strip()
        parts = [p.strip() for p in fields_blob.split(",") if p.strip()]
        if len(parts) < 3:
            continue
        # State is optional and appears as the first part if present.
        state = TaskState.FUTURE
        if parts[0].lower() in _STATE_MAP:
            state = _STATE_MAP[parts[0].lower()]
            parts = parts[1:]
        if len(parts) < 3:
            continue
        task_id, start_spec, end_spec = parts[0], parts[1], parts[2]
        # Resolve start.
        if start_spec.lower().startswith("after "):
            ref_id = start_spec[6:].strip()
            ref = by_id.get(ref_id)
            if ref is None:
                continue
            start = ref.end
        else:
            try:
                start = datetime.strptime(start_spec, date_fmt).date()
            except ValueError:
                start = _parse_date(start_spec, date_fmt) or None
                if start is None:
                    continue
        # Resolve end (absolute date OR duration).
        dur = _parse_duration(end_spec)
        if dur is not None:
            end = start + dur
        else:
            try:
                end = datetime.strptime(end_spec, date_fmt).date()
            except ValueError:
                end = _parse_date(end_spec, date_fmt)
                if end is None:
                    continue
        task = Task(id=task_id, name=name, section=current_section,
                    state=state, start=start, end=end)
        tasks.append(task)
        by_id[task_id] = task

    if not tasks:
        raise AdapterError("no tasks found")
    return GanttIR(title=title, tasks=tuple(tasks))
