"""Tests for Graph.drop() — remove entities by property value."""

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
    g._add_node(
        Entity(
            id="#acme",
            types=["Organisation"],
            properties={"name": "ACME", "location": "Melbourne"},
        )
    )
    g._add_node(
        Entity(
            id="#event",
            types=["Event"],
            properties={"name": "Conference", "tags": ["Melbourne", "annual"]},
        )
    )
    g._add_node(Entity(id="#orphan", types=["Note"], properties={"name": "Orphan"}))
    g._add_edge(Relationship(source="#alice", target="#acme", type="memberOf"))
    g._add_edge(Relationship(source="#bob", target="#acme", type="memberOf"))
    return g


class TestDropByValue:
    def test_single_string_normalised_to_list(self):
        g = _build_graph()
        result = g.drop("Melbourne")
        assert "#alice" not in result._entities

    def test_list_of_values_drops_all_matches(self):
        g = _build_graph()
        result = g.drop(["Melbourne", "Sydney"])
        assert "#alice" not in result._entities
        assert "#acme" not in result._entities
        assert "#bob" not in result._entities

    def test_unhashable_property_values_skipped(self):
        g = _build_graph()
        result = g.drop("Melbourne")
        assert "#event" in result._entities

    def test_no_match_returns_full_graph(self):
        g = _build_graph()
        result = g.drop("Canberra")
        assert len(result) == len(g)

    def test_preserves_pre_existing_isolates(self):
        g = _build_graph()
        result = g.drop("Melbourne")
        assert "#orphan" in result._entities


class TestDropByProperty:
    def test_drops_only_matching_property_key(self):
        g = _build_graph()
        result = g.drop("Melbourne", property="location")
        assert "#alice" not in result._entities
        assert "#acme" not in result._entities
        assert "#bob" in result._entities

    def test_property_key_not_present_keeps_entity(self):
        g = _build_graph()
        result = g.drop("Orphan", property="location")
        assert "#orphan" in result._entities

    def test_list_of_values_with_property(self):
        g = _build_graph()
        result = g.drop(["Melbourne", "Sydney"], property="location")
        assert "#alice" not in result._entities
        assert "#bob" not in result._entities
        assert "#acme" not in result._entities
