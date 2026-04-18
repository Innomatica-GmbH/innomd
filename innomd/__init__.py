"""innomd — terminal Markdown viewer with LaTeX math support."""
from __future__ import annotations

__version__ = "0.2.0"
__all__ = ["main", "__version__"]

import argparse
import io
import json
import os
import re
import select
import signal
import sys
import termios
import threading
import time
import tty
from pathlib import Path

GREEK = {
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ϵ", r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η",
    r"\theta": "θ", r"\vartheta": "ϑ", r"\iota": "ι", r"\kappa": "κ",
    r"\lambda": "λ", r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ",
    r"\pi": "π", r"\varpi": "ϖ", r"\rho": "ρ", r"\varrho": "ϱ",
    r"\sigma": "σ", r"\varsigma": "ς", r"\tau": "τ", r"\upsilon": "υ",
    r"\phi": "φ", r"\varphi": "ϕ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Upsilon": "Υ",
    r"\Phi": "Φ", r"\Psi": "Ψ", r"\Omega": "Ω",
    r"\hbar": "ℏ", r"\ell": "ℓ", r"\Re": "ℜ", r"\Im": "ℑ",
}

OPERATORS = {
    r"\cdot": "·", r"\times": "×", r"\div": "÷", r"\pm": "±", r"\mp": "∓",
    r"\ast": "∗", r"\star": "⋆", r"\circ": "∘", r"\bullet": "•",
    r"\leq": "≤", r"\le": "≤", r"\geq": "≥", r"\ge": "≥",
    r"\neq": "≠", r"\ne": "≠", r"\approx": "≈", r"\equiv": "≡",
    r"\sim": "∼", r"\simeq": "≃", r"\cong": "≅", r"\propto": "∝",
    r"\ll": "≪", r"\gg": "≫",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇", r"\prime": "′",
    r"\sum": "∑", r"\prod": "∏", r"\coprod": "∐",
    r"\int": "∫", r"\iint": "∬", r"\iiint": "∭", r"\oint": "∮",
    r"\sqrt": "√",
    r"\rightarrow": "→", r"\to": "→", r"\leftarrow": "←", r"\gets": "←",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⇔",
    r"\leftrightarrow": "↔", r"\uparrow": "↑", r"\downarrow": "↓",
    r"\mapsto": "↦", r"\longrightarrow": "⟶", r"\longleftarrow": "⟵",
    r"\in": "∈", r"\notin": "∉", r"\ni": "∋",
    r"\subset": "⊂", r"\supset": "⊃", r"\subseteq": "⊆", r"\supseteq": "⊇",
    r"\cup": "∪", r"\cap": "∩", r"\setminus": "∖", r"\emptyset": "∅", r"\varnothing": "∅",
    r"\forall": "∀", r"\exists": "∃", r"\nexists": "∄", r"\neg": "¬",
    r"\land": "∧", r"\wedge": "∧", r"\lor": "∨", r"\vee": "∨",
    r"\therefore": "∴", r"\because": "∵",
    r"\ldots": "…", r"\cdots": "⋯", r"\vdots": "⋮", r"\ddots": "⋱",
    r"\dots": "…",
    r"\quad": "   ", r"\qquad": "      ",
    r"\,": " ", r"\;": " ", r"\:": " ", r"\!": "", r"\ ": " ",
    r"\%": "%", r"\$": "$", r"\&": "&", r"\#": "#", r"\_": "_",
    r"\{": "{", r"\}": "}",
    r"\deg": "°", r"\degree": "°",
    r"\langle": "⟨", r"\rangle": "⟩",
    r"\lfloor": "⌊", r"\rfloor": "⌋", r"\lceil": "⌈", r"\rceil": "⌉",
    r"\aleph": "ℵ", r"\Box": "□", r"\Diamond": "◇", r"\triangle": "△",
    r"\mathbb{R}": "ℝ", r"\mathbb{N}": "ℕ", r"\mathbb{Z}": "ℤ",
    r"\mathbb{Q}": "ℚ", r"\mathbb{C}": "ℂ", r"\mathbb{P}": "ℙ",
    r"\mathcal{L}": "ℒ", r"\mathcal{H}": "ℋ",
    r"\left": "", r"\right": "", r"\bigl": "", r"\bigr": "",
    r"\big": "", r"\Big": "", r"\Bigg": "",
    r"\displaystyle": "", r"\textstyle": "", r"\scriptstyle": "",
}

