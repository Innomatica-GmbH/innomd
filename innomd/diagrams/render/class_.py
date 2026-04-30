"""Class diagram renderer.

Reuses the LayoutResult from compute_layout_class — node positions and
edge paths come straight from grandalf, but each box is drawn with three
compartments (name, separator, members) instead of a plain rect, and
edges carry decorations (hollow triangle for inheritance, filled diamond
for composition, etc.).
"""
from __future__ import annotations

from ..errors import RenderError
from ..ir_class import ClassEdgeKind, ClassNode
from ..layout.grandalf import EdgePath, LayoutResult, NodeBox
from .box import ASCII, UNICODE, Glyphs


_MIN_WIDTH = 20
_PADDING = 1


def render(layout: LayoutResult, *, width: int, ascii_only: bool = False) -> list[str]:
    glyphs = ASCII if ascii_only else UNICODE
    if width < _MIN_WIDTH:
        raise RenderError(f"width {width} below minimum {_MIN_WIDTH}")

    sx = sy = _pick_scale(layout, width)

    placed: list[_Placed] = []
    for nb in layout.nodes:
        bw = max(int(round(nb.w)), 8)
        bh = max(int(round(nb.h)), 4)
        cx = nb.cx * sx + _PADDING
        cy = nb.cy * sy + _PADDING
        x = int(round(cx - bw / 2))
        y = int(round(cy - bh / 2))
        placed.append(_Placed(nb=nb, x=x, y=y, w=bw, h=bh))

    # Shift to non-negative.
    min_x = min((p.x for p in placed), default=0)
    min_y = min((p.y for p in placed), default=0)
    shift_x = max(0, _PADDING - min_x)
    shift_y = max(0, _PADDING - min_y)
    if shift_x or shift_y:
        placed = [p._shift(shift_x, shift_y) for p in placed]

    edges_proj: list[tuple[EdgePath, list[tuple[int, int]]]] = []
    for ep in layout.edges:
        pts = [(int(round(x * sx + _PADDING)) + shift_x,
                int(round(y * sy + _PADDING)) + shift_y) for x, y in ep.points]
        edges_proj.append((ep, pts))

    canvas_w = max((p.x + p.w for p in placed), default=0) + _PADDING
    canvas_h = max((p.y + p.h for p in placed), default=0) + _PADDING
    for _, pts in edges_proj:
        for x, y in pts:
            canvas_w = max(canvas_w, x + 2)
            canvas_h = max(canvas_h, y + 2)
    if canvas_w > width:
        raise RenderError(f"diagram needs {canvas_w} cols, only {width} available")

    grid = [[" "] * canvas_w for _ in range(canvas_h)]

    # Draw edges (with their style: dashed for dependency).
    for ep, pts in edges_proj:
        _draw_class_edge(grid, pts, ep.edge.kind, glyphs)

    # Draw class boxes (overwrite edge cells inside boxes).
    for p in placed:
        _draw_class_box(grid, p, glyphs)

    # Place edge decorations (triangles, diamonds, arrows) at endpoints
    # last so they sit on top of node borders.
    for ep, pts in edges_proj:
        _decorate_endpoint(grid, pts, ep.edge.kind, glyphs, placed)

    return ["".join(row).rstrip() for row in grid]


# --- helpers --------------------------------------------------------------


class _Placed:
    __slots__ = ("nb", "x", "y", "w", "h")
    def __init__(self, nb, x, y, w, h):
        self.nb = nb; self.x = x; self.y = y; self.w = w; self.h = h
    def _shift(self, dx, dy):
        return _Placed(self.nb, self.x + dx, self.y + dy, self.w, self.h)
    def contains(self, x, y):
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h


def _pick_scale(layout: LayoutResult, width: int) -> float:
    if layout.width <= 0:
        return 1.0
    avail = max(width - 2 * _PADDING, _MIN_WIDTH)
    return min(avail / layout.width, 1.0)


