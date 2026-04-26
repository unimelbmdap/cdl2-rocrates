"""GraphML writer — serialises a Graph to a ``.graphml`` file for Gephi etc.

GraphML only accepts scalar node/edge attributes (``str``/``int``/``float``/
``bool``). This writer reuses ``crategraph.writers._flatten`` to promote
``id``/``label``/``type``/``types`` to first-class columns and encode
nested ``properties`` deterministically. See ``docs/writers.md`` (to be
added in a later task) for the full attribute-flattening rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx

from crategraph.core.interfaces import Writer
from crategraph.writers._flatten import flatten_edge, flatten_node

if TYPE_CHECKING:
    from crategraph.core.graph import Graph


class GraphMLWriter(Writer):
    """Write a :class:`Graph` to a GraphML file."""

    def can_write(self, path: str) -> bool:
        return path.lower().endswith(".graphml")

    def write(
        self,
        graph: Graph,
        path: str,
        *,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> None:
        target = Path(path)
        if target.exists() and not overwrite:
            raise FileExistsError(target)
        flat = _to_flat_networkx(graph)
        try:
            nx.write_graphml_lxml(flat, target)
        except ImportError:
            nx.write_graphml(flat, target)


def _to_flat_networkx(graph: Graph) -> nx.MultiDiGraph:
    """Build a fresh MultiDiGraph whose attributes are scalar-only.

    Iterates ``graph.entities`` and ``graph.relationships`` so export follows
    Graph's public relationship model rather than NetworkX-specific edge
    attributes. ``MultiDiGraph`` assigns edge keys so parallel edges between
    the same endpoints survive.
    """
    flat = nx.MultiDiGraph()
    for entity in graph.entities:
        flat.add_node(entity.id, **flatten_node(entity))
    for rel in graph.relationships:
        attrs = flatten_edge(rel)
        flat.add_edge(rel.source, rel.target, **attrs)
    return flat


__all__ = ["GraphMLWriter"]