SUPERSCRIPT = str.maketrans(
    "0123456789+-=()nabcdefghijklmoprstuvwxyzABDEGHIJKLMNOPRTUVW",
    "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿᵃᵇᶜᵈᵉᶠᵍʰⁱʲᵏˡᵐᵒᵖʳˢᵗᵘᵛʷˣʸᶻᴬᴮᴰᴱᴳᴴᴵᴶᴷᴸᴹᴺᴼᴾᴿᵀᵁⱽᵂ",
)
SUBSCRIPT = str.maketrans(
    "0123456789+-=()aehijklmnoprstuvx",
    "₀₁₂₃₄₅₆₇₈₉₊₋₌₍₎ₐₑₕᵢⱼₖₗₘₙₒₚᵣₛₜᵤᵥₓ",
)

THEMES: dict[str, dict[str, str]] = {
    "default": {
        "code": "monokai",
        "header": "bold cyan",
        "border": "dim",
        "hr": "dim",
        "h1": "bold magenta",
        "h2": "bold cyan",
        "h3": "bold green",
        "link": "underline blue",
        "code_inline": "bold yellow",
        "blockquote": "italic grey70",
    },
    "nord": {
        "code": "nord-darker",
        "header": "bold #88C0D0",
        "border": "#4C566A",
        "hr": "#5E81AC",
        "h1": "bold #88C0D0",
        "h2": "bold #8FBCBB",
        "h3": "bold #A3BE8C",
        "link": "underline #81A1C1",
        "code_inline": "bold #EBCB8B",
        "blockquote": "italic #D8DEE9",
    },
    "dracula": {
        "code": "dracula",
        "header": "bold #BD93F9",
        "border": "#6272A4",
        "hr": "#FF79C6",
        "h1": "bold #FF79C6",
        "h2": "bold #BD93F9",
        "h3": "bold #50FA7B",
        "link": "underline #8BE9FD",
        "code_inline": "bold #F1FA8C",
        "blockquote": "italic #6272A4",
    },
    "gruvbox": {
        "code": "gruvbox-dark",
        "header": "bold #FABD2F",
        "border": "#665C54",
        "hr": "#928374",
        "h1": "bold #FB4934",
        "h2": "bold #FABD2F",
        "h3": "bold #B8BB26",
        "link": "underline #83A598",
        "code_inline": "bold #D3869B",
        "blockquote": "italic #A89984",
    },
    "solarized-dark": {
        "code": "solarized-dark",
        "header": "bold #2AA198",
        "border": "#586E75",
        "hr": "#657B83",
        "h1": "bold #268BD2",
        "h2": "bold #2AA198",
        "h3": "bold #859900",
        "link": "underline #6C71C4",
        "code_inline": "bold #B58900",
        "blockquote": "italic #93A1A1",
    },
    "solarized-light": {
        "code": "solarized-light",
        "header": "bold #268BD2",
        "border": "#93A1A1",
        "hr": "#93A1A1",
        "h1": "bold #D33682",
        "h2": "bold #268BD2",
        "h3": "bold #859900",
        "link": "underline #6C71C4",
        "code_inline": "bold #B58900",
        "blockquote": "italic #586E75",
    },
    "tokyonight": {
        "code": "one-dark",
        "header": "bold #7AA2F7",
        "border": "#3B4261",
        "hr": "#565F89",
        "h1": "bold #BB9AF7",
        "h2": "bold #7AA2F7",
        "h3": "bold #9ECE6A",
        "link": "underline #2AC3DE",
        "code_inline": "bold #E0AF68",
        "blockquote": "italic #9AA5CE",
    },
    "github": {
        "code": "github-dark",
        "header": "bold #58A6FF",
        "border": "#30363D",
        "hr": "#484F58",
        "h1": "bold #F78166",
        "h2": "bold #58A6FF",
        "h3": "bold #3FB950",
        "link": "underline #58A6FF",
        "code_inline": "bold #F8E3A1",
        "blockquote": "italic #8B949E",
    },
    "mono": {
        "code": "bw",
        "header": "bold",
        "border": "dim",
        "hr": "dim",
        "h1": "bold",
        "h2": "bold",
        "h3": "bold",
        "link": "underline",
        "code_inline": "reverse",
        "blockquote": "italic",
    },
}


