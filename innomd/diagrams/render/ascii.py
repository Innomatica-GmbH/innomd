"""LayoutResult → list[str] (terminal lines).

Pipeline:
  1. Pick a target column count (≤ width). Scale the layout's logical units
     so the bounding box fits, taking aspect ratio into account (terminal
     cells are roughly twice as tall as they are wide).
  2. Draw nodes onto a 2D char grid.
  3. Draw edges as orthogonal polylines, then place arrowheads.
"""
from __future__ import annotations

from ..errors import RenderError
from ..ir import ArrowStyle, EdgeStyle, NodeShape
from ..layout.grandalf import EdgePath, LayoutResult, NodeBox
from .box import ASCII, UNICODE, Glyphs


_MIN_WIDTH = 20
_PADDING = 1            # blank cells around the bounding box


def render(layout: LayoutResult, *, width: int, ascii_only: bool = False) -> list[str]:
    glyphs = ASCII if ascii_only else UNICODE
    if width < _MIN_WIDTH:
        raise RenderError(f"target width {width} below minimum {_MIN_WIDTH}")

    # Scale: logical x/y → cell columns/rows.
    # We keep node sizes (already in logical units that roughly equal cells)
    # and only scale the *layout coordinates* — the node-internal padding
    # is fixed for legibility.
    sx, sy = _pick_scales(layout, width)

    # Project nodes to integer cell rectangles.
    placed: list[_PlacedNode] = []
    for nb in layout.nodes:
        bw = max(int(round(nb.w)), 5)  # min box width to fit corners + glyph
        bh = max(int(round(nb.h)), 3)
        # Convert center to top-left.
        cx = nb.cx * sx + _PADDING
        cy = nb.cy * sy + _PADDING
        x = int(round(cx - bw / 2))
        y = int(round(cy - bh / 2))
        placed.append(_PlacedNode(nb=nb, x=x, y=y, w=bw, h=bh))

    # Resolve any negative coordinates from rounding.
    min_x = min((p.x for p in placed), default=0)
    min_y = min((p.y for p in placed), default=0)
    if min_x < _PADDING:
        shift = _PADDING - min_x
        placed = [p._shift(dx=shift, dy=0) for p in placed]
    if min_y < _PADDING:
        shift = _PADDING - min_y
        placed = [p._shift(dx=0, dy=shift) for p in placed]

    # Project edges using the same scale.
    edges_proj: list[tuple[EdgePath, list[tuple[int, int]]]] = []
    for ep in layout.edges:
        pts = [(int(round(x * sx + _PADDING)),
                int(round(y * sy + _PADDING))) for x, y in ep.points]
        if min_x < _PADDING:
            pts = [(x + (_PADDING - min_x), y) for x, y in pts]
        if min_y < _PADDING:
            pts = [(x, y + (_PADDING - min_y)) for x, y in pts]
        edges_proj.append((ep, pts))

    # Compute canvas size.
    canvas_w = max((p.x + p.w for p in placed), default=0)
    canvas_h = max((p.y + p.h for p in placed), default=0)
    for _, pts in edges_proj:
        for x, y in pts:
            if x + 1 > canvas_w:
                canvas_w = x + 1
            if y + 1 > canvas_h:
                canvas_h = y + 1
    canvas_w += _PADDING
    canvas_h += _PADDING

    if canvas_w > width:
        raise RenderError(f"diagram needs {canvas_w} cols, only {width} available")

    grid = [[" "] * canvas_w for _ in range(canvas_h)]

    # Draw edges first so node borders sit on top of any overlapping line.
    for ep, pts in edges_proj:
        _draw_edge(grid, pts, ep.edge.style, ep.edge.arrow,
                   ep.edge.label, glyphs)

    # Snip edge endpoints that ran into a node body — replace with box border.
    for p in placed:
        _draw_node(grid, p, glyphs)

    # Place arrowheads last so they aren't overdrawn by node borders.
    for ep, pts in edges_proj:
        _draw_arrow(grid, pts, ep.edge.arrow, glyphs, placed)

    return ["".join(row).rstrip() for row in grid]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class _PlacedNode:
    __slots__ = ("nb", "x", "y", "w", "h")

    def __init__(self, nb: NodeBox, x: int, y: int, w: int, h: int) -> None:
        self.nb = nb
        self.x = x
        self.y = y
        self.w = w
        self.h = h

    def _shift(self, dx: int, dy: int) -> "_PlacedNode":
        return _PlacedNode(self.nb, self.x + dx, self.y + dy, self.w, self.h)

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def on_border(self, x: int, y: int) -> bool:
        return self.contains(x, y) and (
            x == self.x or x == self.x + self.w - 1
            or y == self.y or y == self.y + self.h - 1
        )


