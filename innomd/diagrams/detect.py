"""Detect which fenced code blocks are diagrams we know how to render."""
from __future__ import annotations

import re

# Mermaid is currently the only supported source. Phase-2 will add dot/plantuml.
KNOWN_LANGS = frozenset({"mermaid"})

_FENCE_HEADER = re.compile(r"^```\s*([A-Za-z0-9_+-]+)\s*$")


def fence_language(first_line: str) -> str | None:
    """Return the language token from the opening fence line, or None.

    Accepts ``` followed by an optional language identifier. Anything else
    (e.g. ```mermaid title="x") is conservatively rejected for now — we'd
    rather fall back than misparse.
    """
    m = _FENCE_HEADER.match(first_line.strip())
    return m.group(1).lower() if m else None


def is_diagram_lang(lang: str | None) -> bool:
    return lang in KNOWN_LANGS if lang else False
