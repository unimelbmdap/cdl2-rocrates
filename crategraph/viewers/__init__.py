"""Viewers — tools for producing rich HTML previews of data files."""

from __future__ import annotations

from pathlib import Path

from crategraph.core.interfaces import Viewer
from crategraph.core.models import ViewInfo

__all__ = ["ViewInfo", "Viewer", "find_viewer"]

# Registry of viewer classes, ordered by priority (first match wins).
# Custom viewers should be prepended to take priority over DefaultViewer.
_VIEWER_CLASSES: list[type[Viewer]] = []


def _ensure_registry() -> None:
    """Lazily populate the registry with available viewers."""
    if _VIEWER_CLASSES:
        return
    from crategraph.viewers.default import DefaultViewer

    _VIEWER_CLASSES.append(DefaultViewer)


def find_viewer(path: Path) -> Viewer | None:
    """Return the first viewer that supports the given file path, or None."""
    _ensure_registry()
    for cls in _VIEWER_CLASSES:
        viewer = cls()
        if viewer.supports(path):
            return viewer
    return None