def _pick_scales(layout: LayoutResult, width: int) -> tuple[float, float]:
    """Pick uniform scaling so the layout fits within `width` columns.

    Aspect ratio is preserved (uniform scale on both axes), then y is further
    multiplied by _CELL_ASPECT at projection time so vertical spacing in
    cells looks natural.
    """
    if layout.width <= 0:
        return 1.0, 1.0
    avail = max(width - 2 * _PADDING, _MIN_WIDTH)
    sx = avail / layout.width
    # No upscaling beyond 1.0 — the layout's units are already roughly cell-
    # sized, so a small graph shouldn't be stretched across the whole row.
    sx = min(sx, 1.0)
    return sx, sx


def _put(grid: list[list[str]], x: int, y: int, ch: str) -> None:
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        grid[y][x] = ch


def _draw_node(grid: list[list[str]], p: _PlacedNode, g: Glyphs) -> None:
    shape = p.nb.node.shape
    label_lines = _wrap_label(p.nb.node.label, p.w - 4)

    if shape == NodeShape.DIAMOND:
        _draw_diamond(grid, p, label_lines, g)
        return
    if shape == NodeShape.HEXAGON:
        _draw_hexagon(grid, p, label_lines, g)
        return
    if shape == NodeShape.CIRCLE:
        _draw_circle(grid, p, label_lines, g)
        return
    if shape in (NodeShape.TRAPEZOID, NodeShape.TRAPEZOID_INV):
        _draw_trapezoid(grid, p, label_lines, g, inverted=(shape == NodeShape.TRAPEZOID_INV))
        return
    if shape in (NodeShape.PARALLELOGRAM, NodeShape.PARALLELOGRAM_ALT):
        _draw_parallelogram(grid, p, label_lines, g, lean_left=(shape == NodeShape.PARALLELOGRAM_ALT))
        return

    # RECT / ROUND / STADIUM share the basic box mechanic.
    # Corners differentiate RECT (sharp) from ROUND/STADIUM (rounded).
    # STADIUM additionally swaps the side glyphs for parentheses, which is
    # the conventional "capsule/pill" rendering and makes it readable as a
    # different shape from ROUND in flowcharts that mix both.
    if shape == NodeShape.STADIUM:
        tl, tr, bl, br = g.rtl, g.rtr, g.rbl, g.rbr
        side_left = "(" if g is UNICODE else "("
        side_right = ")" if g is UNICODE else ")"
    elif shape == NodeShape.ROUND:
        tl, tr, bl, br = g.rtl, g.rtr, g.rbl, g.rbr
        side_left = side_right = g.v
    else:
        tl, tr, bl, br = g.tl, g.tr, g.bl, g.br
        side_left = side_right = g.v

    x, y, w, h = p.x, p.y, p.w, p.h
    _put(grid, x, y, tl)
    _put(grid, x + w - 1, y, tr)
    _put(grid, x, y + h - 1, bl)
    _put(grid, x + w - 1, y + h - 1, br)
    for i in range(1, w - 1):
        _put(grid, x + i, y, g.h)
        _put(grid, x + i, y + h - 1, g.h)
    for j in range(1, h - 1):
        _put(grid, x, y + j, side_left)
        _put(grid, x + w - 1, y + j, side_right)
    # Clear interior, then write label.
    for j in range(1, h - 1):
        for i in range(1, w - 1):
            _put(grid, x + i, y + j, " ")
    _write_label(grid, x, y, w, h, label_lines)


def _draw_box_with_chars(grid: list[list[str]], x: int, y: int, w: int, h: int,
                         tl: str, tr: str, bl: str, br: str,
                         horiz: str, vert: str) -> None:
    """Generic clean rectangular box draw with the given corner & edge chars."""
    _put(grid, x, y, tl)
    _put(grid, x + w - 1, y, tr)
    _put(grid, x, y + h - 1, bl)
    _put(grid, x + w - 1, y + h - 1, br)
    for i in range(1, w - 1):
        _put(grid, x + i, y, horiz)
        _put(grid, x + i, y + h - 1, horiz)
    for j in range(1, h - 1):
        _put(grid, x, y + j, vert)
        _put(grid, x + w - 1, y + j, vert)
        for i in range(1, w - 1):
            _put(grid, x + i, y + j, " ")