def _put(grid, x, y, ch):
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        grid[y][x] = ch


def _draw_class_box(grid, p: _Placed, g: Glyphs) -> None:
    """Draw a class with three compartments: name, separator, members."""
    node: ClassNode = p.nb.node
    x, y, w, h = p.x, p.y, p.w, p.h
    # Outer box.
    _put(grid, x, y, g.tl)
    _put(grid, x + w - 1, y, g.tr)
    _put(grid, x, y + h - 1, g.bl)
    _put(grid, x + w - 1, y + h - 1, g.br)
    for i in range(1, w - 1):
        _put(grid, x + i, y, g.h)
        _put(grid, x + i, y + h - 1, g.h)
    for j in range(1, h - 1):
        _put(grid, x, y + j, g.v)
        _put(grid, x + w - 1, y + j, g.v)
        for i in range(1, w - 1):
            _put(grid, x + i, y + j, " ")
    # Class name centered on row 1.
    name_x = x + (w - len(node.name)) // 2
    for i, ch in enumerate(node.name):
        _put(grid, name_x + i, y + 1, ch)
    # Separator on row 2 — connects with side borders.
    if h >= 4 and node.members:
        sep_y = y + 2
        _put(grid, x, sep_y, g.t_right)
        _put(grid, x + w - 1, sep_y, g.t_left)
        for i in range(1, w - 1):
            _put(grid, x + i, sep_y, g.h)
        # Members from row 3 down.
        for k, m in enumerate(node.members):
            row = sep_y + 1 + k
            if row >= y + h - 1:
                break
            text = m.text
            for i, ch in enumerate(text[: w - 4]):
                _put(grid, x + 2 + i, row, ch)


def _draw_class_edge(grid, pts, kind: ClassEdgeKind, g: Glyphs) -> None:
    """Draw a polyline. Dashed for DEPENDENCY/DASHED_LINK; solid otherwise."""
    if len(pts) < 2:
        return
    is_dashed = kind in (ClassEdgeKind.DEPENDENCY, ClassEdgeKind.DASHED_LINK)
    h_glyph = g.h_dashed if is_dashed else g.h
    v_glyph = g.v_dashed if is_dashed else g.v
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 == x1:
            lo, hi = sorted((y0, y1))
            for y in range(lo, hi + 1):
                _overlay(grid, x0, y, v_glyph, g)
        elif y0 == y1:
            lo, hi = sorted((x0, x1))
            for x in range(lo, hi + 1):
                _overlay(grid, x, y0, h_glyph, g)
    # Corners at polyline joints.
    for prev, here, nxt in zip(pts, pts[1:], pts[2:]):
        _put_corner(grid, prev, here, nxt, g)


def _overlay(grid, x, y, ch, g: Glyphs) -> None:
    if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
        return
    cur = grid[y][x]
    if cur == " ":
        grid[y][x] = ch


def _put_corner(grid, prev, here, nxt, g: Glyphs) -> None:
    x, y = here
    if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
        return
    px, py = prev
    nx, ny = nxt
    came = "h" if py == y else "v"
    goes = "h" if ny == y else "v"
    if came == goes:
        return
    incoming = (1 if px < x else -1) if came == "h" else (1 if py < y else -1)
    outgoing = (1 if nx > x else -1) if goes == "h" else (1 if ny > y else -1)
    if came == "v" and goes == "h":
        if incoming == 1 and outgoing == 1:    grid[y][x] = g.rbl
        elif incoming == 1 and outgoing == -1: grid[y][x] = g.rbr
        elif incoming == -1 and outgoing == 1: grid[y][x] = g.rtl
        else:                                  grid[y][x] = g.rtr
    else:
        if incoming == 1 and outgoing == 1:    grid[y][x] = g.rtr
        elif incoming == 1 and outgoing == -1: grid[y][x] = g.rbr
        elif incoming == -1 and outgoing == 1: grid[y][x] = g.rtl
        else:                                  grid[y][x] = g.rbl


