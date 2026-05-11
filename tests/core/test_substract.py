"""Tests for Graph.subtract() — remove one graph from another."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    g = Graph(source="test.zip")
    g._add_node(
        Entity(
            id="#alice", types=["Person"], properties={"name": "Alice", "location": "Melbourne"}
        )
    )
    g._add_node(
        Entity(id="#bob", types=["Person"], properties={"name": "Bob", "location": "Sydney"})
    )
    g._add_node(Entity(id="#acme", types=["Organisation"], properties={"name": "ACME"}))
    g._add_node(Entity(id="#orphan", types=["Note"], properties={"name": "Orphan"}))
    g._add_edge(Relationship(source="#alice", target="#acme", type="memberOf"))
    g._add_edge(Relationship(source="#bob", target="#acme", type="memberOf"))
    return g


class TestSubtract:
    def test_removes_entities_in_other(self):
        g = _build_graph()
        melbourne = g.where(location="Melbourne")
        result = g.subtract(melbourne)
        assert "#alice" not in result._entities
        assert "#bob" in result._entities

    def test_subtracting_empty_graph_returns_full_graph(self):
        g = _build_graph()
        empty = g.where(location="Canberra")
        result = g.subtract(empty)
        assert len(result) == len(g)

    def test_subtracting_full_graph_returns_empty(self):
        g = _build_graph()
        result = g.subtract(g)
        assert len(result) == 0

    def test_preserves_pre_existing_isolates(self):
        g = _build_graph()
        melbourne = g.where(location="Melbourne")
        result = g.subtract(melbourne)
        assert "#orphan" in result._entities

    def test_chainable(self):
        g = _build_graph()
        melbourne = g.where(location="Melbourne")
        result = g.subtract(melbourne).select(entity_types=["Person"])
        assert "#bob" in result._entities
        assert "#alice" not in result._entities