def to_super(s: str) -> str:
    if s and all(c in "0123456789+-=()nabcdefghijklmoprstuvwxyzABDEGHIJKLMNOPRTUVW" for c in s):
        return s.translate(SUPERSCRIPT)
    if len(s) == 1:
        return "^" + s
    return "^(" + s + ")"


def to_sub(s: str) -> str:
    if s and all(c in "0123456789+-=()aehijklmnoprstuvx" for c in s):
        return s.translate(SUBSCRIPT)
    if len(s) == 1:
        return "_" + s
    return "_(" + s + ")"


def balanced_groups(s: str, start: int) -> tuple[str, int] | None:
    if start >= len(s) or s[start] != "{":
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                return s[start + 1 : i], i + 1
    return None


def replace_command_with_groups(text: str, name: str, n_args: int, fn) -> str:
    out = []
    i = 0
    pattern = "\\" + name
    while i < len(text):
        if text.startswith(pattern, i):
            after = i + len(pattern)
            if after < len(text) and text[after].isalpha():
                out.append(text[i])
                i += 1
                continue
            args = []
            j = after
            while j < len(text) and text[j] == " ":
                j += 1
            ok = True
            for _ in range(n_args):
                grp = balanced_groups(text, j)
                if grp is None:
                    ok = False
                    break
                args.append(grp[0])
                j = grp[1]
            if ok:
                out.append(fn(args))
                i = j
                continue
        out.append(text[i])
        i += 1
    return "".join(out)


def convert_math(tex: str) -> str:
    s = tex
    for _ in range(3):
        for cmd in ("text", "mathrm", "mathbf", "mathit", "mathsf", "mathtt",
                    "operatorname", "textbf", "textit"):
            s = replace_command_with_groups(s, cmd, 1, lambda a: a[0])
    for _ in range(4):
        s = replace_command_with_groups(
            s, "frac", 2,
            lambda a: (f"({a[0]})/({a[1]})" if any(c in a[0] + a[1] for c in "+-·× ") else f"{a[0]}/{a[1]}"),
        )
        s = replace_command_with_groups(
            s, "dfrac", 2,
            lambda a: (f"({a[0]})/({a[1]})" if any(c in a[0] + a[1] for c in "+-·× ") else f"{a[0]}/{a[1]}"),
        )
        s = replace_command_with_groups(
            s, "tfrac", 2,
            lambda a: (f"({a[0]})/({a[1]})" if any(c in a[0] + a[1] for c in "+-·× ") else f"{a[0]}/{a[1]}"),
        )
    s = re.sub(r"\\sqrt\[([^\]]+)\]\{([^{}]+)\}",
               lambda m: to_super(m.group(1)) + "√(" + m.group(2) + ")", s)
    s = replace_command_with_groups(s, "sqrt", 1, lambda a: "√(" + a[0] + ")")
    s = replace_command_with_groups(s, "vec", 1, lambda a: a[0] + "⃗")
    s = replace_command_with_groups(s, "hat", 1, lambda a: a[0] + "̂")
    s = replace_command_with_groups(s, "bar", 1, lambda a: a[0] + "̄")
    s = replace_command_with_groups(s, "dot", 1, lambda a: a[0] + "̇")
    items = sorted(list(GREEK.items()) + list(OPERATORS.items()), key=lambda x: -len(x[0]))
    for k, v in items:
        if k and k[-1].isalpha():
            s = re.sub(re.escape(k) + r"(?![A-Za-z])", v, s)
        else:
            s = s.replace(k, v)
    s = re.sub(r"\^\{([^{}]+)\}", lambda m: to_super(m.group(1)), s)
    s = re.sub(r"_\{([^{}]+)\}", lambda m: to_sub(m.group(1)), s)
    s = re.sub(r"\^(\\?[A-Za-z0-9+\-])", lambda m: to_super(m.group(1).lstrip("\\")), s)
    s = re.sub(r"_(\\?[A-Za-z0-9+\-])", lambda m: to_sub(m.group(1).lstrip("\\")), s)
    prev = None
    while prev != s:
        prev = s
        s = re.sub(r"\{([^{}]*)\}", r"\1", s)
    s = re.sub(r"[ \t]+", " ", s).strip()
    return s


