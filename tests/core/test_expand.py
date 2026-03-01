"""Tests for Graph.expand() — grow selection outward."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    """Build: alice → acme ← bob → event ← carol."""
    g = Graph()
    g._add_node(Entity(id="#alice", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#bob", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#carol", types=["Person"], properties={"name": "Carol"}))
    g._add_node(Entity(id="#acme", types=["Organisation"], properties={"name": "ACME"}))
    g._add_node(Entity(id="#event", types=["Event"], properties={"name": "Meeting"}))
    g._add_edge(Relationship(source="#alice", target="#acme", type="memberOf"))
    g._add_edge(Relationship(source="#bob", target="#acme", type="memberOf"))
    g._add_edge(Relationship(source="#bob", target="#event", type="attended"))
    g._add_edge(Relationship(source="#carol", target="#event", type="attended"))
    return g


class TestExpandBasic:
    def test_expand_grows_selection(self):
        g = _build_graph()
        # Start with just alice.
        alice_only = g.select(id="#alice")
        assert len(alice_only) == 1

        expanded = alice_only.expand()
        # Should now include alice + acme (neighbour via memberOf).
        assert "#alice" in expanded._entities
        assert "#acme" in expanded._entities

    def test_expand_depth_2(self):
        g = _build_graph()
        alice_only = g.select(id="#alice")
        expanded = alice_only.expand(depth=2)
        # depth=1: alice + acme; depth=2: + bob (also memberOf acme).
        assert "#bob" in expanded._entities

    def test_expand_no_edges(self):
        g = Graph()
        g._add_node(Entity(id="#lonely", types=["Person"]))
        result = g.select(id="#lonely").expand()
        assert len(result) == 1


class TestExpandByType:
    def test_expand_entity_types(self):
        g = _build_graph()
        alice_only = g.select(id="#alice")
        # Only expand to Person neighbours (not Organisation).
        expanded = alice_only.expand(entity_types=["Person"])
        assert "#alice" in expanded._entities
        # acme is Organisation, so it shouldn't be included.
        assert "#acme" not in expanded._entities

    def test_expand_entity_types_single_item_list(self):
        g = _build_graph()
        alice_only = g.select(id="#alice")
        expanded = alice_only.expand(entity_types=["Organisation"])
        assert "#acme" in expanded._entities


class TestExpandVia:
    def test_expand_via_relationship_type(self):
        g = _build_graph()
        bob_only = g.select(id="#bob")
        # Only follow memberOf edges.
        expanded = bob_only.expand(via="memberOf")
        assert "#acme" in expanded._entities
        assert "#event" not in expanded._entities

    def test_expand_via_other_type(self):
        g = _build_graph()
        bob_only = g.select(id="#bob")
        expanded = bob_only.expand(via="attended")
        assert "#event" in expanded._entities
        assert "#acme" not in expanded._entities


class TestExpandPreservesEdges:
    def test_expanded_graph_has_edges(self):
        g = _build_graph()
        alice_only = g.select(id="#alice")
        expanded = alice_only.expand()
        # alice → acme edge should be present.
        rels = [r for r in expanded.relationships if r.source == "#alice"]
        assert len(rels) >= 1


class TestExpandChaining:
    def test_select_then_expand(self):
        g = _build_graph()
        result = g.select(entity_types=["Person"]).expand(entity_types=["Organisation"])
        # All people + organisations connected to them.
        assert "#acme" in result._entities
        assert "#alice" in result._entities
