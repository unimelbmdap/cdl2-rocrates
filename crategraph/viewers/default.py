"""Default viewer — stdlib-only rich HTML previews for common file types."""

from __future__ import annotations

import base64
import csv
import mimetypes
from html import escape as _escape_html
from pathlib import Path
from typing import TYPE_CHECKING

from crategraph.core.interfaces import Viewer
from crategraph.core.models import ViewInfo

if TYPE_CHECKING:
    from crategraph.core.models import Entity

# Maximum rows to show for CSV/tabular previews.
_MAX_TABLE_ROWS = 50

# Maximum characters to show for text previews.
_MAX_TEXT_CHARS = 5000


def _resolve_entity_path(entity: Entity) -> Path | None:
    """Resolve the file path for an entity, or None if not a data file."""
    entity_id = entity.properties.get("raw_id", entity.id)
    if entity_id.startswith("#") or entity_id.startswith("http"):
        return None
    if entity.source is None:
        return None
    crate_root = Path(entity.source)
    file_path = crate_root / entity_id
    crate_root_resolved = crate_root.resolve(strict=False)
    try:
        file_path_resolved = file_path.resolve(strict=False)
        file_path_resolved.relative_to(crate_root_resolved)
    except ValueError:
        return None
    return file_path_resolved


def _view_image(path: Path, media_type: str) -> str:
    """Produce an <img> tag with base64-encoded image data."""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f"<img src='data:{_escape_html(media_type)};base64,{data}' "
        f"style='max-width:100%; max-height:480px; border-radius:4px'/>"
    )


def _view_csv(path: Path) -> str:
    """Produce an HTML table from a CSV file."""
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        rows = []
        for i, row in enumerate(reader):
            if i > _MAX_TABLE_ROWS:
                break
            rows.append(row)

    if not rows:
        return "<p><em>Empty CSV file</em></p>"

    parts = [
        "<table style='border-collapse:collapse; font-size:13px; "
        "font-family:monospace; width:100%'>",
    ]

    # Header row.
    parts.append("<thead><tr>")
    for cell in rows[0]:
        parts.append(
            f"<th style='border:1px solid #ddd; padding:6px 8px; "
            f"background:#f0f0f0; text-align:left'>{_escape_html(cell)}</th>"
        )
    parts.append("</tr></thead>")

    # Data rows.
    parts.append("<tbody>")
    for row in rows[1:]:
        parts.append("<tr>")
        for cell in row:
            parts.append(
                f"<td style='border:1px solid #ddd; padding:4px 8px'>{_escape_html(cell)}</td>"
            )
        parts.append("</tr>")
    parts.append("</tbody></table>")

    truncated = len(rows) > _MAX_TABLE_ROWS
    if truncated:
        parts.append(
            f"<p style='font-size:12px; color:#888'>Showing first {_MAX_TABLE_ROWS} rows</p>"
        )

    return "".join(parts)


def _view_text(path: Path) -> str:
    """Produce a <pre> block with the file's text content."""
    content = path.read_text(encoding="utf-8", errors="replace")[:_MAX_TEXT_CHARS]
    return (
        f"<pre style='white-space:pre-wrap; padding:8px; "
        f"background:#f5f5f5; border-radius:4px; font-size:13px; "
        f"max-height:400px; overflow-y:auto'>{_escape_html(content)}</pre>"
    )


def _view_audio(path: Path, media_type: str) -> str:
    """Produce an <audio> tag with base64-encoded audio data."""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f"<audio controls style='width:100%'>"
        f"<source src='data:{_escape_html(media_type)};base64,{data}' "
        f"type='{_escape_html(media_type)}'/>"
        f"Your browser does not support the audio element."
        f"</audio>"
    )


def _view_pdf(path: Path) -> str:
    """Produce a PDF preview -- embed via base64 <object> tag."""
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f"<object data='data:application/pdf;base64,{data}' "
        f"type='application/pdf' "
        f"style='width:100%; height:500px; border-radius:4px'>"
        f"<p>PDF preview not supported in this environment. "
        f"File: {_escape_html(path.name)}</p>"
        f"</object>"
    )


def _guess_media_type(path: Path) -> str:
    """Guess the MIME type from the file extension."""
    mt, _ = mimetypes.guess_type(str(path))
    return mt or "application/octet-stream"


class DefaultViewer(Viewer):
    """Stdlib-only viewer for common file types.

    Handles images (base64 ``<img>``), CSV (HTML ``<table>``),
    plain text (``<pre>``), audio (``<audio>``), and PDF
    (``<object>``).  Falls back to a text preview for
    unrecognised types.
    """

    def supports(self, entity: Entity) -> bool:
        """Return True if the entity points to an existing local file."""
        path = _resolve_entity_path(entity)
        if path is None:
            return False
        return path.is_file()

    def view(self, path: Path) -> ViewInfo:
        """Produce a rich HTML preview of the file."""
        media_type = _guess_media_type(path)
        category = media_type.split("/")[0]

        if category == "image":
            html = _view_image(path, media_type)
        elif media_type in ("text/csv", "text/tab-separated-values"):
            html = _view_csv(path)
        elif category == "audio":
            html = _view_audio(path, media_type)
        elif media_type == "application/pdf":
            html = _view_pdf(path)
        else:
            # Fallback: try as text.
            html = _view_text(path)

        return ViewInfo(
            path=str(path),
            html=html,
            title=path.stem,
            size_bytes=path.stat().st_size,
            media_type=media_type,
        )
