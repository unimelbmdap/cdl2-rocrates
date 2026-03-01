"""Inspectors — tools for examining data files referenced by entities."""

from __future__ import annotations

from typing import TYPE_CHECKING

from crategraph.core.interfaces import Inspector
from crategraph.core.models import FileInfo

if TYPE_CHECKING:
    from crategraph.core.models import Entity

__all__ = ["FileInfo", "Inspector", "find_inspector"]

# Registry of inspector classes, ordered by priority (first match wins).
# Custom inspectors should be prepended to take priority over MarkItDown.
_INSPECTOR_CLASSES: list[type[Inspector]] = []


def _ensure_registry() -> None:
    """Lazily populate the registry with available inspectors."""
    if _INSPECTOR_CLASSES:
        return
    try:
        from crategraph.inspectors.markitdown import MarkItDownInspector

        _INSPECTOR_CLASSES.append(MarkItDownInspector)
    except ImportError:
        pass


def find_inspector(entity: Entity) -> Inspector | None:
    """Return the first inspector that supports the given entity, or None."""
    _ensure_registry()
    for cls in _INSPECTOR_CLASSES:
        inspector = cls()
        if inspector.supports(entity):
            return inspector
    return None
