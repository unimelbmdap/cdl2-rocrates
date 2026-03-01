"""General-purpose SVG renderer for crategraph graphs."""

from __future__ import annotations

import math
from html import escape as _esc
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core.interfaces import Renderer
from crategraph.renderers._colours import resolve_colour_map

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
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
        filepath: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Render *graph* and return an ``IPython.display.SVG`` or filepath.

        Args:
            graph: The graph to render.
            colour_by: Entity attribute or property used to assign colours.
                ``"type"`` (default) colours by primary type.
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

        positions = _compute_layout(
            graph,
            radii=radii,
            pad=pad,
            width=vb_w,
            height=vb_h,
        )
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


def _compute_layout(
    graph: Graph,
    *,
    radii: dict[str, float] | None = None,
    width: float = 1200,
    height: float = 900,
    pad: float = 80,
) -> dict[str, tuple[float, float]]:
    """Compute node positions via a size-aware force-directed layout.

    Uses Fruchterman-Reingold-style repulsion/attraction with a deterministic
    seed.  Node radii are used to boost repulsion so circles don't overlap.
    """
    import random as _random

    nodes = list(graph._entities.keys())
    if not nodes:
        return {}

    radii = radii or {}
    edges = [(r.source, r.target) for r in graph._relationships]

    # Seed for determinism.
    rng = _random.Random(42)
    pos: dict[str, list[float]] = {n: [rng.uniform(-1, 1), rng.uniform(-1, 1)] for n in nodes}

    k = 2.0 / max(1.0, math.sqrt(len(nodes)))  # ideal spring length
    # Normalise radii into layout-space so they influence repulsion.
    canvas_span = min(width, height) - 2 * pad
    r_scale = 2.0 / max(canvas_span, 1.0)
    layout_radii = {n: radii.get(n, 16.0) * r_scale for n in nodes}

    iterations = 80
    temperature = 1.5

    for _step in range(iterations):
        disp: dict[str, list[float]] = {n: [0.0, 0.0] for n in nodes}

        # Repulsion between all pairs (size-aware).
        for i, a in enumerate(nodes):
            ra = layout_radii[a]
            for b in nodes[i + 1 :]:
                rb = layout_radii[b]
                dx = pos[a][0] - pos[b][0]
                dy = pos[a][1] - pos[b][1]
                dist = max(math.sqrt(dx * dx + dy * dy), 0.001)
                # Extra repulsion when nodes overlap: treat combined radii
                # as a minimum separation distance.
                min_sep = (ra + rb) * 1.2
                effective_dist = max(dist - min_sep, 0.001)
                force = k * k / effective_dist
                fx = dx / dist * force
                fy = dy / dist * force
                disp[a][0] += fx
                disp[a][1] += fy
                disp[b][0] -= fx
                disp[b][1] -= fy

        # Attraction along edges.
        for src, tgt in edges:
            dx = pos[src][0] - pos[tgt][0]
            dy = pos[src][1] - pos[tgt][1]
            dist = max(math.sqrt(dx * dx + dy * dy), 0.001)
            force = dist * dist / k
            fx = dx / dist * force
            fy = dy / dist * force
            disp[src][0] -= fx
            disp[src][1] -= fy
            disp[tgt][0] += fx
            disp[tgt][1] += fy

        # Apply displacements with temperature cap.
        for n in nodes:
            dx, dy = disp[n]
            mag = max(math.sqrt(dx * dx + dy * dy), 0.001)
            scale = min(mag, temperature) / mag
            pos[n][0] += dx * scale
            pos[n][1] += dy * scale

        temperature *= 0.95

    # Scale to canvas coordinates with padding.
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    range_x = max_x - min_x or 1.0
    range_y = max_y - min_y or 1.0

    result = {
        nid: (
            pad + (p[0] - min_x) / range_x * (width - 2 * pad),
            pad + (p[1] - min_y) / range_y * (height - 2 * pad),
        )
        for nid, p in pos.items()
    }

    # Post-layout overlap removal: iteratively push apart overlapping circles.
    _resolve_overlaps(result, radii, width=width, height=height, pad=pad)
    return result


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

    # Edges (drawn first, behind nodes).
    max_weight = max(
        (r.properties.get("weight", 1) for r in graph._relationships),
        default=1,
    )
    for rel in graph._relationships:
        src_pos = positions.get(rel.source)
        tgt_pos = positions.get(rel.target)
        if src_pos is None or tgt_pos is None:
            continue
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
