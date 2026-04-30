"""Exceptions raised by the diagram pipeline. Internal — never escapes the public API."""
from __future__ import annotations


class DiagramError(Exception):
    """Base for any pipeline failure."""


class AdapterError(DiagramError):
    """Source-format parsing failed."""


class LayoutError(DiagramError):
    """Layout engine failed (e.g. grandalf could not place a graph)."""


class RenderError(DiagramError):
    """Renderer could not produce output (e.g. graph too large for width)."""
