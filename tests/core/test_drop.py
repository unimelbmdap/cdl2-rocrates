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

    def test_list_valued_property_dropped_on_membership(self):
        g = _build_graph()
        result = g.drop("Melbourne")
        assert "#event" not in result._entities

    def test_list_valued_property_without_match_kept(self):
        g = _build_graph()
        result = g.drop("Sydney")
        assert "#event" in result._entities

    def test_unhashable_non_list_values_skipped(self):
        g = _build_graph()
        g._add_node(Entity(id="#geo", types=["Place"], properties={"geo": {"lat": 1.0}}))
        result = g.drop("Melbourne")
        assert "#geo" in result._entities

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

    def test_list_valued_property_dropped_on_membership(self):
        g = _build_graph()
        result = g.drop("Melbourne", property="tags")
        assert "#event" not in result._entities
        assert "#alice" in result._entities

    def test_list_valued_property_without_match_kept(self):
        g = _build_graph()
        result = g.drop("Sydney", property="tags")
        assert "#event" in result._entities

    def test_single_item_list_matches_scalar(self):
        g = _build_graph()
        g._add_node(Entity(id="#wrapped", types=["Note"], properties={"name": ["Orphan"]}))
        result = g.drop("Orphan", property="name")
        assert "#wrapped" not in result._entities
        assert "#orphan" not in result._entities

    def test_tuple_valued_property_dropped_on_membership(self):
        g = _build_graph()
        g._add_node(Entity(id="#tup", types=["Note"], properties={"tags": ("Melbourne", "x")}))
        result = g.drop("Melbourne", property="tags")
        assert "#tup" not in result._entities

    def test_unhashable_element_before_match_is_skipped(self):
        g = _build_graph()
        g._add_node(
            Entity(
                id="#mixed",
                types=["Note"],
                properties={"tags": [{"nested": 1}, "Melbourne"]},
            )
        )
        assert "#mixed" not in g.drop("Melbourne")._entities
        assert "#mixed" not in g.drop("Melbourne", property="tags")._entities
