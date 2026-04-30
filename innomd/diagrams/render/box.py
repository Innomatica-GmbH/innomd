"""Glyph sets for ASCII and Unicode box drawing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Glyphs:
    # Box corners (rect)
    tl: str; tr: str; bl: str; br: str
    # Box edges
    h: str; v: str
    # Round corners
    rtl: str; rtr: str; rbl: str; rbr: str
    # Line crossings / branches
    cross: str
    t_down: str; t_up: str; t_left: str; t_right: str
    # Arrow tips
    arrow_up: str; arrow_down: str; arrow_left: str; arrow_right: str
    # Diagonal slopes (used in trapezoid + parallelogram corners)
    diamond_top: str; diamond_bot: str
    diamond_left: str; diamond_right: str
    # Heavy single-line box (DIAMOND): connects cleanly, visually thicker.
    h_heavy: str; v_heavy: str
    tl_heavy: str; tr_heavy: str; bl_heavy: str; br_heavy: str
    # Double-line box (HEXAGON): connects cleanly, two parallel strokes.
    h_double: str; v_double: str
    tl_double: str; tr_double: str; bl_double: str; br_double: str
    # Circle outline (single glyph used in corners + edges)
    circle_top: str; circle_bot: str
    circle_left: str; circle_right: str
    circle_tl: str; circle_tr: str; circle_bl: str; circle_br: str
    # Dashed line variants
    h_dashed: str; v_dashed: str
    # Thick line variants (legacy alias for heavy — keep for edge styles).
    h_thick: str; v_thick: str


UNICODE = Glyphs(
    tl="┌", tr="┐", bl="└", br="┘",
    h="─", v="│",
    rtl="╭", rtr="╮", rbl="╰", rbr="╯",
    cross="┼",
    t_down="┬", t_up="┴", t_left="┤", t_right="├",
    arrow_up="▲", arrow_down="▼", arrow_left="◀", arrow_right="▶",
    diamond_top="╱", diamond_bot="╱", diamond_left="╲", diamond_right="╲",
    h_heavy="━", v_heavy="┃",
    tl_heavy="┏", tr_heavy="┓", bl_heavy="┗", br_heavy="┛",
    h_double="═", v_double="║",
    tl_double="╔", tr_double="╗", bl_double="╚", br_double="╝",
    circle_top="─", circle_bot="─", circle_left="│", circle_right="│",
    circle_tl="╭", circle_tr="╮", circle_bl="╰", circle_br="╯",
    h_dashed="╌", v_dashed="╎",
    h_thick="━", v_thick="┃",
)


ASCII = Glyphs(
    tl="+", tr="+", bl="+", br="+",
    h="-", v="|",
    rtl="+", rtr="+", rbl="+", rbr="+",
    cross="+",
    t_down="+", t_up="+", t_left="+", t_right="+",
    arrow_up="^", arrow_down="v", arrow_left="<", arrow_right=">",
    diamond_top="/", diamond_bot="/", diamond_left="\\", diamond_right="\\",
    # ASCII has no real heavy/double weights; we approximate with #/= and
    # plain corners so the shapes still draw cleanly.
    h_heavy="#", v_heavy="#",
    tl_heavy="#", tr_heavy="#", bl_heavy="#", br_heavy="#",
    h_double="=", v_double="|",
    tl_double="+", tr_double="+", bl_double="+", br_double="+",
    circle_top="-", circle_bot="-", circle_left="|", circle_right="|",
    circle_tl="+", circle_tr="+", circle_bl="+", circle_br="+",
    h_dashed="-", v_dashed="|",
    h_thick="=", v_thick="|",
)
