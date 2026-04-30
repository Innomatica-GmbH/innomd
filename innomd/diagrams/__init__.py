"""Diagram engine: parse fenced diagram blocks into ASCII/Unicode renderings."""
from __future__ import annotations

from .errors import AdapterError, DiagramError, LayoutError
from .public import render_mermaid

__all__ = ["render_mermaid", "DiagramError", "AdapterError", "LayoutError"]