def preprocess(text: str) -> str:
    fence_re = re.compile(r"(^```.*?^```)", re.DOTALL | re.MULTILINE)
    parts = fence_re.split(text)
    out = []
    for part in parts:
        if part.startswith("```"):
            out.append(part)
            continue
        part = re.sub(r"\$\$(.+?)\$\$",
                      lambda m: "\n\n> **" + convert_math(m.group(1)) + "**\n\n",
                      part, flags=re.DOTALL)
        part = re.sub(r"\\\[(.+?)\\\]",
                      lambda m: "\n\n> **" + convert_math(m.group(1)) + "**\n\n",
                      part, flags=re.DOTALL)
        part = re.sub(r"(?<!\\)\$([^\$\n]+?)(?<!\\)\$",
                      lambda m: "`" + convert_math(m.group(1)) + "`", part)
        part = re.sub(r"\\\((.+?)\\\)",
                      lambda m: "`" + convert_math(m.group(1)) + "`",
                      part, flags=re.DOTALL)
        out.append(part)
    return "".join(out)


def ipynb_to_markdown(raw: str) -> str:
    nb = json.loads(raw)
    lang = (nb.get("metadata", {}).get("kernelspec", {}).get("language")
            or nb.get("metadata", {}).get("language_info", {}).get("name")
            or "python")
    parts: list[str] = []
    for cell in nb.get("cells", []):
        ctype = cell.get("cell_type")
        src = "".join(cell.get("source", []))
        if ctype == "markdown":
            parts.append(src)
        elif ctype == "code":
            parts.append(f"```{lang}\n{src}\n```")
            for out in cell.get("outputs", []):
                otype = out.get("output_type")
                if otype == "stream":
                    text = "".join(out.get("text", []))
                    if text.strip():
                        parts.append("```\n" + text.rstrip() + "\n```")
                elif otype in ("execute_result", "display_data"):
                    data = out.get("data", {})
                    if "text/markdown" in data:
                        parts.append("".join(data["text/markdown"]))
                    elif "text/plain" in data:
                        text = "".join(data["text/plain"])
                        if text.strip():
                            parts.append("```\n" + text.rstrip() + "\n```")
                elif otype == "error":
                    tb = "\n".join(out.get("traceback", []))
                    tb = re.sub(r"\x1b\[[0-9;]*m", "", tb)
                    parts.append("```\n" + tb + "\n```")
        elif ctype == "raw":
            parts.append(src)
    return "\n\n".join(parts)


def load_source(file: str | None) -> str:
    if not file:
        return sys.stdin.read()
    path = Path(file)
    raw = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".ipynb":
        return ipynb_to_markdown(raw)
    return raw


def build_renderer(theme_name: str, code_override: str | None):
    from rich import box
    from rich.align import Align
    from rich.console import Console
    from rich.markdown import Markdown, TableElement, HorizontalRule
    from rich.table import Table
    from rich.text import Text
    from rich.theme import Theme

    t = THEMES.get(theme_name, THEMES["default"])
    code_theme = code_override or t["code"]

    class InnoTable(TableElement):
        def __rich_console__(self, console, options):
            table = Table(box=box.ROUNDED, show_header=True,
                          header_style=t["header"], border_style=t["border"],
                          pad_edge=True, expand=False)
            if self.header is not None and self.header.row is not None:
                for column in self.header.row.cells:
                    table.add_column(column.content)
            if self.body is not None:
                for row in self.body.rows:
                    table.add_row(*[c.content for c in row.cells])
            yield table

    class InnoRule(HorizontalRule):
        def __rich_console__(self, console, options):
            yield Align.center(Text("· · ·", style=t["hr"]))

    class InnoMarkdown(Markdown):
        elements = {**Markdown.elements, "table_open": InnoTable, "hr": InnoRule}

    rich_theme = Theme({
        "markdown.h1": t["h1"],
        "markdown.h2": t["h2"],
        "markdown.h3": t["h3"],
        "markdown.h4": t["h3"],
        "markdown.link": t["link"],
        "markdown.link_url": t["link"],
        "markdown.code": t["code_inline"],
        "markdown.block_quote": t["blockquote"],
    }, inherit=True)

    return Console, InnoMarkdown, rich_theme, code_theme


