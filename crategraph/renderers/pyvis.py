"""Default renderer — pyvis interactive network visualisation."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from markupsafe import escape
from pyvis.network import Network

from crategraph.core.interfaces import Renderer
from crategraph.renderers._colours import resolve_colour_map

if TYPE_CHECKING:
    from crategraph.core.graph import Graph


def _node_size(degree: int, max_degree: int) -> int:
    """Scale node size by degree. Range: 6-45px."""
    if max_degree <= 0:
        return 12
    normalised = degree / max_degree
    return 6 + int(39 * math.sqrt(normalised))


def _try_layout(graph: Graph) -> dict[str, tuple[float, float]] | None:
    """Attempt server-side layout; return ``None`` to fall back to client-side physics."""
    if not graph._entities:
        return None
    try:
        raw = graph.layout()
    except ImportError:
        return None

    # Scale raw positions to a pixel range suitable for vis.js.
    xs = [p[0] for p in raw.values()]
    ys = [p[1] for p in raw.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    range_x = max_x - min_x or 1.0
    range_y = max_y - min_y or 1.0
    spread = 3000.0
    return {
        nid: (
            (p[0] - min_x) / range_x * spread - spread / 2,
            (p[1] - min_y) / range_y * spread - spread / 2,
        )
        for nid, p in raw.items()
    }


class PyvisRenderer(Renderer):
    """Render a ``Graph`` as an interactive pyvis network."""

    def render(
        self,
        graph: Graph,
        *,
        colour_by: str = "type",
        size_by: str = "connections",
        height: str = "100vh",
        width: str = "100%",
        filepath: str | None = None,
        notebook: bool = True,
        **kwargs: Any,
    ) -> Network | str:
        """Build a pyvis Network from *graph*.

        Args:
            colour_by: Property to colour nodes by (default ``"type"``).
                Any entity property or attribute works. ``"community"``
                auto-computes Louvain communities if not already present.
            size_by: ``"connections"`` (default) scales node size by degree.
            height: CSS height of the canvas.
            width: CSS width of the canvas.
            filepath: If given, save the HTML to this path and return it.
            notebook: If True (default), configure for inline Jupyter display.

        Returns the ``pyvis.network.Network`` object (or the filepath string
        if *filepath* was provided).
        """
        net = Network(
            height=height,
            width=width,
            notebook=notebook,
            directed=True,
            cdn_resources="in_line",
        )

        # Colour mapping.
        colour_map = resolve_colour_map(graph, colour_by)

        # Try server-side layout; fall back to client-side physics.
        positions = _try_layout(graph)

        # Pre-compute size values.
        size_values: dict[str, float] = {}
        if size_by == "connections":
            for eid in graph._entities:
                size_values[eid] = float(len(graph._neighbours(eid)))
        else:
            for eid, entity in graph._entities.items():
                val = entity.properties.get(size_by)
                try:
                    size_values[eid] = float(val) if val is not None else 0.0
                except (ValueError, TypeError):
                    size_values[eid] = 0.0
        max_size_val = max(size_values.values()) if size_values else 0

        # Add nodes.
        for eid, entity in graph._entities.items():
            label = entity.properties.get("name", eid)
            if len(str(label)) > 40:
                label = str(label)[:37] + "..."

            colour = colour_map.get(eid, "#bab0ac")
            size = _node_size(int(size_values.get(eid, 0)), int(max_size_val))

            # Tooltip with type and properties.
            title_parts = [f"<b>{escape(entity.type)}</b>: {escape(eid)}"]
            for key, value in list(entity.properties.items())[:8]:
                val_str = str(value)
                if len(val_str) > 60:
                    val_str = val_str[:57] + "..."
                title_parts.append(f"{escape(str(key))}: {escape(val_str)}")
            title = "<br>".join(title_parts)

            # Hide labels on large graphs — show name on hover instead.
            is_large = len(graph._entities) > 30
            node_label = "" if is_large else str(label)

            node_opts: dict[str, Any] = {
                "label": node_label,
                "color": colour,
                "size": size,
                "title": title,
            }
            if positions and eid in positions:
                node_opts["x"] = positions[eid][0]
                node_opts["y"] = positions[eid][1]
                node_opts["physics"] = False

            net.add_node(eid, **node_opts)

        # Add edges.
        for rel in graph._relationships:
            if rel.source in graph._entities and rel.target in graph._entities:
                weight = rel.properties.get("weight", 1)
                if isinstance(weight, (int, float)) and weight > 1:
                    edge_width = 1 + 2 * math.log1p(weight)
                else:
                    edge_width = 1
                edge_opts: dict[str, Any] = {
                    "title": rel.type,
                    "width": edge_width,
                    "color": "rgba(150,150,150,0.3)",
                }
                if rel.properties.get("bidirectional"):
                    edge_opts["arrows"] = ""
                net.add_edge(rel.source, rel.target, **edge_opts)

        # Physics: disabled when layout is pre-computed, otherwise use
        # Barnes-Hut with stabilisation.
        if positions:
            physics_json = '{"enabled": false}'
        else:
            physics_json = """{
                "enabled": true,
                "barnesHut": {
                    "gravitationalConstant": -8000,
                    "springLength": 250,
                    "springConstant": 0.02,
                    "damping": 0.12
                },
                "stabilization": {
                    "iterations": 300
                }
            }"""
        net.set_options(f"""{{
            "physics": {physics_json},
            "edges": {{
                "arrows": {{"to": {{"enabled": true, "scaleFactor": 0.3}}}},
                "smooth": {{"type": "continuous"}}
            }},
            "interaction": {{
                "hover": true,
                "tooltipDelay": 100
            }}
        }}""")

        if filepath:
            net.save_graph(filepath)
            return filepath

        return net