def _decorate_endpoint(grid, pts, kind: ClassEdgeKind, g: Glyphs, placed) -> None:
    """Stamp an end-decoration on the appropriate side of the path.

    UML places the decoration on the side that semantically owns it:
       INHERITANCE  → at PARENT side (= source, top)  — △ hollow triangle
       COMPOSITION  → at WHOLE side  (= source, top)  — ◆ filled diamond
       AGGREGATION  → at WHOLE side  (= source, top)  — ◇ hollow diamond
       ASSOCIATION  → at TARGET side (arrow head)     — ▶/◀/▲/▼
       DEPENDENCY   → at TARGET side                  — ▶ (dashed line cues it)
       BIDIRECTIONAL → arrows at both ends
       LINK / DASHED_LINK → no decoration
    """
    if len(pts) < 2:
        return

    decorate_source = kind in (
        ClassEdgeKind.INHERITANCE,
        ClassEdgeKind.COMPOSITION,
        ClassEdgeKind.AGGREGATION,
    )
    decorate_target = kind in (
        ClassEdgeKind.ASSOCIATION,
        ClassEdgeKind.DEPENDENCY,
        ClassEdgeKind.BIDIRECTIONAL,
    )

    if decorate_source:
        # Direction is the side the path APPROACHES the source from
        # (i.e. opposite of departure). The decoration sits at the cell
        # adjacent to the source box — we reuse pts[0] as that cell.
        sx, sy = pts[0]
        idx = 1
        while idx < len(pts) and pts[idx] == (sx, sy):
            idx += 1
        if idx < len(pts):
            nx, ny = pts[idx]
            # Departure direction → glyph points back toward source.
            if nx > sx:    direction = "left"
            elif nx < sx: direction = "right"
            elif ny > sy: direction = "up"
            else:         direction = "down"
            glyph = _decoration_glyph(kind, direction)
            if glyph:
                _put(grid, sx, sy, glyph)

    if decorate_target:
        x1, y1 = pts[-1]
        idx = len(pts) - 2
        while idx >= 0 and pts[idx] == (x1, y1):
            idx -= 1
        if idx >= 0:
            x0, y0 = pts[idx]
            if x1 > x0:    direction = "right"
            elif x1 < x0: direction = "left"
            elif y1 > y0: direction = "down"
            else:         direction = "up"
            glyph = _decoration_glyph(kind, direction)
            if glyph:
                _put(grid, x1, y1, glyph)
        # Bidirectional: also stamp at source.
        if kind == ClassEdgeKind.BIDIRECTIONAL:
            sx, sy = pts[0]
            idx2 = 1
            while idx2 < len(pts) and pts[idx2] == (sx, sy):
                idx2 += 1
            if idx2 < len(pts):
                nx, ny = pts[idx2]
                if nx > sx:    src_dir = "left"
                elif nx < sx: src_dir = "right"
                elif ny > sy: src_dir = "up"
                else:         src_dir = "down"
                src_glyph = _decoration_glyph(ClassEdgeKind.ASSOCIATION, src_dir)
                if src_glyph:
                    _put(grid, sx, sy, src_glyph)


def _decoration_glyph(kind: ClassEdgeKind, direction: str) -> str | None:
    """Return the end-glyph for an edge approaching from `direction`."""
    if kind == ClassEdgeKind.INHERITANCE:
        return {"up": "△", "down": "▽", "left": "◁", "right": "▷"}.get(direction)
    if kind == ClassEdgeKind.COMPOSITION:
        return "◆"
    if kind == ClassEdgeKind.AGGREGATION:
        return "◇"
    if kind in (ClassEdgeKind.ASSOCIATION, ClassEdgeKind.DEPENDENCY,
                ClassEdgeKind.BIDIRECTIONAL):
        return {"up": "▲", "down": "▼", "left": "◀", "right": "▶"}.get(direction)
    return None
