"""Tests for Graph.substract() — remove one graph from another."""

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


class TestSubstract:
    def test_removes_entities_in_other(self):
        g = _build_graph()
        melbourne = g.where(location="Melbourne")
        result = g.substract(melbourne)
        assert "#alice" not in result._entities
        assert "#bob" in result._entities

    def test_substracting_empty_graph_returns_full_graph(self):
        g = _build_graph()
        empty = g.where(location="Canberra")
        result = g.substract(empty)
        assert len(result) == len(g)

    def test_substracting_full_graph_returns_empty(self):
        g = _build_graph()
        result = g.substract(g)
        assert len(result) == 0

    def test_preserves_pre_existing_isolates(self):
        g = _build_graph()
        melbourne = g.where(location="Melbourne")
        result = g.substract(melbourne)
        assert "#orphan" in result._entities

    def test_chainable(self):
        g = _build_graph()
        melbourne = g.where(location="Melbourne")
        result = g.substract(melbourne).select(entity_types=["Person"])
        assert "#bob" in result._entities
        assert "#alice" not in result._entities
