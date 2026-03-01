"""NetworkX graph backend — the default engine."""

from __future__ import annotations

import networkx as nx

from crategraph.core.interfaces import GraphBackend
from crategraph.core.models import Entity, Relationship


class NetworkXBackend(GraphBackend):
    """Graph backend backed by a NetworkX MultiDiGraph."""

    def __init__(self) -> None:
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()

    def add_node(self, node_id: str, entity: Entity) -> None:
        self._graph.add_node(node_id, entity=entity)

    def add_edge(
        self, source: str, target: str, key: str, relationship: Relationship
    ) -> None:
        self._graph.add_edge(source, target, key=key, relationship=relationship)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._graph

    def successors(self, node_id: str) -> set[str]:
        return set(self._graph.successors(node_id))

    def predecessors(self, node_id: str) -> set[str]:
        return set(self._graph.predecessors(node_id))

    def subgraph(self, node_ids, entities, relationships):
        new = NetworkXBackend()
        new._graph = self._graph.subgraph(node_ids).copy()
        return new