def render_once(text: str, width: int | None, theme_name: str, code_override: str | None,
                use_pager: bool) -> None:
    Console, InnoMarkdown, rich_theme, code_theme = build_renderer(theme_name, code_override)
    console = Console(width=width, theme=rich_theme)
    md = InnoMarkdown(text, code_theme=code_theme, hyperlinks=True)
    if use_pager:
        os.environ.setdefault("LESS", "-R")
        with console.pager(styles=True):
            console.print(md)
    else:
        console.print(md)


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07")
MOUSE_RE = re.compile(r"\x1b\[<(\d+);(\d+);(\d+)([Mm])")
MOUSE_SCROLL_LINES = 3


def _term_size() -> tuple[int, int]:
    try:
        sz = os.get_terminal_size()
        return sz.columns, sz.lines
    except OSError:
        return 80, 24


def _ansi_strip(s: str) -> str:
    return ANSI_RE.sub("", s)


class _WatchState:
    def __init__(self, file: str, user_width: int | None,
                 theme_name: str, code_override: str | None) -> None:
        self.file = Path(file)
        self.user_width = user_width
        self.theme_name = theme_name
        self.code_override = code_override
        self.lines: list[str] = []
        self.offset = 0
        self.cols, self.rows = _term_size()
        self.last_reload = time.time()
        self.lock = threading.Lock()
        self.dirty = threading.Event()
        self.stop = threading.Event()
        self.resize_pending = False
        self.status_msg = ""
        self.mode = "normal"
        self.prompt_prefix = ""
        self.prompt_buffer = ""
        self.search_pattern: re.Pattern | None = None
        self.match_lines: list[int] = []


def _render_lines(state: _WatchState) -> list[str]:
    try:
        text = load_source(str(state.file))
    except FileNotFoundError:
        return [f"\x1b[31minnomd: waiting for {state.file}…\x1b[0m"]
    except Exception as e:
        return [f"\x1b[31minnomd: {e}\x1b[0m"]
    try:
        processed = preprocess(text)
        Console, InnoMarkdown, rich_theme, code_theme = build_renderer(
            state.theme_name, state.code_override)
    except Exception as e:
        return [f"\x1b[31minnomd: {e}\x1b[0m"]
    width = state.user_width or max(20, state.cols)
    buf = io.StringIO()
    console = Console(file=buf, width=width, theme=rich_theme,
                      force_terminal=True, color_system="truecolor",
                      legacy_windows=False)
    try:
        md = InnoMarkdown(processed, code_theme=code_theme, hyperlinks=True)
        console.print(md)
    except Exception as e:
        return [f"\x1b[31minnomd: render failed: {e}\x1b[0m"]
    return buf.getvalue().rstrip("\n").split("\n")


def _highlight_matches(line: str, pattern: re.Pattern) -> str:
    stripped = _ansi_strip(line)
    matches = list(pattern.finditer(stripped))
    if not matches:
        return line
    starts = {m.start() for m in matches}
    ends = {m.end() for m in matches}
    out: list[str] = []
    vis = 0
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "\x1b":
            m = ANSI_RE.match(line, i)
            if m:
                out.append(m.group(0))
                i = m.end()
                continue
        if vis in ends:
            out.append("\x1b[27m")
        if vis in starts:
            out.append("\x1b[7m")
        out.append(line[i])
        vis += 1
        i += 1
    if vis in ends:
        out.append("\x1b[27m")
    return "".join(out)


