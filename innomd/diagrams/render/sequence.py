"""SequenceIR → list[str] (terminal lines).

Layout:
  - Each participant gets a column (lifeline).
  - Header row contains a labeled box per participant.
  - Below, a vertical lifeline (│) extends down through all messages.
  - Each message takes one or more rows: a horizontal arrow between
    source and destination lifelines, with the label centered above it.

Self-messages get a small loop drawn on the lifeline.
"""
from __future__ import annotations

from ..errors import RenderError
from ..ir_sequence import (
    Activation, Block, Message, MessageStyle, Note, NoteSide,
    Participant, SequenceIR,
)
from .box import ASCII, UNICODE, Glyphs


_PADDING = 1                # blank cells around the bounding box
_HEADER_H = 4               # rows for participant header boxes
_MIN_LIFELINE_GAP = 18      # min cells between adjacent lifelines
_MSG_ROWS = 3               # rows per message (label, arrow, blank)
_SELF_MSG_ROWS = 4          # self-message takes one extra row for the loop
_BLOCK_LABEL_ROWS = 1       # rows added per block start (one for the label)
_BLOCK_END_ROWS = 1         # rows added per block end (one for the closer)
_NOTE_ROWS = 4              # rows per inline note (top border, body, bottom)


def render(ir: SequenceIR, *, width: int, ascii_only: bool = False) -> list[str]:
    glyphs = ASCII if ascii_only else UNICODE
    if not ir.participants:
        raise RenderError("no participants")

    # 1. Compute per-participant column widths so labels fit.
    label_w = [max(len(p.label) + 2, 8) for p in ir.participants]

    # 2. Compute lifeline gap. It must be wide enough for participant
    #    headers AND for any inter-participant message label that should
    #    fit on a single line.
    inter_msg_widths = [
        len(m.text) for m in ir.messages if m.src != m.dst and m.text
    ]
    gap = max(
        _MIN_LIFELINE_GAP,
        max(label_w) + 4,
        (max(inter_msg_widths) + 4) if inter_msg_widths else 0,
    )

    # 3. Compute participant column centers.
    centers: list[int] = []
    cur = _PADDING + label_w[0] // 2
    centers.append(cur)
    for i in range(1, len(ir.participants)):
        cur += gap
        centers.append(cur)

    centers_by_id = {p.id: cx for p, cx in zip(ir.participants, centers)}

    # 4. Natural canvas width: enough for headers, plus room to the right
    #    of the last lifeline for any self-message label originating there,
    #    plus enough room on either side for notes anchored to participants.
    natural_w = centers[-1] + label_w[-1] // 2 + _PADDING
    for m in ir.messages:
        if m.src == m.dst and m.text and m.src in centers_by_id:
            cx = centers_by_id[m.src]
            need = cx + 6 + len(m.text) + _PADDING
            if need > natural_w:
                natural_w = need
    for n in ir.notes:
        cols = [centers_by_id.get(p) for p in n.participants if p in centers_by_id]
        if not cols:
            continue
        text_lines = n.text.replace("<br/>", "\n").replace("\\n", "\n").splitlines() or [""]
        inner = max((len(ln) for ln in text_lines), default=0)
        box_w = inner + 4
        if n.side.value == "right":
            need = cols[0] + 2 + box_w + _PADDING
        elif n.side.value == "left":
            # Note expands leftward — affects PADDING area on the left;
            # we don't shift other content, so this only matters when the
            # note would extend below x=0 (we render anyway, possibly
            # truncated). Don't enlarge canvas for this case.
            need = natural_w
        else:  # OVER
            mid = (min(cols) + max(cols)) // 2
            need = max(mid + box_w // 2, max(cols)) + _PADDING
        if need > natural_w:
            natural_w = need

    canvas_w = natural_w
    if canvas_w > width:
        raise RenderError(
            f"sequence needs {canvas_w} cols, only {width} available"
        )

    # 5. Compute total height — messages + block markers + notes + a footer
    #    row of participant boxes (mirrors the header so long diagrams stay
    #    readable when the header scrolls off).
    total_msg_rows = sum(
        _SELF_MSG_ROWS if m.src == m.dst else _MSG_ROWS
        for m in ir.messages
    )
    total_block_rows = len(ir.blocks) * (_BLOCK_LABEL_ROWS + _BLOCK_END_ROWS)
    total_note_rows = len(ir.notes) * _NOTE_ROWS
    canvas_h = (_PADDING + _HEADER_H + total_msg_rows + total_block_rows
                + total_note_rows + _HEADER_H + _PADDING + 1)

    # 5. Allocate canvas.
    grid = [[" "] * canvas_w for _ in range(canvas_h)]

    # 6. Draw participant header boxes.
    header_y = _PADDING
    for cx, p, lw in zip(centers, ir.participants, label_w):
        _draw_header_box(grid, cx, header_y, lw, p.label, glyphs)

    # 7. Draw lifelines (vertical) — between header and footer.
    lifeline_top = header_y + _HEADER_H
    lifeline_bot = canvas_h - _PADDING - _HEADER_H - 1
    for cx in centers:
        for y in range(lifeline_top, lifeline_bot + 1):
            _put(grid, cx, y, glyphs.v)

    # 8. Draw each message in turn, advancing y. Block start/end markers
    #    insert one row each before/after their message range. Notes are
    #    placed AFTER the message they're attached to.
    leftmost = centers[0]
    rightmost = centers[-1]
    blocks_start = {b.msg_start: b for b in ir.blocks}
    blocks_end_at: dict[int, list[Block]] = {}
    for b in ir.blocks:
        blocks_end_at.setdefault(b.msg_end, []).append(b)
    notes_after_msg: dict[int, list[Note]] = {}
    for n in ir.notes:
        notes_after_msg.setdefault(n.after_msg, []).append(n)

    # Track y-range each message occupies so activations can be drawn
    # later on top of the lifelines.
    msg_y_range: dict[int, tuple[int, int]] = {}

    # Notes that come BEFORE the first message (after_msg = -1).
    y = lifeline_top + 1   # leave one blank row below header
    for note in notes_after_msg.get(-1, []):
        _draw_note(grid, y, note, centers_by_id, glyphs)
        y += _NOTE_ROWS

    for i, m in enumerate(ir.messages):
        if i in blocks_start:
            b = blocks_start[i]
            _draw_block_open(grid, y, leftmost, rightmost, b, glyphs)
            y += _BLOCK_LABEL_ROWS

        msg_start_y = y
        if m.src not in centers_by_id or m.dst not in centers_by_id:
            y += _MSG_ROWS
        else:
            src_x = centers_by_id[m.src]
            dst_x = centers_by_id[m.dst]
            if src_x == dst_x:
                _draw_self_message(grid, src_x, y, m, glyphs)
                y += _SELF_MSG_ROWS
            else:
                _draw_message(grid, src_x, dst_x, y, m, glyphs)
                y += _MSG_ROWS
        msg_y_range[i] = (msg_start_y, y - 1)

        if (i + 1) in blocks_end_at:
            for b in blocks_end_at[i + 1]:
                _draw_block_close(grid, y, leftmost, rightmost, b, glyphs)
                y += _BLOCK_END_ROWS

        # Notes attached after this message.
        for note in notes_after_msg.get(i, []):
            _draw_note(grid, y, note, centers_by_id, glyphs)
            y += _NOTE_ROWS

    # 8b. Activations — overlay a thin vertical bar on the active
    # participant's lifeline column for the y-range of its activation.
    for act in ir.activations:
        if act.participant not in centers_by_id:
            continue
        cx = centers_by_id[act.participant]
        if act.msg_start not in msg_y_range or act.msg_end not in msg_y_range:
            continue
        y0 = msg_y_range[act.msg_start][0]
        y1 = msg_y_range[act.msg_end][1]
        for ay in range(y0, y1 + 1):
            cur = grid[ay][cx] if 0 <= ay < len(grid) else " "
            # Don't overwrite arrow tips or other meaningful glyphs;
            # only replace the lifeline glyph itself.
            if cur in (glyphs.v, " "):
                grid[ay][cx] = "▐" if glyphs is UNICODE else "#"

    # 9. Footer: repeat the participant boxes at the bottom so participant
    #    identity stays visible on long diagrams.
    footer_y = canvas_h - _PADDING - _HEADER_H
    for cx, p, lw in zip(centers, ir.participants, label_w):
        _draw_header_box(grid, cx, footer_y, lw, p.label, glyphs)

    return ["".join(row).rstrip() for row in grid]


def _draw_note(grid, y: int, note: Note,
               centers_by_id: dict[str, int], g: Glyphs) -> None:
    """Render a sequence diagram note as a small box.

    Layout:
       row y:    blank (separator from preceding message)
       row y+1:  ╭─────────╮  top of the note box
       row y+2:  │ text    │  body
       row y+3:  ╰─────────╯  bottom

    Position depends on side: LEFT places the box just to the left of
    the participant's lifeline; RIGHT just to the right; OVER spans
    horizontally between two lifelines (or sits on top of one).
    """
    # Resolve participant column(s).
    cols = [centers_by_id.get(p) for p in note.participants]
    cols = [c for c in cols if c is not None]
    if not cols:
        return
    # Compose label lines.
    text_lines = note.text.replace("<br/>", "\n").replace("\\n", "\n").splitlines() or [""]
    inner_w = max((len(ln) for ln in text_lines), default=0)
    box_w = inner_w + 4
    if note.side == NoteSide.LEFT:
        right = cols[0] - 2
        left = max(0, right - box_w + 1)
    elif note.side == NoteSide.RIGHT:
        left = cols[0] + 2
        right = left + box_w - 1
    else:  # OVER
        if len(cols) >= 2:
            mid = (min(cols) + max(cols)) // 2
        else:
            mid = cols[0]
        left = max(0, mid - box_w // 2)
        right = left + box_w - 1
    # Box body — note row 0 stays blank as a separator. Box draws on
    # rows y+1 .. y+3.
    box_top = y + 1
    box_bot = y + 3
    _put(grid, left, box_top, g.rtl)
    _put(grid, right, box_top, g.rtr)
    _put(grid, left, box_bot, g.rbl)
    _put(grid, right, box_bot, g.rbr)
    for x in range(left + 1, right):
        _put(grid, x, box_top, g.h)
        _put(grid, x, box_bot, g.h)
    _put(grid, left, y + 2, g.v)
    _put(grid, right, y + 2, g.v)
    for x in range(left + 1, right):
        _put(grid, x, y + 2, " ")
    # Place the first line of text centered.
    text = text_lines[0] if text_lines else ""
    text_x = left + 2 + max(0, (inner_w - len(text)) // 2)
    for i, ch in enumerate(text):
        _put(grid, text_x + i, y + 2, ch)


def _draw_block_open(grid, y, leftmost, rightmost, block: Block, g: Glyphs) -> None:
    """Draw a block-start marker: a horizontal rule with `[kind label]`."""
    label = block.label.strip()
    text = f"[{block.kind}{(' ' + label) if label else ''}]"
    # Line glyph spanning lifelines.
    for x in range(leftmost, rightmost + 1):
        _put(grid, x, y, g.h_dashed)
    # Place label slightly inset from leftmost lifeline.
    label_x = leftmost + 2
    # Surrounding spaces so the label reads as separate from the rule.
    if label_x - 1 >= 0:
        _put(grid, label_x - 1, y, " ")
    for i, ch in enumerate(text):
        _put(grid, label_x + i, y, ch)
    end = label_x + len(text)
    if end < rightmost:
        _put(grid, end, y, " ")


def _draw_block_close(grid, y, leftmost, rightmost, block: Block, g: Glyphs) -> None:
    """Draw a block-end marker: a horizontal rule with `[end <kind>]`."""
    text = f"[end {block.kind}]"
    for x in range(leftmost, rightmost + 1):
        _put(grid, x, y, g.h_dashed)
    label_x = leftmost + 2
    if label_x - 1 >= 0:
        _put(grid, label_x - 1, y, " ")
    for i, ch in enumerate(text):
        _put(grid, label_x + i, y, ch)
    end = label_x + len(text)
    if end < rightmost:
        _put(grid, end, y, " ")


def _put(grid: list[list[str]], x: int, y: int, ch: str) -> None:
    if 0 <= y < len(grid) and 0 <= x < len(grid[0]):
        grid[y][x] = ch


def _draw_header_box(grid: list[list[str]], cx: int, y: int,
                     w: int, label: str, g: Glyphs) -> None:
    """Draw a labeled box centered horizontally on `cx` at row `y`.

    Box is `w` wide × _HEADER_H rows. Label goes in row y+1 (or center).
    """
    left = cx - w // 2
    right = left + w - 1
    h = _HEADER_H
    _put(grid, left, y, g.tl)
    _put(grid, right, y, g.tr)
    _put(grid, left, y + h - 1, g.bl)
    _put(grid, right, y + h - 1, g.br)
    for i in range(left + 1, right):
        _put(grid, i, y, g.h)
        _put(grid, i, y + h - 1, g.h)
    for j in range(1, h - 1):
        _put(grid, left, y + j, g.v)
        _put(grid, right, y + j, g.v)
        for i in range(left + 1, right):
            _put(grid, i, y + j, " ")
    # Label centered.
    label_y = y + h // 2
    label_x = cx - len(label) // 2
    for i, ch in enumerate(label):
        _put(grid, label_x + i, label_y, ch)


def _draw_message(grid: list[list[str]], src_x: int, dst_x: int, y: int,
                  m: Message, g: Glyphs) -> None:
    """Draw a 3-row message between lifelines.

    Row y:   label (centered between lifelines)
    Row y+1: horizontal arrow
    Row y+2: blank (spacer before next message)
    """
    going_right = dst_x > src_x
    lo, hi = (src_x, dst_x) if going_right else (dst_x, src_x)

    # Label centered between lifelines, slightly trimmed if needed.
    if m.text:
        avail = hi - lo - 1
        text = m.text if len(m.text) <= avail else m.text[:max(0, avail - 1)] + "…"
        text_start = (lo + hi) // 2 - len(text) // 2
        for i, ch in enumerate(text):
            _put(grid, text_start + i, y, ch)

    # Arrow row.
    arrow_y = y + 1
    is_dashed = m.style in (MessageStyle.ASYNC, MessageStyle.DASHED)
    line_glyph = g.h_dashed if is_dashed else g.h
    has_arrow = m.style in (MessageStyle.SYNC, MessageStyle.ASYNC)
    # Draw the line; at intermediate lifeline crossings, use the cross
    # glyph (┼) so the lifeline stays visible through the message line.
    for x in range(lo, hi + 1):
        if grid[arrow_y][x] == g.v:           # crossing an intermediate lifeline
            _put(grid, x, arrow_y, g.cross)
        else:
            _put(grid, x, arrow_y, line_glyph)
    # Arrow tip overrides the cross at the destination.
    if has_arrow:
        if going_right:
            _put(grid, dst_x, arrow_y, g.arrow_right)
        else:
            _put(grid, dst_x, arrow_y, g.arrow_left)


def _draw_self_message(grid: list[list[str]], x: int, y: int,
                       m: Message, g: Glyphs) -> None:
    """Draw a self-loop on a single lifeline.

    Layout (4 rows, _SELF_MSG_ROWS):

       │   label                row y:   label, sits to the right of loop
       ├──╮                     row y+1: ├ on lifeline + horizontal + corner
       │  │                     row y+2: lifeline + right side of loop
       ◀──╯                     row y+3: arrow back to lifeline

    The arrow tip ◀ replaces the lifeline glyph at (x, y+3) so the
    direction is clear.
    """
    is_dashed = m.style in (MessageStyle.ASYNC, MessageStyle.DASHED)
    has_arrow = m.style in (MessageStyle.SYNC, MessageStyle.ASYNC)
    h_glyph = g.h_dashed if is_dashed else g.h

    # Row y: label to the right of the lifeline.
    if m.text:
        for i, ch in enumerate(m.text):
            _put(grid, x + 7 + i, y, ch)
    # Row y+1: top of loop. Junction at lifeline, horizontals, then corner.
    _put(grid, x, y + 1, g.t_right)        # ├
    for i in range(1, 5):
        _put(grid, x + i, y + 1, h_glyph)
    _put(grid, x + 5, y + 1, g.rtr)        # ╮
    # Row y+2: lifeline | already there at col x; right side of loop.
    _put(grid, x + 5, y + 2, g.v)
    # Row y+3: arrow back to lifeline. Arrow at (x+1) so it doesn't
    # obliterate the ├ junction.
    if has_arrow:
        _put(grid, x, y + 3, g.t_right)    # ├
        _put(grid, x + 1, y + 3, g.arrow_left)
        for i in range(2, 5):
            _put(grid, x + i, y + 3, h_glyph)
    else:
        _put(grid, x, y + 3, g.t_right)
        for i in range(1, 5):
            _put(grid, x + i, y + 3, h_glyph)
    _put(grid, x + 5, y + 3, g.rbr)        # ╯