def _draw_diamond(grid: list[list[str]], p: _PlacedNode,
                  label_lines: list[str], g: Glyphs) -> None:
    """Render a decision diamond.

    For short single-line labels (≤6 chars) we draw a TRUE rhombus using
    only ╱ and ╲ — no horizontals or verticals, so every diagonal connects
    cleanly to its neighbours along the slope.

    For longer labels a true rhombus would be too tall (height grows with
    label length), so we fall back to a HEAVY-bordered box (┏━┓ ┗━┛) —
    geometrically rectangular but its thicker stroke clearly separates it
    from RECT/ROUND while every junction connects cleanly.

         ╱╲                ┏━━━━━━━━━━┓
        ╱  ╲               ┃ Choice?  ┃
       ╱test╲              ┃          ┃
        ╲  ╱               ┗━━━━━━━━━━┛
         ╲╱
        rhombus            heavy box (long label)
    """
    x, y, w, h = p.x, p.y, p.w, p.h
    # _node_dims signals "render as rhombus" by emitting w == h+1, odd h.
    is_rhombus = (h >= 3 and h % 2 == 1 and w == h + 1)
    if is_rhombus:
        _draw_rhombus(grid, p, label_lines, g)
        return
    if h < 3 or w < 5:
        _draw_plain_box(grid, x, y, w, h, g)
    else:
        _draw_box_with_chars(grid, x, y, w, h,
                             g.tl_heavy, g.tr_heavy, g.bl_heavy, g.br_heavy,
                             g.h_heavy, g.v_heavy)
    _write_label(grid, x, y, w, h, label_lines)


