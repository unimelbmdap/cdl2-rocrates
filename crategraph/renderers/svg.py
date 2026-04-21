"""General-purpose SVG renderer for crategraph graphs."""

from __future__ import annotations

import math
from html import escape as _esc
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core.interfaces import Renderer
from crategraph.renderers._colours import resolve_colour_map
from crategraph.renderers._edge_width import resolve_edge_widths

if TYPE_CHECKING:
    from crategraph.core.graph import Graph

# Default display size (CSS pixels).  The internal coordinate space is
# always twice this so the layout has room to breathe; the browser
# scales it down via the SVG ``viewBox``.
DEFAULT_WIDTH = 600
DEFAULT_HEIGHT = 450


class SvgRenderer(Renderer):
    """Render a graph as an inline SVG image.

    Works with both raw graphs (sizing by degree) and merged/aggregated
    graphs (sizing by ``count`` property).
    """

    def render(
        self,
        graph: Graph,
        *,
        colour_by: str = "type",
        edge_width: int | float | str | None = None,
        width: int | str = DEFAULT_WIDTH,
        height: int | str = DEFAULT_HEIGHT,
        filepath: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Render *graph* and return an ``IPython.display.SVG`` or filepath.

        Args:
            graph: The graph to render.
            colour_by: Entity attribute or property used to assign colours.
                ``"type"`` (default) colours by primary type.
            edge_width: Per-edge stroke width. ``None`` (default) keeps
                the existing ``1 + 3*(weight/max_weight)`` auto-width.
                A number sets every edge to that pixel width (compensated
                for the 2x viewBox so it renders at the requested CSS
                pixel width). A string is treated as a property name and
                width-encodes via ``1 + 2*log1p(v)``.
            width: Display width in CSS pixels (default 600).
            height: Display height in CSS pixels (default 450).
            filepath: If given, save the SVG to this path and return it.

        Returns:
            An ``IPython.display.SVG`` object (for notebook display) or the
            *filepath* string if a file was written.
        """
        # Accept CSS strings from visualise() — fall back to defaults.
        if not isinstance(width, (int, float)):
            width = DEFAULT_WIDTH
        if not isinstance(height, (int, float)):
            height = DEFAULT_HEIGHT

        # Internal coordinate space is 2x the display size so the
        # layout has room; viewBox handles the scaling.
        vb_w = float(width * 2)
        vb_h = float(height * 2)

        if not graph._entities:
            svg = _empty_svg(width, height, vb_w, vb_h)
            return _output(svg, filepath)

        # Detect sizing mode: merged graphs have a ``count`` property.
        first_entity = next(iter(graph._entities.values()))
        use_count = "count" in first_entity.properties

        if use_count:
            size_values = {eid: e.properties.get("count", 1) for eid, e in graph._entities.items()}
        else:
            size_values = {eid: len(graph._neighbours(eid)) for eid in graph._entities}

        max_val = max(size_values.values()) if size_values else 1

        # Scale node radii proportionally to the canvas.
        scale = min(vb_w, vb_h) / 600.0
        radii = {nid: _node_radius(v, max_val, scale=scale) for nid, v in size_values.items()}

        # Dynamic padding: ensure the largest node fits within the canvas.
        max_radius = max(radii.values()) if radii else 16.0 * scale
        pad = max(80.0 * scale, max_radius + 30.0 * scale)

        raw_positions = graph.layout()
        positions = _scale_positions(raw_positions, pad=pad, width=vb_w, height=vb_h)
        _resolve_overlaps(positions, radii, width=vb_w, height=vb_h, pad=pad)
        colour_map = resolve_colour_map(graph, colour_by)
        svg = _build_svg(
            graph,
            positions,
            colour_map,
            radii=radii,
            display_width=width,
            display_height=height,
            vb_width=vb_w,
            vb_height=vb_h,
            scale=scale,
            edge_width=edge_width,
        )
        return _output(svg, filepath)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _output(svg: str, filepath: str | None) -> Any:
    """Return an ``IPython.display.SVG`` or write to *filepath*."""
    if filepath:
        Path(filepath).write_text(svg, encoding="utf-8")
        return filepath
    from IPython.display import SVG

    return SVG(data=svg)


def _empty_svg(
    display_width: int,
    display_height: int,
    vb_width: float,
    vb_height: float,
) -> str:
    """Return an SVG placeholder for empty graphs."""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{display_width}" height="{display_height}" '
        f'viewBox="0 0 {vb_width} {vb_height}">'
        f'<text x="{vb_width / 2}" y="{vb_height / 2}" text-anchor="middle" '
        f'font-family="system-ui, sans-serif" font-size="16" '
        f'fill="#888">Empty graph</text></svg>'
    )


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


def _scale_positions(
    raw: dict[str, tuple[float, float]],
    *,
    width: float = 1200,
    height: float = 900,
    pad: float = 80,
) -> dict[str, tuple[float, float]]:
    """Scale raw layout positions to canvas coordinates with padding."""
    if not raw:
        return {}

    xs = [p[0] for p in raw.values()]
    ys = [p[1] for p in raw.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    range_x = max_x - min_x or 1.0
    range_y = max_y - min_y or 1.0

    return {
        nid: (
            pad + (p[0] - min_x) / range_x * (width - 2 * pad),
            pad + (p[1] - min_y) / range_y * (height - 2 * pad),
        )
        for nid, p in raw.items()
    }


def _resolve_overlaps(
    positions: dict[str, tuple[float, float]],
    radii: dict[str, float],
    *,
    width: float,
    height: float,
    pad: float,
    iterations: int = 50,
) -> None:
    """Push overlapping circles apart in canvas space (mutates *positions*)."""
    nodes = list(positions.keys())
    if len(nodes) < 2:
        return

    label_gap = 16.0  # extra space for labels below circles

    def _clamp(nid: str, x: float, y: float) -> tuple[float, float]:
        r = radii.get(nid, 16.0)
        x = max(pad + r, min(width - pad - r, x))
        y = max(pad + r, min(height - pad - r - label_gap, y))
        return x, y

    for _ in range(iterations):
        moved = False
        for i, a in enumerate(nodes):
            ra = radii.get(a, 16.0)
            ax, ay = positions[a]
            for b in nodes[i + 1 :]:
                rb = radii.get(b, 16.0)
                bx, by = positions[b]
                dx = ax - bx
                dy = ay - by
                dist = math.sqrt(dx * dx + dy * dy)
                min_sep = ra + rb + label_gap
                if dist < min_sep:
                    if dist < 0.001:
                        dx, dy, dist = 1.0, 0.0, 1.0
                    overlap = (min_sep - dist) / 2.0 + 2.0
                    nx_ = dx / dist * overlap
                    ny_ = dy / dist * overlap
                    ax, ay = _clamp(a, ax + nx_, ay + ny_)
                    bx, by = _clamp(b, bx - nx_, by - ny_)
                    # If one node hit a wall, give the full push to the other.
                    dx2 = ax - bx
                    dy2 = ay - by
                    dist2 = math.sqrt(dx2 * dx2 + dy2 * dy2)
                    if dist2 < min_sep and dist2 > 0.001:
                        extra = min_sep - dist2 + 1.0
                        ex = dx2 / dist2 * extra
                        ey = dy2 / dist2 * extra
                        ax, ay = _clamp(a, ax + ex * 0.5, ay + ey * 0.5)
                        bx, by = _clamp(b, bx - ex * 0.5, by - ey * 0.5)
                    positions[a] = (ax, ay)
                    positions[b] = (bx, by)
                    moved = True
        if not moved:
            break


def _node_radius(count: int, max_count: int, *, scale: float = 1.0) -> float:
    """Scale node radius by entity count. Range: 12-50 (at scale 1.0)."""
    if max_count <= 0:
        return 20.0 * scale
    normalised = count / max_count
    return (12.0 + 38.0 * math.sqrt(normalised)) * scale


# ---------------------------------------------------------------------------
# SVG assembly
# ---------------------------------------------------------------------------


def _build_svg(
    graph: Graph,
    positions: dict[str, tuple[float, float]],
    colour_map: dict[str, str],
    *,
    radii: dict[str, float],
    display_width: int,
    display_height: int,
    vb_width: float,
    vb_height: float,
    scale: float = 1.0,
    edge_width: int | float | str | None = None,
) -> str:
    """Assemble the SVG string."""
    font_size = max(9, round(11 * scale))

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{display_width}" height="{display_height}" '
        f'viewBox="0 0 {vb_width} {vb_height}" '
        f'font-family="system-ui, sans-serif">'
    )

    # Background.
    parts.append(f'<rect width="{vb_width}" height="{vb_height}" fill="#fafafa" rx="8"/>')

    # Resolve per-edge widths; None means "fall back to the legacy linear path".
    widths = resolve_edge_widths(graph._relationships, edge_width)
    # viewBox is 2x display size — compensate so scalar input is CSS pixels.
    vb_multiplier = vb_width / float(display_width)

    # Edges (drawn first, behind nodes).
    max_weight = max(
        (r.properties.get("weight", 1) for r in graph._relationships),
        default=1,
    )
    for i, rel in enumerate(graph._relationships):
        src_pos = positions.get(rel.source)
        tgt_pos = positions.get(rel.target)
        if src_pos is None or tgt_pos is None:
            continue
        if widths is not None:
            stroke_width = widths[i] * vb_multiplier
        else:
            weight = rel.properties.get("weight", 1)
            stroke_width = 1.0 + 3.0 * (weight / max(max_weight, 1))
        parts.append(
            f'<line x1="{src_pos[0]:.1f}" y1="{src_pos[1]:.1f}" '
            f'x2="{tgt_pos[0]:.1f}" y2="{tgt_pos[1]:.1f}" '
            f'stroke="#aaa" stroke-width="{stroke_width:.1f}" '
            f'stroke-linecap="round"/>'
        )

    # Nodes and labels.
    for eid, entity in graph._entities.items():
        pos = positions.get(eid)
        if pos is None:
            continue
        r = radii.get(eid, 16.0)
        colour = colour_map.get(eid, "#bab0ac")

        # Label: prefer explicit label property, fall back to name or id.
        raw_label = entity.properties.get("label") or entity.properties.get("name") or eid
        truncated = raw_label[:20] + "\u2026" if len(raw_label) > 20 else raw_label

        # Count suffix: only for merged/aggregated graphs.
        count = entity.properties.get("count")
        label = f"{_esc(truncated)} ({count})" if count is not None else _esc(truncated)

        parts.append(
            f'<circle cx="{pos[0]:.1f}" cy="{pos[1]:.1f}" r="{r:.1f}" '
            f'fill="{colour}" opacity="0.85" stroke="white" stroke-width="2"/>'
        )
        parts.append(
            f'<text x="{pos[0]:.1f}" y="{pos[1] + r + 14:.1f}" '
            f'text-anchor="middle" font-size="{font_size}" '
            f'fill="#333">{label}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts)
