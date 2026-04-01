"""MarkItDown-backed inspector — default engine for file inspection."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from crategraph.core._files import resolve_entity_path
from crategraph.core.interfaces import Inspector
from crategraph.core.models import FileInfo

if TYPE_CHECKING:
    from crategraph.core.models import Entity


class MarkItDownInspector(Inspector):
    """Inspector that delegates to the markitdown package."""

    def supports(self, entity: Entity) -> bool:
        """Return True if the entity points to an existing local file."""
        path = resolve_entity_path(entity)
        if path is None:
            return False
        return path.is_file()

    def inspect(self, path: Path) -> FileInfo:
        """Convert the file to markdown using MarkItDown."""
        try:
            from markitdown import MarkItDown
        except ImportError:
            msg = (
                "markitdown is required for file inspection. "
                "Install it with: pip install crategraph[inspect]"
            )
            raise ImportError(msg) from None

        md = MarkItDown()
        result = md.convert(path)

        return FileInfo(
            path=str(path),
            content=result.markdown or "",
            title=result.title,
            size_bytes=path.stat().st_size,
            media_type=None,
        )
