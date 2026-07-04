"""Behavioural parity tests for _neighbours after the MultiDiGraph removal."""

from __future__ import annotations

import pickle

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_topology_graph() -> Graph:
    """Self-loop on #loop, isolated #island, parallel edges #a->#b, and #b->#c."""
    g = Graph()
    for eid, etype in [
        ("#a", "Person"),
        ("#b", "Person"),
        ("#c", "File"),
        ("#loop", "Person"),
        ("#island", "File"),
    ]:
        g._add_node(Entity(id=eid, types=[etype]))
    g._add_edge(Relationship(source="#a", target="#b", type="knows"))
    g._add_edge(Relationship(source="#a", target="#b", type="employs"))  # parallel
    g._add_edge(Relationship(source="#b", target="#c", type="hasPart"))
    g._add_edge(Relationship(source="#loop", target="#loop", type="knows"))
    return g


class TestNeighbours:
    def test_both_directions(self):
        g = _build_topology_graph()
        assert g._neighbours("#b") == {"#a", "#c"}

    def test_parallel_edges_deduped(self):
        g = _build_topology_graph()
        assert g._neighbours("#a") == {"#b"}

    def test_self_loop_includes_self(self):
        g = _build_topology_graph()
        assert g._neighbours("#loop") == {"#loop"}

    def test_isolated_node_empty(self):
        g = _build_topology_graph()
        assert g._neighbours("#island") == set()

    def test_unknown_id_empty(self):
        g = _build_topology_graph()
        assert g._neighbours("#nonexistent") == set()

    def test_new_edge_visible_after_prior_neighbours_call(self):
        """_rel_adjacency invalidation: an edge added after a _neighbours call
        (the reader mutation path) must appear in subsequent results."""
        g = _build_topology_graph()
        assert g._neighbours("#island") == set()  # builds the adjacency cache
        g._add_edge(Relationship(source="#island", target="#a", type="mentions"))
        assert g._neighbours("#island") == {"#a"}
        assert "#island" in g._neighbours("#a")

    def test_public_path_degree_unchanged(self):
        """most_connected consumes _neighbours; #b has degree 2 (deduped), #a 1.

        most_connected returns list[tuple[Entity, int]] (graph.py:424-428).
        """
        g = _build_topology_graph()
        top = g.most_connected(n=1)
        entity, degree = top[0]
        assert entity.id == "#b"
        assert degree == 2


class TestNoInternalNxGraph:
    def test_graph_attribute_gone(self):
        g = _build_topology_graph()
        assert not hasattr(g, "_graph")

    def test_pickle_round_trip(self):
        """Private state shape is out of the compatibility contract, but
        pickling itself must keep working."""
        g = _build_topology_graph()
        restored = pickle.loads(pickle.dumps(g))
        assert len(restored.entities) == 5
        assert len(restored.relationships) == 4
        assert restored._neighbours("#b") == {"#a", "#c"}