def _recompute_matches(state: _WatchState) -> None:
    """Caller must hold state.lock."""
    if state.search_pattern is None:
        state.match_lines = []
        return
    state.match_lines = [i for i, line in enumerate(state.lines)
                         if state.search_pattern.search(_ansi_strip(line))]


def _jump_to_match(state: _WatchState, forward: bool, include_current: bool = False) -> None:
    """Caller must hold state.lock."""
    if not state.match_lines:
        return
    if forward:
        start = state.offset if include_current else state.offset + 1
        nxt = next((i for i in state.match_lines if i >= start), state.match_lines[0])
    else:
        nxt = next((i for i in reversed(state.match_lines) if i < state.offset),
                   state.match_lines[-1])
    state.offset = nxt
    _clamp_offset(state)


def _do_search(state: _WatchState, pattern_text: str) -> None:
    if not pattern_text:
        with state.lock:
            state.search_pattern = None
            state.match_lines = []
        state.status_msg = ""
        return
    try:
        pat = re.compile(pattern_text, re.IGNORECASE)
    except re.error as e:
        with state.lock:
            state.search_pattern = None
            state.match_lines = []
        state.status_msg = f"bad regex: {e}"
        return
    with state.lock:
        state.search_pattern = pat
        _recompute_matches(state)
        matched = len(state.match_lines)
        if matched:
            _jump_to_match(state, forward=True, include_current=True)
    if matched:
        state.status_msg = f"{matched} match(es) · n/N"
    else:
        state.status_msg = f"no match for /{pattern_text}/"


def _clamp_offset(state: _WatchState) -> None:
    body_rows = max(1, state.rows - 1)
    max_offset = max(0, len(state.lines) - body_rows)
    state.offset = max(0, min(state.offset, max_offset))


def _status_line(state: _WatchState) -> str:
    total = max(1, len(state.lines))
    body_rows = max(1, state.rows - 1)
    bottom = min(state.offset + body_rows, total)
    pct = int(100 * bottom / total)
    ts = time.strftime("%H:%M:%S", time.localtime(state.last_reload))
    left = (f" {state.file.name} · {state.offset + 1}-{bottom}/{total} "
            f"({pct}%) · {state.theme_name} · {ts} ")
    hints = " j/k ↑↓ space/b g/G / :q "
    msg = state.status_msg
    middle = f"  {msg}  " if msg else ""
    pad = max(1, state.cols - len(left) - len(middle) - len(hints))
    return (left + middle + " " * pad + hints)[:state.cols]


def _draw(state: _WatchState) -> None:
    with state.lock:
        body_rows = max(1, state.rows - 1)
        visible = state.lines[state.offset:state.offset + body_rows]
        pattern = state.search_pattern
        status = _status_line(state)
        rows = state.rows
        cols = state.cols
        mode = state.mode
        prompt_prefix = state.prompt_prefix
        prompt_buffer = state.prompt_buffer
    out = ["\x1b[?25l\x1b[H"]
    for line in visible:
        if pattern is not None:
            line = _highlight_matches(line, pattern)
        out.append(line)
        out.append("\x1b[K\n")
    for _ in range(body_rows - len(visible)):
        out.append("\x1b[K\n")
    out.append(f"\x1b[{rows};1H")
    if mode == "prompt":
        prompt = (prompt_prefix + prompt_buffer)[:cols - 1]
        out.append(prompt)
        out.append("\x1b[K")
        out.append("\x1b[?25h")  # show cursor while prompting
    else:
        out.append("\x1b[7m")
        out.append(status)
        out.append("\x1b[0m\x1b[K")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def _watcher_thread(state: _WatchState) -> None:
    last_mtime = -1.0
    while not state.stop.is_set():
        try:
            mtime = state.file.stat().st_mtime
        except FileNotFoundError:
            mtime = -1.0
        if mtime != last_mtime:
            last_mtime = mtime
            lines = _render_lines(state)
            with state.lock:
                state.lines = lines
                state.last_reload = time.time()
                _clamp_offset(state)
                _recompute_matches(state)
            state.dirty.set()
        state.stop.wait(0.3)


