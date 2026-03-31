"""3D force-directed graph renderer using 3d-force-graph (Three.js)."""

from __future__ import annotations

import math
from importlib.resources import files
from typing import TYPE_CHECKING, Any

from markupsafe import Markup

from crategraph.core.interfaces import Renderer
from crategraph.renderers._colours import resolve_colour_map
from crategraph.renderers._validation import validate_css_dimension

if TYPE_CHECKING:
    from crategraph.core.graph import Graph


def _load_template() -> Markup:
    """Load the 3D force-graph HTML template from the templates directory."""
    html = (
        files("crategraph.renderers.templates")
        .joinpath("forcegraph3d.html")
        .read_text(encoding="utf-8")
    )
    return Markup(html)


def _node_size(degree: int) -> float:
    """Square-root node sizing. Range: 2-100."""
    return max(2.0, min(100.0, 2.0 + math.sqrt(degree) * 4))


class ForceGraph3DRenderer(Renderer):
    """Render a ``Graph`` as an interactive 3D force-directed visualisation."""

    def _graph_to_json(
        self,
        graph: Graph,
        *,
        colour_by: str = "type",
        size_by: str = "connections",
    ) -> dict[str, Any]:
        """Convert *graph* to the JSON structure expected by 3d-force-graph."""
        if not graph._entities:
            return {"nodes": [], "links": []}

        # Pre-compute size values.
        size_values: dict[str, float] = {}
        if size_by == "connections":
            for eid in graph._entities:
                size_values[eid] = float(len(graph._neighbours(eid)))
        else:
            for eid, entity in graph._entities.items():
                raw = entity.properties.get(size_by)
                try:
                    size_values[eid] = float(raw) if raw is not None else 0.0
                except (ValueError, TypeError):
                    size_values[eid] = 0.0

        # Colour mapping.
        colour_map = resolve_colour_map(graph, colour_by)

        # Build nodes.
        nodes = []
        for eid, entity in graph._entities.items():
            degree = len(graph._neighbours(eid))
            val = _node_size(int(size_values.get(eid, 0)))
            properties = {k: str(v) for k, v in entity.properties.items()}

            nodes.append(
                {
                    "id": eid,
                    "name": entity.name,
                    "val": val,
                    "color": colour_map.get(eid, "#45B7D1"),
                    "degree": degree,
                    "properties": properties,
                }
            )

        # Build links.
        links = []
        for rel in graph._relationships:
            if rel.source in graph._entities and rel.target in graph._entities:
                properties = {k: str(v) for k, v in rel.properties.items()}
                weight = rel.properties.get("weight", 1)
                if isinstance(weight, (int, float)) and weight > 1:
                    width = 0.4 + 2 * math.log1p(weight)
                else:
                    width = 0.4
                links.append(
                    {
                        "source": rel.source,
                        "target": rel.target,
                        "type": rel.type,
                        "properties": properties,
                        "bidirectional": bool(rel.properties.get("bidirectional")),
                        "width": round(width, 2),
                    }
                )

        return {"nodes": nodes, "links": links}

    def render(
        self,
        graph: Graph,
        *,
        colour_by: str = "type",
        size_by: str = "connections",
        height: str = "100vh",
        width: str = "100%",
        filepath: str | None = None,
        **kwargs: Any,
    ) -> Any:
        """Build a 3D force-graph HTML visualisation from *graph*.

        Args:
            colour_by: Property to colour nodes by (default ``"type"``).
                Any entity property or attribute works. ``"community"``
                auto-computes Louvain communities if not already present.
            size_by: ``"connections"`` (default) scales node size by degree.
            height: CSS height of the canvas.
            width: CSS width of the canvas.
            filepath: If given, save the HTML to this path and return it.

        Returns an ``IPython.display.HTML`` object for notebook display,
        or the filepath string if *filepath* was provided.
        """
        import json

        validate_css_dimension(height, "height")
        validate_css_dimension(width, "width")

        graph_json = self._graph_to_json(
            graph,
            colour_by=colour_by,
            size_by=size_by,
        )
        # Escape '</script>' sequences before embedding JSON in a script block.
        json_str = Markup(json.dumps(graph_json).replace("</", "<\\/"))

        template = _load_template()
        html = template % {
            "graph_data": json_str,
            "height": height,
            "width": width,
        }

        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            return filepath

        from IPython.display import HTML

        return HTML(html)
