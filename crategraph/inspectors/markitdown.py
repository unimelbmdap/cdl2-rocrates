"""MarkItDown-backed inspector — default engine for file inspection."""

from __future__ import annotations

from pathlib import Path

from crategraph.core.interfaces import Inspector
from crategraph.core.models import FileInfo


class MarkItDownInspector(Inspector):
    """Inspector that delegates to the markitdown package."""

    def supports(self, path: Path) -> bool:
        """Return True if *path* points to an existing local file."""
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
