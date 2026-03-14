"""WebGL graph renderer using Sigma.js with ForceAtlas2 layout."""

from __future__ import annotations

import math
import random
from importlib.resources import files
from typing import TYPE_CHECKING, Any

from markupsafe import Markup

from crategraph.core.interfaces import Renderer
from crategraph.renderers._colours import PALETTE, resolve_colour_map

if TYPE_CHECKING:
    from crategraph.core.graph import Graph


def _hex_to_rgba(hex_colour: str, alpha: float) -> str:
    """Convert a hex colour like '#4e79a7' to 'rgba(78,121,167,0.6)'."""
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _dim_hex(hex_colour: str, factor: float = 0.35) -> str:
    """Darken a hex colour by scaling RGB channels towards black.

    Used for edge colours — sigma v2's WebGL renderer only supports
    hex, not rgba, so we simulate transparency by darkening.
    """
    h = hex_colour.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def _node_size(degree: int, max_degree: int) -> float:
    """Sqrt-scaled node sizing. Range: 3-20."""
    if max_degree <= 0:
        return 3.0
    return max(3.0, min(20.0, 3.0 + math.sqrt(degree / max_degree) * 17.0))


class SigmaRenderer(Renderer):
    """Render a ``Graph`` as an interactive WebGL visualisation using Sigma.js.

    Layout is computed client-side using ForceAtlas2. Supports synchronous
    (default) and animated (web worker) modes via the ``animated`` parameter.
    """

    def graph_to_json(
        self,
        graph: Graph,
        *,
        colour_by: str = "type",
        size_by: str = "connections",
    ) -> dict[str, Any]:
        """Convert *graph* to the JSON structure expected by the Sigma.js template."""
        if not graph._entities:
            return {"nodes": [], "edges": []}

        # Pre-compute degrees.
        degrees: dict[str, int] = {}
        for eid in graph._entities:
            degrees[eid] = len(graph._neighbours(eid))
        max_degree = max(degrees.values()) if degrees else 0

        # Colour mapping.
        colour_map = resolve_colour_map(graph, colour_by)

        # Deterministic random positions for initial layout seed.
        rng = random.Random(42)

        # Build nodes.
        nodes = []
        for eid, entity in graph._entities.items():
            degree = degrees.get(eid, 0)
            size = _node_size(degree, max_degree) if size_by == "connections" else 6.0

            hex_colour = colour_map.get(eid, "#45B7D1")

            nodes.append(
                {
                    "id": eid,
                    "label": entity.name or eid[:30],
                    "x": rng.uniform(-100, 100),
                    "y": rng.uniform(-100, 100),
                    "size": size,
                    "color": _hex_to_rgba(hex_colour, 0.6),
                    "entityType": entity.type,
                    "degree": degree,
                }
            )

        # Build a lookup for source node hex colours (for edge colouring).
        node_hex: dict[str, str] = {}
        for eid in graph._entities:
            node_hex[eid] = colour_map.get(eid, "#45B7D1")

        # Build edges.
        edges = []
        for i, rel in enumerate(graph._relationships):
            if rel.source in graph._entities and rel.target in graph._entities:
                source_hex = node_hex.get(rel.source, "#ffffff")
                edges.append(
                    {
                        "id": f"e{i}",
                        "source": rel.source,
                        "target": rel.target,
                        "color": _dim_hex(source_hex, 0.2),
                    }
                )

        return {"nodes": nodes, "edges": edges}

    @staticmethod
    def _load_template(*, variant: str = "full") -> Markup:
        """Load a Sigma.js HTML template.

        *variant* is one of ``"full"``, ``"simple"``, or ``"grid"``.
        """
        names = {"full": "sigma.html", "simple": "sigma_simple.html", "grid": "sigma_grid.html"}
        html = (
            files("crategraph.renderers.templates")
            .joinpath(names[variant])
            .read_text(encoding="utf-8")
        )
        return Markup(html)

    @staticmethod
    def _load_bundle() -> Markup:
        """Load the vendored Sigma.js + graphology + FA2 JS bundle.

        Returns ``Markup`` so MarkupSafe does not HTML-escape the JS
        when it is substituted into the template via ``%`` formatting.
        """
        js = (
            files("crategraph.renderers.templates")
            .joinpath("vendor/sigma-fa2.min.js")
            .read_text(encoding="utf-8")
        )
        return Markup(js)

    def render(
        self,
        graph: Graph,
        *,
        colour_by: str = "type",
        size_by: str = "connections",
        height: str = "100vh",
        width: str = "100%",
        filepath: str | None = None,
        animated: bool = False,
        simple: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Build a Sigma.js HTML visualisation from *graph*.

        Args:
            colour_by: Property to colour nodes by (default ``"type"``).
                ``"community"`` auto-computes Louvain communities.
            size_by: ``"connections"`` (default) scales node size by degree.
            height: CSS height of the canvas.
            width: CSS width of the canvas.
            filepath: If given, save the HTML to this path and return it.
            animated: If ``True``, run ForceAtlas2 in animated (web-worker)
                mode; otherwise run a synchronous layout pass.
            simple: If ``True``, use a minimal template with no UI panels
                — suitable for grid thumbnails and embedding.

        Returns an ``IPython.display.HTML`` object for notebook display,
        or the filepath string if *filepath* was provided.
        """
        import json

        graph_json = self.graph_to_json(
            graph,
            colour_by=colour_by,
            size_by=size_by,
        )

        # Build type → colour mapping for the legend.
        types = sorted({e.type for e in graph._entities.values()})
        type_colours = {t: PALETTE[i % len(PALETTE)] for i, t in enumerate(types)}

        config = {"animated": animated, "simple": simple}

        template = self._load_template(variant="simple" if simple else "full")
        bundle = self._load_bundle()

        # Escape '</script>' sequences in JSON to prevent XSS when
        # embedding inside <script> tags (OWASP recommendation).
        def _safe_json(obj: object) -> Markup:
            return Markup(json.dumps(obj).replace("</", "<\\/"))

        html = template % {
            "graph_data": _safe_json(graph_json),
            "type_colours": _safe_json(type_colours),
            "config": _safe_json(config),
            "bundle": bundle,
            "height": height,
            "width": width,
        }

        if filepath:
            with open(filepath, "w", encoding="utf-8") as fh:
                fh.write(html)
            return filepath

        from IPython.display import HTML

        return HTML(html)
