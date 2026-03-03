"""Viewers — tools for producing rich HTML previews of data files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from crategraph.core.interfaces import Viewer
from crategraph.core.models import ViewInfo

if TYPE_CHECKING:
    from crategraph.core.models import Entity

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


def find_viewer(entity: Entity) -> Viewer | None:
    """Return the first viewer that supports the given entity, or None."""
    _ensure_registry()
    for cls in _VIEWER_CLASSES:
        viewer = cls()
        if viewer.supports(entity):
            return viewer
    return None