def _draw_rhombus(grid: list[list[str]], p: _PlacedNode,
                  label_lines: list[str], g: Glyphs) -> None:
    """True diamond rhombus — only ╱ and ╲ glyphs, all connections clean.

    Each row's slope endpoints land exactly on the next row's slope start
    points (because consecutive ╱ at offset cells share a corner), so the
    shape draws as one continuous outline.  The widest row sits in the
    middle and holds the label.
    """
    x, y, w, h = p.x, p.y, p.w, p.h
    nw = g.diamond_top    # ╱
    ne = g.diamond_left   # ╲
    # cx is the LEFT cell of the apex pair; the apex spans cols cx and cx+1.
    cx = x + w // 2 - 1
    mid = h // 2          # widest row index (h is odd)

    for k in range(h):
        if k <= mid:
            # Upper half: row width = 2 + 2k.
            d = k
            left_glyph, right_glyph = nw, ne     # ╱ on left, ╲ on right
        else:
            # Lower half: distance from bottom apex.
            d = h - 1 - k
            left_glyph, right_glyph = ne, nw     # ╲ on left, ╱ on right
        left = cx - d
        right = cx + d + 1
        _put(grid, left, y + k, left_glyph)
        _put(grid, right, y + k, right_glyph)
        for i in range(left + 1, right):
            _put(grid, i, y + k, " ")

    # Place the original (un-wrapped) label centered on the widest row —
    # the layout module already sized the rhombus to fit it. The pre-wrapped
    # `label_lines` would over-wrap because it uses the rect inner-width
    # heuristic (w-4), which doesn't match a rhombus's geometry.
    label = p.nb.node.label.strip().replace("\n", " ")
    inner_w = 2 * mid     # cells between the slopes on the widest row
    label_left = cx - mid + 1
    label_x = label_left + max(0, (inner_w - len(label)) // 2)
    for i, ch in enumerate(label):
        _put(grid, label_x + i, y + mid, ch)


def _draw_hexagon(grid: list[list[str]], p: _PlacedNode,
                  label_lines: list[str], g: Glyphs) -> None:
    """Render a hexagon (mermaid `{{text}}`) as a DOUBLE-line box.

    Same reasoning as DIAMOND — diagonal corner glyphs don't connect.
    Double-line box-drawing chars (═ ║ ╔ ╗ ╚ ╝) form a parallel-stroke
    border that is unambiguously different from both single-line RECT/ROUND
    and from the heavy DIAMOND.

         ╔══════════╗     double line = preparation/data
         ║   text   ║
         ║          ║
         ╚══════════╝
    """
    x, y, w, h = p.x, p.y, p.w, p.h
    if h < 3 or w < 5:
        _draw_plain_box(grid, x, y, w, h, g)
    else:
        _draw_box_with_chars(grid, x, y, w, h,
                             g.tl_double, g.tr_double, g.bl_double, g.br_double,
                             g.h_double, g.v_double)
    _write_label(grid, x, y, w, h, label_lines)


def _draw_plain_box(grid: list[list[str]], x: int, y: int, w: int, h: int,
                    g: Glyphs) -> None:
    """Sharp-cornered rect — used as a fallback when a shape is too small."""
    for i in range(1, w - 1):
        _put(grid, x + i, y, g.h)
        _put(grid, x + i, y + h - 1, g.h)
    for j in range(h):
        _put(grid, x, y + j, g.v)
        _put(grid, x + w - 1, y + j, g.v)
    _put(grid, x, y, g.tl)
    _put(grid, x + w - 1, y, g.tr)
    _put(grid, x, y + h - 1, g.bl)
    _put(grid, x + w - 1, y + h - 1, g.br)


def _draw_circle(grid: list[list[str]], p: _PlacedNode,
                 label_lines: list[str], g: Glyphs) -> None:
    """Render an approximate circle: rounded corners + indented top & bottom.

    The top and bottom rows are inset by 1 cell on each side so the box
    looks "rounded" overall rather than rectangular. Distinguishes from
    ROUND (which only has soft corners) and STADIUM (which uses parens).

         ╭────╮
        ╱      ╲
        │ text │
        ╲      ╱
         ╰────╯
    """
    x, y, w, h = p.x, p.y, p.w, p.h
    if h < 4 or w < 6:
        # Not enough room for the rounded look — fall back to a soft-cornered
        # box (visually similar to ROUND, but the layout was constrained).
        for i in range(1, w - 1):
            _put(grid, x + i, y, g.h)
            _put(grid, x + i, y + h - 1, g.h)
        for j in range(0, h):
            _put(grid, x, y + j, g.v)
            _put(grid, x + w - 1, y + j, g.v)
        _put(grid, x, y, g.rtl)
        _put(grid, x + w - 1, y, g.rtr)
        _put(grid, x, y + h - 1, g.rbl)
        _put(grid, x + w - 1, y + h - 1, g.rbr)
        _write_label(grid, x, y, w, h, label_lines)
        return

    # Top: indented row with rounded ends.
    _put(grid, x + 1, y, g.rtl)
    _put(grid, x + w - 2, y, g.rtr)
    for i in range(x + 2, x + w - 2):
        _put(grid, i, y, g.h)
    # Row 1 (just below top): outward slopes connecting top to body.
    _put(grid, x, y + 1, g.diamond_top)         # ╱
    _put(grid, x + w - 1, y + 1, g.diamond_left)  # ╲
    for i in range(x + 1, x + w - 1):
        _put(grid, i, y + 1, " ")
    # Body rows: vertical sides.
    for k in range(2, h - 2):
        _put(grid, x, y + k, g.v)
        _put(grid, x + w - 1, y + k, g.v)
        for i in range(x + 1, x + w - 1):
            _put(grid, i, y + k, " ")
    # Row h-2: inward slopes (mirror of row 1).
    _put(grid, x, y + h - 2, g.diamond_left)    # ╲
    _put(grid, x + w - 1, y + h - 2, g.diamond_top)  # ╱
    for i in range(x + 1, x + w - 1):
        _put(grid, i, y + h - 2, " ")
    # Bottom: indented row with rounded ends.
    _put(grid, x + 1, y + h - 1, g.rbl)
    _put(grid, x + w - 2, y + h - 1, g.rbr)
    for i in range(x + 2, x + w - 2):
        _put(grid, i, y + h - 1, g.h)

    _write_label(grid, x, y, w, h, label_lines)


def _draw_trapezoid(grid: list[list[str]], p: _PlacedNode,
                    label_lines: list[str], g: Glyphs,
                    *, inverted: bool) -> None:
    """Render a trapezoid with the narrow horizontal on its own row.

    Putting the slope (╱╲) and the horizontal (─) on the *same* row creates
    visible gaps where they meet — diagonal glyphs and box-drawing glyphs
    don't connect cleanly inside a single cell.  Separating them onto
    adjacent rows hides the discontinuity: each row uses only one glyph
    family, and the shape reads as a coherent trapezoid.

    `inverted=False` (mermaid `[/text\\]`): bottom-wider.

           ──────       row 0: narrow horizontal cap
          ╱      ╲      row 1: slopes opening outward
          │ text │      row 2..h-2: vertical body
          │      │
          └──────┘      row h-1: flat wide bottom

    `inverted=True` (mermaid `[\\text/]`): top-wider — flat wide top,
    narrow horizontal at bottom.

          ┌──────┐
          │ text │
          │      │
          ╲      ╱      slopes converging
           ──────       narrow horizontal cap
    """
    x, y, w, h = p.x, p.y, p.w, p.h
    nw = g.diamond_top    # ╱
    ne = g.diamond_left   # ╲
    if h < 5 or w < 7:
        # Not enough rows for the dedicated cap; fall back to a plain box.
        _draw_plain_box(grid, x, y, w, h, g)
        _write_label(grid, x, y, w, h, label_lines)
        return

    if not inverted:
        # Row 0: narrow horizontal cap with rounded corners — closes the
        # narrow top into a clean polygon instead of a floating bar.
        _put(grid, x + 2, y, g.rtl)
        _put(grid, x + w - 3, y, g.rtr)
        for i in range(x + 3, x + w - 3):
            _put(grid, i, y, g.h)
        # Row 1: slopes — ╱ at col 1, ╲ at col w-2 (one inset from edges).
        _put(grid, x + 1, y + 1, nw)
        _put(grid, x + w - 2, y + 1, ne)
        # Body rows: vertical sides at the full width.
        for k in range(2, h - 1):
            _put(grid, x, y + k, g.v)
            _put(grid, x + w - 1, y + k, g.v)
            for i in range(x + 1, x + w - 1):
                _put(grid, i, y + k, " ")
        # Last row: flat wide bottom with corners.
        _put(grid, x, y + h - 1, g.bl)
        _put(grid, x + w - 1, y + h - 1, g.br)
        for i in range(x + 1, x + w - 1):
            _put(grid, i, y + h - 1, g.h)
    else:
        # Row 0: flat wide top with corners.
        _put(grid, x, y, g.tl)
        _put(grid, x + w - 1, y, g.tr)
        for i in range(x + 1, x + w - 1):
            _put(grid, i, y, g.h)
        # Body rows.
        for k in range(1, h - 2):
            _put(grid, x, y + k, g.v)
            _put(grid, x + w - 1, y + k, g.v)
            for i in range(x + 1, x + w - 1):
                _put(grid, i, y + k, " ")
        # Slope row: ╲ at col 1, ╱ at col w-2.
        _put(grid, x + 1, y + h - 2, ne)
        _put(grid, x + w - 2, y + h - 2, nw)
        # Bottom narrow horizontal cap with rounded corners.
        _put(grid, x + 2, y + h - 1, g.rbl)
        _put(grid, x + w - 3, y + h - 1, g.rbr)
        for i in range(x + 3, x + w - 3):
            _put(grid, i, y + h - 1, g.h)

    _write_label(grid, x, y, w, h, label_lines)


def _draw_parallelogram(grid: list[list[str]], p: _PlacedNode,
                        label_lines: list[str], g: Glyphs,
                        *, lean_left: bool) -> None:
    """Render a true leaning parallelogram by offsetting each row.

    The bounding box is wider than the label area by `h-1` cells (allocated
    in `_node_dims`).  Each row of the box body shifts horizontally by one
    cell so the box visibly leans — without any diagonal glyphs that would
    fail to connect to the box-drawing border characters.

    `lean_left=False` (mermaid `[/text/]`): top is shifted RIGHT, bottom
    LEFT (right-leaning):

           ╭───────────╮
          │   text    │
         │           │
        ╰───────────╯

    `lean_left=True` (mermaid `[\\text\\]`): top LEFT, bottom RIGHT.

         ╭───────────╮
          │   text    │
           │           │
            ╰───────────╯
    """
    x, y, w, h = p.x, p.y, p.w, p.h
    slant = h - 1
    inner_w = w - slant
    if h < 4 or inner_w < 5:
        # Constrained — fall back to a clean rounded box.
        _draw_box_with_chars(grid, x, y, w, h,
                             g.rtl, g.rtr, g.rbl, g.rbr, g.h, g.v)
        _write_label(grid, x, y, w, h, label_lines)
        return

    # Body sides use the slope glyph rather than vertical bars: stacked at
    # offset columns, the ╱ (or ╲) chars form a continuous diagonal because
    # each row's slope endpoint lines up with the next row's start point.
    side = g.diamond_left if lean_left else g.diamond_top  # ╲ or ╱

    for k in range(h):
        # Right-lean: row 0 starts furthest right, row h-1 furthest left.
        # Left-lean: opposite.
        offset = (slant - k) if not lean_left else k
        left = x + offset
        right = left + inner_w - 1
        if k == 0:
            _put(grid, left, y, g.rtl)
            _put(grid, right, y, g.rtr)
            for i in range(left + 1, right):
                _put(grid, i, y, g.h)
        elif k == h - 1:
            _put(grid, left, y + k, g.rbl)
            _put(grid, right, y + k, g.rbr)
            for i in range(left + 1, right):
                _put(grid, i, y + k, g.h)
        else:
            _put(grid, left, y + k, side)
            _put(grid, right, y + k, side)
            for i in range(left + 1, right):
                _put(grid, i, y + k, " ")

    # Place the label inside the body, shifted to track the lean.
    # Use the middle body row's offset as an anchor — labels at non-anchor
    # rows will be off by 1, which is fine for short labels and visually
    # reads as "label flowing along the slant".
    label_row_idx = max(1, h // 2)   # body row closest to the middle
    if not lean_left:
        label_offset = slant - label_row_idx
    else:
        label_offset = label_row_idx
    label_x = x + label_offset
    _write_label(grid, label_x, y, inner_w, h, label_lines)


def _wrap_label(label: str, max_w: int) -> list[str]:
    if max_w <= 0:
        return [label[: max(1, len(label))]]
    # Honour explicit \n in label first.
    raw_lines = label.splitlines() or [label]
    out: list[str] = []
    for raw in raw_lines:
        line = raw.strip()
        while len(line) > max_w:
            cut = line.rfind(" ", 0, max_w)
            if cut <= 0:
                cut = max_w
            out.append(line[:cut])
            line = line[cut:].lstrip()
        out.append(line)
    return out


def _write_label(grid: list[list[str]], x: int, y: int, w: int, h: int,
                 lines: list[str]) -> None:
    inner_h = h - 2
    if inner_h <= 0 or not lines:
        return
    start_row = y + 1 + max(0, (inner_h - len(lines)) // 2)
    for k, line in enumerate(lines[:inner_h]):
        col = x + 1 + max(0, (w - 2 - len(line)) // 2)
        for i, ch in enumerate(line):
            if 0 <= col + i < x + w - 1:
                _put(grid, col + i, start_row + k, ch)


def _draw_edge(grid: list[list[str]], pts: list[tuple[int, int]],
               style: EdgeStyle, arrow: ArrowStyle,
               label: str | None, g: Glyphs) -> None:
    if len(pts) < 2:
        return
    h_glyph = g.h if style == EdgeStyle.SOLID else (
        g.h_dashed if style == EdgeStyle.DASHED else g.h_thick
    )
    v_glyph = g.v if style == EdgeStyle.SOLID else (
        g.v_dashed if style == EdgeStyle.DASHED else g.v_thick
    )
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 == x1:
            lo, hi = sorted((y0, y1))
            for y in range(lo, hi + 1):
                _overlay(grid, x0, y, v_glyph, g)
        elif y0 == y1:
            lo, hi = sorted((x0, x1))
            for x in range(lo, hi + 1):
                _overlay(grid, x, y0, h_glyph, g)
        else:
            # Should not happen since we route orthogonally; fall back to
            # a step at the midpoint.
            mx = x0
            my = y1
            for y in range(min(y0, my), max(y0, my) + 1):
                _overlay(grid, mx, y, v_glyph, g)
            for x in range(min(mx, x1), max(mx, x1) + 1):
                _overlay(grid, x, my, h_glyph, g)
    # Place corner glyphs at polyline joints.
    for prev, here, nxt in zip(pts, pts[1:], pts[2:]):
        _put_corner(grid, prev, here, nxt, g)
    # Label placement: midpoint of the longest segment, biased to horizontal.
    if label:
        _place_edge_label(grid, pts, label)


def _overlay(grid: list[list[str]], x: int, y: int, ch: str, g: Glyphs) -> None:
    if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
        return
    cur = grid[y][x]
    if cur == " ":
        grid[y][x] = ch
    elif (cur in (g.h, g.h_dashed, g.h_thick) and ch in (g.v, g.v_dashed, g.v_thick)
          or cur in (g.v, g.v_dashed, g.v_thick) and ch in (g.h, g.h_dashed, g.h_thick)):
        grid[y][x] = g.cross


def _put_corner(grid: list[list[str]], prev: tuple[int, int],
                here: tuple[int, int], nxt: tuple[int, int], g: Glyphs) -> None:
    x, y = here
    if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
        return
    px, py = prev
    nx, ny = nxt
    came = "h" if py == y else "v"
    goes = "h" if ny == y else "v"
    if came == goes:
        return
    incoming_dir = (1 if px < x else -1) if came == "h" else (1 if py < y else -1)
    outgoing_dir = (1 if nx > x else -1) if goes == "h" else (1 if ny > y else -1)
    if came == "v" and goes == "h":
        # vertical → horizontal turn
        if incoming_dir == 1 and outgoing_dir == 1:    # came down, goes right
            grid[y][x] = g.rbl
        elif incoming_dir == 1 and outgoing_dir == -1:
            grid[y][x] = g.rbr
        elif incoming_dir == -1 and outgoing_dir == 1:
            grid[y][x] = g.rtl
        else:
            grid[y][x] = g.rtr
    else:
        # horizontal → vertical
        if incoming_dir == 1 and outgoing_dir == 1:    # came right, goes down
            grid[y][x] = g.rtr
        elif incoming_dir == 1 and outgoing_dir == -1:
            grid[y][x] = g.rbr
        elif incoming_dir == -1 and outgoing_dir == 1:
            grid[y][x] = g.rtl
        else:
            grid[y][x] = g.rbl


def _place_edge_label(grid: list[list[str]], pts: list[tuple[int, int]],
                      label: str) -> None:
    label = label.strip()
    if not label:
        return
    # Find longest horizontal segment for label placement.
    best = None
    best_len = -1
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if y0 != y1:
            continue
        seg_len = abs(x1 - x0)
        if seg_len > best_len:
            best_len = seg_len
            best = (x0, y0, x1, y1)
    if best is None:
        # Vertical only: place label to the right of the midpoint.
        x0, y0 = pts[0]
        x1, y1 = pts[-1]
        mx = x0 + 1
        my = (y0 + y1) // 2
        for i, ch in enumerate(label):
            _put(grid, mx + i, my, ch)
        return
    x0, y0, x1, _ = best
    cx = (x0 + x1) // 2
    start = cx - len(label) // 2
    # Place above the segment when there's room; else below.
    target_y = y0 - 1 if y0 - 1 >= 0 else y0 + 1
    for i, ch in enumerate(label):
        _put(grid, start + i, target_y, ch)


def _draw_arrow(grid: list[list[str]], pts: list[tuple[int, int]],
                arrow: ArrowStyle, g: Glyphs,
                placed: list[_PlacedNode]) -> None:
    if arrow == ArrowStyle.NONE or len(pts) < 2:
        return
    x1, y1 = pts[-1]
    # Walk back through the path until we find a point with different
    # coordinates from the endpoint. Path rounding can collapse adjacent
    # bend points onto the same cell, so the literal pts[-2] may equal
    # pts[-1] and yield no direction (would default to UP).
    idx = len(pts) - 2
    while idx >= 0 and pts[idx] == (x1, y1):
        idx -= 1
    if idx < 0:
        return
    x0, y0 = pts[idx]
    if x1 > x0:
        glyph = g.arrow_right
    elif x1 < x0:
        glyph = g.arrow_left
    elif y1 > y0:
        glyph = g.arrow_down
    else:
        glyph = g.arrow_up
    # The path now ends one cell outside the target box (see _route in
    # layout/grandalf.py), so the endpoint cell is exactly where the arrow
    # tip belongs. Stamp the glyph there, overwriting the path's last char.
    _put(grid, x1, y1, glyph)
