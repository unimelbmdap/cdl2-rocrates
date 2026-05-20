"""MarkItDown-backed inspector — default engine for file inspection."""

from __future__ import annotations

import mimetypes
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
        try:
            result = md.convert(path)
        except Exception as exc:
            if _is_text_decode_failure(path, exc):
                return FileInfo(
                    path=str(path),
                    content=path.read_text(encoding="utf-8", errors="replace"),
                    title=None,
                    size_bytes=path.stat().st_size,
                    media_type=mimetypes.guess_type(path)[0],
                )
            raise

        return FileInfo(
            path=str(path),
            content=result.markdown or "",
            title=result.title,
            size_bytes=path.stat().st_size,
            media_type=None,
        )


def _is_text_decode_failure(path: Path, exc: Exception) -> bool:
    """Whether MarkItDown failed decoding a text-like file."""
    media_type = mimetypes.guess_type(path)[0]
    is_text_like = (
        media_type is not None and media_type.startswith("text/")
    ) or path.suffix.lower() in {".txt", ".text", ".md", ".csv", ".tsv", ".xml"}
    return is_text_like and (
        isinstance(exc, UnicodeDecodeError) or "UnicodeDecodeError" in str(exc)
    )
