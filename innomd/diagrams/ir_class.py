"""IR for class diagrams: classes (with members) + relationships.

The graph topology can be laid out by the same Sugiyama engine used
for flowcharts; only the box-rendering differs (compartments for the
class name, attributes, and methods).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ClassEdgeKind(Enum):
    INHERITANCE = "inherits"        # `<|--`  hollow triangle
    COMPOSITION = "composes"        # `*--`   filled diamond
    AGGREGATION = "aggregates"      # `o--`   hollow diamond
    ASSOCIATION = "assoc"           # `-->`   plain arrow
    DEPENDENCY = "depends"          # `..>`   dashed arrow
    LINK = "link"                   # `--`    plain line, no arrow
    DASHED_LINK = "dashed_link"     # `..`    dashed line, no arrow
    BIDIRECTIONAL = "bidi"          # `<-->`  arrows both ends


@dataclass(frozen=True)
class ClassMember:
    """A field or method line inside a class box."""
    text: str            # raw text — display as-is, e.g. "+int chimp" or "size()"


@dataclass(frozen=True)
class ClassNode:
    id: str                                  # used by edges
    name: str                                # display name
    members: tuple[ClassMember, ...] = ()    # fields + methods, in source order


@dataclass(frozen=True)
class ClassEdge:
    src: str
    dst: str
    kind: ClassEdgeKind = ClassEdgeKind.ASSOCIATION
    label: str | None = None


@dataclass(frozen=True)
class ClassIR:
    nodes: tuple[ClassNode, ...]
    edges: tuple[ClassEdge, ...]