def _read_key(timeout: float) -> str | None:
    try:
        r, _, _ = select.select([sys.stdin], [], [], timeout)
    except (InterruptedError, OSError):
        return None
    if not r:
        return None
    ch = sys.stdin.read(1)
    if ch != "\x1b":
        return ch
    r, _, _ = select.select([sys.stdin], [], [], 0.02)
    if not r:
        return "\x1b"
    seq = "\x1b" + sys.stdin.read(1)
    if seq == "\x1b[":
        while True:
            r, _, _ = select.select([sys.stdin], [], [], 0.02)
            if not r:
                break
            c = sys.stdin.read(1)
            seq += c
            if c.isalpha() or c == "~":
                break
    return seq


def _handle_prompt_key(state: _WatchState, key: str) -> str | None:
    if key == "\x1b":
        state.mode = "normal"
        state.prompt_buffer = ""
        state.status_msg = ""
        return "redraw"
    if key in ("\r", "\n"):
        prefix, buf = state.prompt_prefix, state.prompt_buffer
        state.mode = "normal"
        state.prompt_buffer = ""
        if prefix == "/":
            _do_search(state, buf)
        elif prefix == ":":
            cmd = buf.strip()
            if cmd in ("q", "quit"):
                return "quit"
            if cmd in ("r", "reload"):
                lines = _render_lines(state)
                with state.lock:
                    state.lines = lines
                    state.last_reload = time.time()
                    _clamp_offset(state)
                    _recompute_matches(state)
                state.status_msg = "reloaded"
            elif cmd == "":
                state.status_msg = ""
            else:
                state.status_msg = f"unknown command: :{cmd}"
        return "redraw"
    if key in ("\x7f", "\x08"):
        state.prompt_buffer = state.prompt_buffer[:-1]
        return "redraw"
    if len(key) == 1 and key >= " " and key != "\x7f":
        state.prompt_buffer += key
        return "redraw"
    return None


def _handle_mouse(state: _WatchState, key: str) -> str | None:
    m = MOUSE_RE.match(key)
    if not m:
        return None
    btn, _, _, action = int(m.group(1)), m.group(2), m.group(3), m.group(4)
    if action != "M":
        return "redraw"  # ignore release events
    if btn == 64:
        with state.lock:
            state.offset -= MOUSE_SCROLL_LINES
            _clamp_offset(state)
        return "redraw"
    if btn == 65:
        with state.lock:
            state.offset += MOUSE_SCROLL_LINES
            _clamp_offset(state)
        return "redraw"
    return "redraw"


def _handle_key(state: _WatchState, key: str) -> str | None:
    if key.startswith("\x1b[<"):
        return _handle_mouse(state, key)
    if state.mode == "prompt":
        return _handle_prompt_key(state, key)
    if key == "/":
        state.mode = "prompt"
        state.prompt_prefix = "/"
        state.prompt_buffer = ""
        state.status_msg = ""
        return "redraw"
    if key == ":":
        state.mode = "prompt"
        state.prompt_prefix = ":"
        state.prompt_buffer = ""
        state.status_msg = ""
        return "redraw"
    if key == "n":
        with state.lock:
            _jump_to_match(state, forward=True)
        return "redraw"
    if key == "N":
        with state.lock:
            _jump_to_match(state, forward=False)
        return "redraw"
    with state.lock:
        body_rows = max(1, state.rows - 1)
        page = max(1, body_rows - 1)
        if key in ("q", "\x03"):
            return "quit"
        elif key in ("j", "\x1b[B"):
            state.offset += 1
        elif key in ("k", "\x1b[A"):
            state.offset -= 1
        elif key in (" ", "\x1b[6~"):
            state.offset += page
        elif key in ("b", "\x1b[5~"):
            state.offset -= page
        elif key in ("g", "\x1b[H"):
            state.offset = 0
        elif key in ("G", "\x1b[F"):
            state.offset = len(state.lines)
        else:
            return None
        _clamp_offset(state)
    return "redraw"


