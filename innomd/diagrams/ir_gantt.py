"""IR for gantt charts: tasks on a time axis, optionally grouped by section."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class TaskState(Enum):
    DONE = "done"
    ACTIVE = "active"
    CRITICAL = "crit"
    FUTURE = "future"


@dataclass(frozen=True)
class Task:
    id: str                       # internal id (used by `after` deps)
    name: str                     # display label
    section: str | None           # optional grouping
    state: TaskState
    start: date                   # resolved absolute start
    end: date                     # resolved absolute end (exclusive)


@dataclass(frozen=True)
class GanttIR:
    title: str | None
    tasks: tuple[Task, ...]
