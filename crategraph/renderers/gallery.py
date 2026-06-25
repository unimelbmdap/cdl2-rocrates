"""Render a graph's image-bearing entities as a self-contained thumbnail grid.

A *gallery* is a visual artifact built from a graph, like ``glimpse()``, so it is
a :class:`~crategraph.core.interfaces.Renderer`, not a writer. It finds the entities
that carry an image (a ``thumbnail`` property, or an image ``File`` itself), embeds
each as a base64 data-URI, and lays them out in a CSS grid. Dependency-free: only the
standard library (``base64``, ``html.escape``, ``mimetypes`` via the viewers helper).
"""

from __future__ import annotations

import base64
import warnings
from collections.abc import Sequence
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core._files import resolve_entity_path
from crategraph.core.interfaces import Renderer
from crategraph.viewers.default import _guess_media_type

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity
    from crategraph.core.views import EntityView

# Default cap on embedded thumbnails. Every image is base64-embedded inline, so
# an unbounded gallery on a large crate produces an enormous document; the cap
# keeps the common case safe while ``limit=None`` remains an explicit opt-out.
# 48 is a multiple of the default column count (12 full rows of 4).
_DEFAULT_LIMIT = 48

# Image suffixes recognised when an entity declares no (or a vague) media type.
_IMAGE_EXTENSIONS = frozenset(
    {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff", ".avif"}
)

_EMPTY = (
    '<div class="cg-gallery-empty" '
    'style="padding:16px;color:#888;font-family:system-ui,sans-serif">'
    "No images found</div>"
)


class GalleryRenderer(Renderer):
    """Lay a graph's image-bearing entities out as a thumbnail grid."""

    def render(
        self,
        graph: Graph,
        *,
        caption: str | None = "label",
        hover: str | Sequence[str] | None = None,
        columns: int = 4,
        limit: int | None = _DEFAULT_LIMIT,
        filepath: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Render *graph* as a thumbnail gallery.

        Args:
            caption: Property shown as an always-visible caption below each
                thumbnail. The special value ``"label"`` (the default) uses the
                entity's human label (``name`` -> ``title`` -> ``id``). ``None``
                shows no caption.
            hover: Property, or sequence of properties, shown as the native
                ``title`` tooltip on hover. Multiple values are joined with
                ``" · "``. ``None`` (the default) adds no tooltip.
            columns: Number of grid columns.
            limit: Cap on the number of thumbnails (every image is embedded
                inline, so this bounds the output size). Defaults to
                ``100``; when more images are available the gallery shows the
                first *limit* and warns. Pass ``None`` to embed them all, or
                filter the graph first (e.g. ``graph.where(...)``).
            filepath: When given, write a self-contained HTML page there and
                return the path. Otherwise return an ``IPython.display.HTML``.
        """
        items = _gallery_items(graph)
        total = len(items)
        if limit is not None and limit <= 0:
            items = []
        elif limit is not None:
            items = items[:limit]
        if limit is not None and 0 < limit < total:
            warnings.warn(
                f"gallery() is showing the first {limit} of {total} images. "
                f"Filter the graph before calling gallery() (e.g. "
                f"graph.where(...)) or pass a larger limit= to include more.",
                stacklevel=2,
            )
        if not items:
            return _output(_EMPTY, filepath)

        cells: list[str] = []
        for entity, path, media in items:
            try:
                raw = path.read_bytes()
            except OSError:
                # File vanished or became unreadable between discovery and now;
                # skip this thumbnail rather than aborting the whole gallery.
                continue
            view = graph.entity_view(entity.id)
            caption_text = _resolve_caption(view, caption)
            hover_text = _resolve_hover(view, hover)
            data = base64.b64encode(raw).decode("ascii")
            overlay_html = (
                f'<span class="cg-hover">{escape(hover_text)}</span>' if hover_text else ""
            )
            caption_html = (
                f'<figcaption class="cg-caption">{escape(caption_text)}</figcaption>'
                if caption_text
                else ""
            )
            cells.append(
                f'<figure class="cg-cell">'
                f'<span class="cg-frame">'
                f'<img src="data:{escape(media)};base64,{data}" alt="{escape(caption_text)}">'
                f"{overlay_html}</span>"
                f"{caption_html}</figure>"
            )

        if not cells:
            return _output(_EMPTY, filepath)
        return _output(_build_fragment(cells, columns), filepath)


# ---------------------------------------------------------------------------
# Item detection
# ---------------------------------------------------------------------------


def _gallery_items(graph: Graph) -> list[tuple[Entity, Path, str]]:
    """Collect ``(entity, image_path, media_type)`` for every image-bearing entity.

    Prefers entities that carry a ``thumbnail`` (small, curated previews); only
    when none do does it fall back to image ``File`` entities. Resolved paths are
    de-duplicated so the same image is never collected twice. Choosing *which*
    images, and *how many*, is the caller's job: filter the graph, then cap with
    ``limit`` at the render layer.
    """
    source = graph.source
    seen: set[Path] = set()
    items: list[tuple[Entity, Path, str]] = []

    def _take(entity: Entity, path: Path, media: str) -> None:
        if path in seen:
            return
        seen.add(path)
        items.append((entity, path, media))

    # Pass 1: entities carrying a thumbnail property.
    for entity in graph.entities:
        thumb = entity.properties.get("thumbnail")
        if not thumb:
            continue
        path = _resolve_thumbnail(thumb, entity.source or source)
        if path is None:
            continue
        _take(entity, path, _guess_media_type(path))
    if items:
        return items

    # Pass 2: data entities that are themselves image files.
    for entity in graph.entities:
        if not entity.has_data:
            continue
        path = resolve_entity_path(entity, fallback_source=entity.source or source)
        if path is None or not path.is_file():
            continue
        media = _entity_media_type(entity, path)
        if not _is_image(path, media):
            continue
        _take(entity, path, media)
    return items


def _resolve_thumbnail(thumb: Any, source: str | None) -> Path | None:
    """Resolve a ``thumbnail`` value (dict ``@id``, string, or list) to a local file.

    A list is tried in order, returning the first member that resolves to an
    existing local file, so a missing or remote first entry does not mask a
    valid later one.
    """
    if source is None:
        return None
    candidates = thumb if isinstance(thumb, list) else [thumb]
    for item in candidates:
        path = _resolve_one_thumbnail(item, source)
        if path is not None:
            return path
    return None


def _resolve_one_thumbnail(item: Any, source: str) -> Path | None:
    """Resolve a single thumbnail reference (dict ``@id`` or string) to a local file."""
    if isinstance(item, dict):
        item = item.get("@id")
    if not isinstance(item, str) or not item:
        return None
    if item.startswith(("#", "http://", "https://")):
        return None

    base = Path(source).resolve(strict=False)
    candidate = (base / item).resolve(strict=False)
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _entity_media_type(entity: Entity, path: Path) -> str:
    """Media type from the entity's ``encodingFormat``, else guessed from *path*.

    Preferring the declared format lets extensionless image files (a ``File``
    with ``encodingFormat`` ``image/jpeg`` but no suffix) be recognised.
    """
    fmt = _first(entity.properties.get("encodingFormat"))
    if isinstance(fmt, str) and "/" in fmt:
        return fmt
    return _guess_media_type(path)


def _is_image(path: Path, media: str) -> bool:
    """Whether *path*/*media* names an image."""
    return media.split("/")[0] == "image" or path.suffix.lower() in _IMAGE_EXTENSIONS


# ---------------------------------------------------------------------------
# Caption / hover resolution
# ---------------------------------------------------------------------------


def _first(value: Any) -> Any:
    """Unwrap a property crategraph returns as a list when multi-valued."""
    return value[0] if isinstance(value, list) else value


def _resolve_caption(view: EntityView, caption: str | None) -> str:
    if not caption:
        return ""
    if caption == "label":
        return str(view.label or "")
    value = _first(view.get(caption))
    return "" if value is None else str(value)


def _resolve_hover(view: EntityView, hover: str | Sequence[str] | None) -> str:
    if not hover:
        return ""
    fields = [hover] if isinstance(hover, str) else list(hover)
    parts: list[str] = []
    for field in fields:
        value = _first(view.get(field))
        if value is not None and str(value) != "":
            parts.append(str(value))
    return " · ".join(parts)


# ---------------------------------------------------------------------------
# HTML assembly
# ---------------------------------------------------------------------------


# Cap each column's width so thumbnails stay thumbnail-sized rather than
# ballooning (and upscaling) to fill a wide screen at a low column count.
_MAX_COLUMN_PX = 220


def _build_fragment(cells: list[str], columns: int) -> str:
    """Build a scoped, self-contained gallery fragment (style + grid div)."""
    cols = max(1, int(columns))
    # ``minmax(0, 1fr)`` lets columns divide evenly and shrink below the image's
    # intrinsic width; images keep their natural aspect ratio (no cropping) so a
    # tall document is shown whole, not squared off.
    style = (
        ".cg-gallery{display:grid;"
        f"grid-template-columns:repeat({cols},minmax(0,1fr));"
        f"gap:8px;align-items:start;max-width:{cols * _MAX_COLUMN_PX}px;"
        "margin:0 auto;font-family:system-ui,-apple-system,sans-serif}"
        ".cg-gallery .cg-cell{margin:0;display:flex;flex-direction:column;gap:4px}"
        # The frame holds the image and the hover overlay on top of it.
        ".cg-gallery .cg-frame{position:relative;display:block}"
        ".cg-gallery .cg-frame img{width:100%;height:auto;display:block;"
        "border-radius:4px;background:#fff}"
        # Hover overlay: fades in over the image, revealing the hover text.
        ".cg-gallery .cg-hover{position:absolute;inset:0;display:flex;align-items:center;"
        "justify-content:center;box-sizing:border-box;padding:8px;border-radius:4px;"
        "color:#fff;font-size:12px;line-height:1.35;text-align:center;"
        "background:rgba(0,0,0,.72);opacity:0;transition:opacity .15s}"
        ".cg-gallery .cg-frame:hover .cg-hover{opacity:1}"
        # Caption below the image: wraps to as many lines as the text needs.
        ".cg-gallery .cg-caption{font-size:12px;color:#333;text-align:center;line-height:1.35}"
    )
    return f'<style>{style}</style><div class="cg-gallery">{"".join(cells)}</div>'


def _output(fragment: str, filepath: str | None) -> Any:
    """Return an ``IPython.display.HTML`` or write a standalone page to *filepath*."""
    if filepath:
        doc = (
            '<!doctype html><html><head><meta charset="utf-8">'
            "<style>html,body{margin:0;padding:0;background:#fafafa}</style>"
            f"</head><body>{fragment}</body></html>"
        )
        Path(filepath).write_text(doc, encoding="utf-8")
        return filepath
    from IPython.display import HTML

    return HTML(fragment)
