"""GraphIR → LayoutResult via grandalf's Sugiyama layered layout.

Grandalf returns center coordinates per node. We do edge routing ourselves
(orthogonal segments) because grandalf's spline output is awkward to map
onto a character grid and orthogonal routing reads better in ASCII anyway.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..errors import LayoutError
from ..ir import Direction, Edge, GraphIR, Node


# Logical box sizes used during layout. The renderer rescales everything
# to the target terminal width, so the absolute values matter only for
# the *ratios* between nodes and the spacing grandalf produces.
_DEFAULT_W = 12
_DEFAULT_H = 4


@dataclass(frozen=True)
class NodeBox:
    node: Node
    cx: float       # center x in layout units
    cy: float       # center y
    w: float
    h: float


@dataclass(frozen=True)
class EdgePath:
    edge: Edge
    points: tuple[tuple[float, float], ...]   # polyline (≥ 2 points)


@dataclass(frozen=True)
class LayoutResult:
    ir: GraphIR
    nodes: tuple[NodeBox, ...]
    edges: tuple[EdgePath, ...]
    width: float           # bounding box width in layout units
    height: float          # bounding box height in layout units


_RHOMBUS_LABEL_LIMIT = 6  # max single-line label length for true rhombus diamond


def compute_layout_class(ir):
    """Layout a ClassIR using the same Sugiyama engine as flowcharts.

    Returns a LayoutResult whose nodes carry the original ClassNode in
    `node` (instead of an `ir.Node`), and whose box dimensions account
    for the class name + member compartments. The class-specific renderer
    reads those dimensions to draw class boxes.
    """
    from ..ir_class import ClassIR
    from ..ir import Direction
    from ..errors import LayoutError
    if not ir.nodes:
        raise LayoutError("no classes")
    try:
        from grandalf.graphs import Edge as GEdge, Graph, Vertex
        from grandalf.layouts import SugiyamaLayout
    except ImportError as exc:
        raise LayoutError(f"grandalf not available: {exc}") from exc

    def class_dims(node):
        # Width: longest of class name and member text, +4 for padding.
        longest = max(
            [len(node.name)] + [len(m.text) for m in node.members], default=0
        )
        w = max(_DEFAULT_W, longest + 4)
        # Height: 1 row name + separator + members + 2 borders + 1 pad
        members_h = len(node.members)
        if members_h == 0:
            h = 4
        else:
            h = 4 + members_h    # top border + name row + sep + members + bot border
        return w, h

    vertices: dict[str, Vertex] = {}
    natural: dict[str, tuple[int, int]] = {}
    for n in ir.nodes:
        v = Vertex(n.id)
        w, h = class_dims(n)
        natural[n.id] = (w, h)

        class _View:
            __slots__ = ("w", "h", "xy")
            def __init__(self, w, h):
                self.w = w; self.h = h; self.xy = (0.0, 0.0)
        v.view = _View(w, h)
        v.data = n
        vertices[n.id] = v

    g_edges = []
    for e in ir.edges:
        if e.src in vertices and e.dst in vertices:
            g_edges.append(GEdge(vertices[e.src], vertices[e.dst]))

    g = Graph(list(vertices.values()), g_edges)
    # Lay out each connected component independently with TD Sugiyama,
    # then SHELF-PACK the components left-to-right. Class diagrams typically
    # have many small components (just a parent/child pair, etc.); stacking
    # all of them in a single column wastes horizontal space.
    component_layouts: list[tuple[list[NodeBox], float, float]] = []
    for comp in g.C:
        sug = SugiyamaLayout(comp)
        sug.xspace = 4
        sug.yspace = 4
        sug.init_all()
        try:
            sug.draw()
        except Exception as exc:
            raise LayoutError(f"sugiyama layout failed: {exc}") from exc
        if not comp.sV:
            continue
        # First pass: collect raw centers into NodeBoxes.
        raw: list[NodeBox] = []
        for v in comp.sV:
            cx = v.view.xy[0]
            cy = v.view.xy[1]
            nat_w, nat_h = natural[v.data.id]
            raw.append(NodeBox(node=v.data, cx=cx, cy=cy, w=nat_w, h=nat_h))
        # Second pass: normalize so leftmost EDGE sits at x=0 and topmost
        # EDGE sits at y=0 — using box edges, not just centers.
        min_left = min(nb.cx - nb.w / 2 for nb in raw)
        min_top = min(nb.cy - nb.h / 2 for nb in raw)
        comp_nodes = [
            NodeBox(node=nb.node, cx=nb.cx - min_left, cy=nb.cy - min_top,
                    w=nb.w, h=nb.h)
            for nb in raw
        ]
        comp_w = max(nb.cx + nb.w / 2 for nb in comp_nodes)
        comp_h = max(nb.cy + nb.h / 2 for nb in comp_nodes)
        component_layouts.append((comp_nodes, comp_w, comp_h))

    # Shelf-pack components into rows. Use a generous row width so even
    # mid-sized class diagrams fit on one row before wrapping.
    SHELF_WIDTH = 100.0
    GAP_X = 6.0
    GAP_Y = _DEFAULT_H
    laid: list[NodeBox] = []
    cur_x = 0.0
    cur_y = 0.0
    row_h = 0.0
    for nodes, w, h in component_layouts:
        if cur_x > 0 and cur_x + w > SHELF_WIDTH:
            # Wrap to next shelf.
            cur_x = 0.0
            cur_y += row_h + GAP_Y
            row_h = 0.0
        for nb in nodes:
            laid.append(NodeBox(node=nb.node, cx=nb.cx + cur_x,
                                cy=nb.cy + cur_y, w=nb.w, h=nb.h))
        cur_x += w + GAP_X
        row_h = max(row_h, h)

    # Route edges (orthogonal, like in compute_layout).
    by_id = {nb.node.id: nb for nb in laid}
    paths = []
    for e in ir.edges:
        if e.src in by_id and e.dst in by_id:
            paths.append(EdgePath(edge=e, points=_route(by_id[e.src], by_id[e.dst], Direction.TD)))

    nodes_t = tuple(laid)
    edges_t = tuple(paths)

    # Shift to non-negative.
    if nodes_t:
        min_left = min(nb.cx - nb.w / 2 for nb in nodes_t)
        min_top = min(nb.cy - nb.h / 2 for nb in nodes_t)
        if min_left < 0 or min_top < 0:
            dx = -min_left if min_left < 0 else 0.0
            dy = -min_top if min_top < 0 else 0.0
            nodes_t = tuple(NodeBox(node=nb.node, cx=nb.cx + dx, cy=nb.cy + dy,
                                    w=nb.w, h=nb.h) for nb in nodes_t)
            edges_t = tuple(EdgePath(edge=ep.edge,
                                     points=tuple((x + dx, y + dy) for x, y in ep.points))
                            for ep in edges_t)
        max_x = max(nb.cx + nb.w / 2 for nb in nodes_t)
        max_y = max(nb.cy + nb.h / 2 for nb in nodes_t)
    else:
        max_x = max_y = 0.0

    # Synthetic IR for the LayoutResult; renderer ignores .ir except for
    # an existence check, so a thin ClassIR shim is fine.
    return LayoutResult(ir=ir, nodes=nodes_t, edges=edges_t,
                        width=max_x, height=max_y)


def _node_dims(label: str, shape: "NodeShape | None" = None) -> tuple[int, int]:
    # Width grows with the longest label line; +4 for "│ … │" padding.
    from ..ir import NodeShape  # late import to avoid cycle
    lines = label.splitlines() or [label]
    longest = max((len(ln) for ln in lines), default=0)
    # True rhombus for short DIAMOND labels — pure ╱╲, no horizontals.
    # Width = M+2 (or M+3 for odd M to keep h odd / single widest row),
    # Height = M+1 (or M+2). For longer labels we fall back to the heavy
    # box rendering, which doesn't grow vertically with label length.
    if (shape == NodeShape.DIAMOND
            and len(lines) == 1
            and 1 <= longest <= _RHOMBUS_LABEL_LIMIT):
        # k_widest = number of rows from apex to widest row
        # widest row has inner space = 2*k_widest, must fit the label
        k_widest = max(1, (longest + 1) // 2)
        return 2 * k_widest + 2, 2 * k_widest + 1
    w = max(_DEFAULT_W, longest + 4)
    h = max(_DEFAULT_H, len(lines) + 2)
    # Parallelograms physically slant — the rendered shape is `(h-1)` cells
    # wider than the rectangular label area so the offset rows actually fit.
    if shape in (NodeShape.PARALLELOGRAM, NodeShape.PARALLELOGRAM_ALT):
        w += h - 1
    # Trapezoids dedicate one row to the narrow horizontal cap, separate
    # from the slope row, so the shape reads cleanly.
    if shape in (NodeShape.TRAPEZOID, NodeShape.TRAPEZOID_INV):
        h += 1
    return w, h


def compute_layout(ir: GraphIR) -> LayoutResult:
    if not ir.nodes:
        raise LayoutError("graph has no nodes")

    try:
        from grandalf.graphs import Edge as GEdge, Graph, Vertex
        from grandalf.layouts import SugiyamaLayout
    except ImportError as exc:
        raise LayoutError(f"grandalf not available: {exc}") from exc

    # Build grandalf graph. grandalf always lays out top-down internally;
    # we rotate the result afterwards for LR / BT / RL.
    #
    # For LR/RL we want the screen-rendered boxes to keep their natural
    # horizontal orientation (wide-and-short labels), so during layout
    # we swap w/h — telling grandalf that nodes are "tall" — and the
    # subsequent rotation maps that "tallness" back into the across-layer
    # axis on screen.
    rotated = ir.direction in (Direction.LR, Direction.RL)
    vertices: dict[str, Vertex] = {}
    natural_dims: dict[str, tuple[int, int]] = {}
    for n in ir.nodes:
        v = Vertex(n.id)
        w, h = _node_dims(n.label, n.shape)
        natural_dims[n.id] = (w, h)

        class _View:
            __slots__ = ("w", "h", "xy")

            def __init__(self, w: int, h: int) -> None:
                self.w = w
                self.h = h
                self.xy = (0.0, 0.0)

        if rotated:
            v.view = _View(h, w)   # swap so layer-axis spacing accounts for box width
        else:
            v.view = _View(w, h)
        v.data = n
        vertices[n.id] = v

    g_edges = []
    for e in ir.edges:
        if e.src not in vertices or e.dst not in vertices:
            raise LayoutError(f"edge references unknown node: {e.src} -> {e.dst}")
        g_edges.append(GEdge(vertices[e.src], vertices[e.dst]))

    g = Graph(list(vertices.values()), g_edges)

    # Sugiyama processes one connected component at a time.
    component_offset_y = 0.0
    laid_nodes: list[NodeBox] = []
    for comp in g.C:
        sug = SugiyamaLayout(comp)
        # grandalf defaults to xspace=20, yspace=20, which is generous for
        # screen rendering and crushing for terminal cells. Tightening these
        # is the single biggest visual improvement here.
        # Layout coordinates are produced in terminal-cell units (the
        # renderer does not apply additional aspect-ratio correction).
        # xspace/yspace are the pad between adjacent nodes inside a layer
        # and between layers respectively; tuned for legible-but-compact
        # terminal output.
        sug.xspace = 4
        # yspace=4 leaves enough vertical room (after the +1/-1 endpoint
        # shift in _route) for the arrow tip to sit cleanly outside the
        # target box and for the bend midpoint to round to a different
        # row than the endpoint.
        sug.yspace = 4
        sug.init_all()
        try:
            sug.draw()
        except Exception as exc:  # grandalf throws assorted internal errors
            raise LayoutError(f"sugiyama layout failed: {exc}") from exc

        # Collect nodes in this component, normalized to local origin.
        xs = [v.view.xy[0] for v in comp.sV]
        ys = [v.view.xy[1] for v in comp.sV]
        if not xs:
            continue
        min_x = min(xs)
        min_y = min(ys)
        for v in comp.sV:
            cx = v.view.xy[0] - min_x
            cy = v.view.xy[1] - min_y + component_offset_y
            # Always store boxes with their natural (visual) dimensions,
            # regardless of any pre-layout swap we did for LR/RL.
            nat_w, nat_h = natural_dims[v.data.id]
            laid_nodes.append(NodeBox(node=v.data, cx=cx, cy=cy,
                                      w=nat_w, h=nat_h))
        # Stack components vertically.
        comp_h = (max(ys) - min_y) + max((v.view.h for v in comp.sV), default=0)
        component_offset_y += comp_h + _DEFAULT_H

    # Index for orthogonal edge routing.
    by_id = {nb.node.id: nb for nb in laid_nodes}
    paths: list[EdgePath] = []
    for e in ir.edges:
        a = by_id[e.src]
        b = by_id[e.dst]
        paths.append(EdgePath(edge=e, points=_route(a, b, ir.direction)))

    nodes_t = tuple(laid_nodes)
    edges_t = tuple(paths)

    # Rotate first so the bounding-box correction below operates on
    # post-rotation (= screen) coordinates and box dimensions, not the
    # layout-internal ones that may have been swapped for LR/RL.
    if ir.direction in (Direction.LR, Direction.RL, Direction.BT):
        nodes_t, edges_t, _, _ = _rotate(
            nodes_t, edges_t, 0.0, 0.0, ir.direction
        )

    # Shift everything so the leftmost / topmost box edges sit at 0.
    # Sugiyama centers nodes around 0; without this fix, wide boxes would
    # have negative left edges and the renderer's bbox would under-report
    # the true extent (or, after the rotation above, push the diagram down
    # by half its width worth of empty rows).
    if nodes_t:
        min_left = min(nb.cx - nb.w / 2 for nb in nodes_t)
        min_top = min(nb.cy - nb.h / 2 for nb in nodes_t)
        if min_left < 0 or min_top < 0:
            dx = -min_left if min_left < 0 else 0.0
            dy = -min_top if min_top < 0 else 0.0
            nodes_t = tuple(
                NodeBox(node=nb.node, cx=nb.cx + dx, cy=nb.cy + dy,
                        w=nb.w, h=nb.h)
                for nb in nodes_t
            )
            edges_t = tuple(
                EdgePath(edge=ep.edge,
                         points=tuple((x + dx, y + dy) for x, y in ep.points))
                for ep in edges_t
            )
        max_x = max(nb.cx + nb.w / 2 for nb in nodes_t)
        max_y = max(nb.cy + nb.h / 2 for nb in nodes_t)
    else:
        max_x = max_y = 0.0

    return LayoutResult(ir=ir, nodes=nodes_t, edges=edges_t,
                        width=max_x, height=max_y)


def _route(a: NodeBox, b: NodeBox, direction: Direction) -> tuple[tuple[float, float], ...]:
    """Orthogonal route from a's exit side to b's entry side.

    grandalf always lays out top-down internally. We exit one row below
    the source box and enter one row above the target box, so the arrow
    tip lands cleanly OUTSIDE the box border (touching but not on it).
    The bend row uses an integer in the upper third of the path range,
    which keeps the final descent ≥1 cell after rounding.
    """
    sx, sy = a.cx, a.cy + a.h / 2       # path starts touching source bottom
    tx, ty = b.cx, b.cy - b.h / 2 - 1   # one row above target box (arrow tip)
    if abs(sx - tx) < 0.5 or sy >= ty:
        return ((sx, sy), (tx, ty))
    # Snap the bend to an integer row strictly above ty, so the final
    # descent is at least one cell long and the arrow direction is
    # unambiguous after rounding.
    import math
    mid_y = math.floor((sy + ty) / 2.0)
    if mid_y >= ty:
        mid_y = ty - 1
    if mid_y <= sy:
        mid_y = sy + 1 if sy + 1 < ty else sy
    return ((sx, sy), (sx, mid_y), (tx, mid_y), (tx, ty))


def _rotate(nodes: tuple[NodeBox, ...], edges: tuple[EdgePath, ...],
            w: float, h: float, direction: Direction
            ) -> tuple[tuple[NodeBox, ...], tuple[EdgePath, ...], float, float]:
    """Map TD coordinates to LR/RL/BT.

    LR: swap (x, y) and (w, h).
    BT: flip y around max_y.
    RL: LR + flip x.
    """
    def map_point(x: float, y: float) -> tuple[float, float]:
        if direction == Direction.LR:
            return (y, x)
        if direction == Direction.RL:
            return (h - y, x)
        if direction == Direction.BT:
            return (x, h - y)
        return (x, y)

    new_nodes = []
    for nb in nodes:
        cx, cy = map_point(nb.cx, nb.cy)
        # Box dimensions are kept as their natural (visual) values.
        new_nodes.append(NodeBox(node=nb.node, cx=cx, cy=cy,
                                 w=nb.w, h=nb.h))

    new_edges = []
    for ep in edges:
        new_pts = tuple(map_point(x, y) for x, y in ep.points)
        new_edges.append(EdgePath(edge=ep.edge, points=new_pts))

    if direction in (Direction.LR, Direction.RL):
        new_w, new_h = h, w
    else:
        new_w, new_h = w, h
    return tuple(new_nodes), tuple(new_edges), new_w, new_h
