"""rustworkx graph backend — optional high-performance engine.

Requires ``rustworkx >= 0.15``.  Install via::

    pip install crategraph[rustworkx]
"""

from __future__ import annotations

import rustworkx as rx

from crategraph.core.interfaces import GraphBackend
from crategraph.core.models import Entity, Relationship


class RustworkxBackend(GraphBackend):
    """Graph backend backed by a rustworkx PyDiGraph.

    rustworkx uses integer node indices internally.  This class maintains
    a ``_id_to_index`` mapping so the public interface stays string-based.
    """

    def __init__(self) -> None:
        self._graph: rx.PyDiGraph = rx.PyDiGraph()  # type: ignore[type-arg]
        self._id_to_index: dict[str, int] = {}

    def add_node(self, node_id: str, entity: Entity) -> None:
        if node_id in self._id_to_index:
            # Update payload on existing node.
            idx = self._id_to_index[node_id]
            self._graph[idx] = {"id": node_id, "entity": entity}
        else:
            idx = self._graph.add_node({"id": node_id, "entity": entity})
            self._id_to_index[node_id] = idx

    def add_edge(self, source: str, target: str, key: str, relationship: Relationship) -> None:
        src_idx = self._id_to_index[source]
        tgt_idx = self._id_to_index[target]
        self._graph.add_edge(src_idx, tgt_idx, {"key": key, "relationship": relationship})

    def has_node(self, node_id: str) -> bool:
        return node_id in self._id_to_index

    def successors(self, node_id: str) -> set[str]:
        idx = self._id_to_index[node_id]
        return {self._graph[s]["id"] for s in self._graph.successor_indices(idx)}

    def predecessors(self, node_id: str) -> set[str]:
        idx = self._id_to_index[node_id]
        return {self._graph[p]["id"] for p in self._graph.predecessor_indices(idx)}

    def subgraph(self, node_ids, entities, relationships):
        new = RustworkxBackend()
        for nid in node_ids:
            if nid in entities:
                new.add_node(nid, entities[nid])
        for rel in relationships:
            if rel.source in node_ids and rel.target in node_ids:
                new.add_edge(rel.source, rel.target, rel.type, rel)
        return new
