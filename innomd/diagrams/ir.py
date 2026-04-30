"""Internal representation: format-agnostic graph description."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Direction(Enum):
    TD = "TD"   # top-down
    LR = "LR"   # left-right
    BT = "BT"   # bottom-top
    RL = "RL"   # right-left


class NodeShape(Enum):
    RECT = "rect"
    ROUND = "round"                # rounded corners — mermaid (text)
    STADIUM = "stadium"            # mermaid ([text])
    DIAMOND = "diamond"            # mermaid {text} — decision node
    HEXAGON = "hexagon"            # mermaid {{text}} — preparation step
    CIRCLE = "circle"              # mermaid ((text))
    PARALLELOGRAM = "parallel_r"   # mermaid [/text/] — right-leaning
    PARALLELOGRAM_ALT = "parallel_l"  # mermaid [\text\] — left-leaning
    TRAPEZOID = "trap_bb"          # mermaid [/text\] — bottom-wider trapezoid
    TRAPEZOID_INV = "trap_bt"      # mermaid [\text/] — top-wider trapezoid


class EdgeStyle(Enum):
    SOLID = "solid"
    DASHED = "dashed"
    THICK = "thick"


class ArrowStyle(Enum):
    NONE = "none"
    END = "end"
    BOTH = "both"


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    shape: NodeShape = NodeShape.RECT


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    label: str | None = None
    style: EdgeStyle = EdgeStyle.SOLID
    arrow: ArrowStyle = ArrowStyle.END


@dataclass(frozen=True)
class GraphIR:
    direction: Direction
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