def watch_loop(file: str, width: int | None, theme_name: str,
               code_override: str | None) -> int:
    state = _WatchState(file, width, theme_name, code_override)

    if not sys.stdin.isatty():
        print("innomd: --watch requires an interactive terminal on stdin",
              file=sys.stderr)
        return 1

    with state.lock:
        state.lines = _render_lines(state)
        _clamp_offset(state)
    state.dirty.set()

    old_termios = termios.tcgetattr(sys.stdin)
    sys.stdout.write("\x1b[?1049h\x1b[?25l\x1b[?1000h\x1b[?1006h")
    sys.stdout.flush()
    tty.setcbreak(sys.stdin.fileno())

    def on_resize(*_args) -> None:
        state.resize_pending = True

    prev_winch = signal.getsignal(signal.SIGWINCH) if hasattr(signal, "SIGWINCH") else None
    if hasattr(signal, "SIGWINCH"):
        signal.signal(signal.SIGWINCH, on_resize)

    watcher = threading.Thread(target=_watcher_thread, args=(state,), daemon=True)
    watcher.start()

    try:
        while not state.stop.is_set():
            if state.resize_pending:
                state.resize_pending = False
                cols, rows = _term_size()
                with state.lock:
                    state.cols, state.rows = cols, rows
                lines = _render_lines(state)
                with state.lock:
                    state.lines = lines
                    _clamp_offset(state)
                    _recompute_matches(state)
                state.dirty.set()
            if state.dirty.is_set():
                state.dirty.clear()
                _draw(state)
            key = _read_key(0.1)
            if key is None:
                continue
            action = _handle_key(state, key)
            if action == "quit":
                break
            if action == "redraw":
                state.dirty.set()
    except KeyboardInterrupt:
        pass
    finally:
        state.stop.set()
        if hasattr(signal, "SIGWINCH") and prev_winch is not None:
            signal.signal(signal.SIGWINCH, prev_winch)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_termios)
        sys.stdout.write("\x1b[?1006l\x1b[?1000l\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()

    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        prog="innomd",
        description="Terminal Markdown viewer with LaTeX math, Jupyter notebooks, themes, and live reload.",
    )
    p.add_argument("file", nargs="?", help="markdown or ipynb file (reads stdin if omitted)")
    p.add_argument("-P", "--no-pager", action="store_true", help="do not page output")
    p.add_argument("-r", "--raw", action="store_true", help="print preprocessed markdown without rendering")
    p.add_argument("-w", "--width", type=int, default=None, help="terminal width in columns")
    p.add_argument("-t", "--theme", default="default",
                   help=f"preset theme: {', '.join(THEMES)}")
    p.add_argument("-c", "--code-theme", default=None,
                   help="override pygments code theme (e.g. monokai, dracula, nord)")
    p.add_argument("-W", "--watch", action="store_true",
                   help="live-reload: re-render when the file changes")
    p.add_argument("--list-themes", action="store_true", help="list available themes and exit")
    p.add_argument("-V", "--version", action="version",
                   version=f"innomd {__version__}")
    args = p.parse_args()

    if args.list_themes:
        for name in THEMES:
            print(name)
        return 0

    if args.theme not in THEMES:
        print(f"innomd: unknown theme '{args.theme}'. Available: {', '.join(THEMES)}",
              file=sys.stderr)
        return 1

    if args.watch:
        if not args.file:
            print("innomd: --watch requires a file argument", file=sys.stderr)
            return 1
        return watch_loop(args.file, args.width, args.theme, args.code_theme)

    try:
        text = load_source(args.file)
    except FileNotFoundError:
        print(f"innomd: file not found: {args.file}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as e:
        print(f"innomd: encoding error: {e}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"innomd: invalid notebook JSON: {e}", file=sys.stderr)
        return 1

    processed = preprocess(text)

    if args.raw:
        sys.stdout.write(processed)
        return 0

    try:
        use_pager = (not args.no_pager) and sys.stdout.isatty()
        render_once(processed, args.width, args.theme, args.code_theme, use_pager)
    except ImportError:
        print("innomd: 'rich' is not installed — install with: pip install rich",
              file=sys.stderr)
        return 1
    return 0
