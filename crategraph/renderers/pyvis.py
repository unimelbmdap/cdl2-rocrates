"""Default renderer — pyvis interactive network visualisation."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

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


class PyvisRenderer(Renderer):
    """Render a ``Graph`` as an interactive pyvis network."""

    def render(
        self,
        graph: Graph,
        *,
        colour_by: str = "type",
        size_by: str = "connections",
        height: str = "600px",
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

        # Pre-compute degrees for sizing.
        degrees: dict[str, int] = {}
        for eid in graph._entities:
            degrees[eid] = len(graph._neighbours(eid))
        max_degree = max(degrees.values()) if degrees else 0

        # Add nodes.
        for eid, entity in graph._entities.items():
            label = entity.properties.get("name", eid)
            if len(str(label)) > 40:
                label = str(label)[:37] + "..."

            colour = colour_map.get(eid, "#bab0ac")
            size = _node_size(degrees.get(eid, 0), max_degree) if size_by == "connections" else 15

            # Tooltip with type and properties.
            title_parts = [f"<b>{entity.type}</b>: {eid}"]
            for key, value in list(entity.properties.items())[:8]:
                val_str = str(value)
                if len(val_str) > 60:
                    val_str = val_str[:57] + "..."
                title_parts.append(f"{key}: {val_str}")
            title = "<br>".join(title_parts)

            # Hide labels on large graphs — show name on hover instead.
            is_large = len(graph._entities) > 30
            node_label = "" if is_large else str(label)

            net.add_node(
                eid,
                label=node_label,
                color=colour,
                size=size,
                title=title,
            )

        # Add edges.
        for rel in graph._relationships:
            if rel.source in graph._entities and rel.target in graph._entities:
                weight = rel.properties.get("weight", 1)
                edge_width = 1 + math.log1p(weight) if isinstance(weight, (int, float)) else 1
                edge_opts: dict[str, Any] = {
                    "title": rel.type,
                    "width": edge_width,
                    "color": "rgba(150,150,150,0.3)",
                }
                if rel.properties.get("bidirectional"):
                    edge_opts["arrows"] = ""
                net.add_edge(rel.source, rel.target, **edge_opts)

        # Sensible physics defaults.
        net.set_options("""{
            "physics": {
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
            },
            "edges": {
                "arrows": {"to": {"enabled": true, "scaleFactor": 0.3}},
                "smooth": {"type": "continuous"}
            },
            "interaction": {
                "hover": true,
                "tooltipDelay": 100
            }
        }""")

        if filepath:
            net.save_graph(filepath)
            return filepath

        return net
