"""Tests for Graph.merge_nodes() — node aggregation."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"location": "Melbourne"}))
    g._add_node(Entity(id="#b", types=["Person"], properties={"location": "Melbourne"}))
    g._add_node(Entity(id="#c", types=["Organisation"], properties={"location": "Sydney"}))
    g._add_node(Entity(id="#d", types=["Event"], properties={"location": "Melbourne"}))
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#a", target="#d", type="attended"))
    return g


class TestMergeByType:
    def test_produces_one_node_per_type(self):
        g = _build_graph()
        merged = g.merge_nodes(by="type")
        assert len(merged) == 3  # Person, Organisation, Event

    def test_group_has_count(self):
        g = _build_graph()
        merged = g.merge_nodes(by="type")
        person = merged.get("Person")
        assert person.properties["count"] == 2

    def test_edges_between_groups(self):
        g = _build_graph()
        merged = g.merge_nodes(by="type")
        # Person → Organisation (2 memberOf edges) → weight=2.
        rels = [
            r for r in merged.relationships if r.source == "Person" and r.target == "Organisation"
        ]
        assert len(rels) == 1
        assert rels[0].properties["weight"] == 2

    def test_no_self_loops(self):
        g = _build_graph()
        merged = g.merge_nodes(by="type")
        # attended: Person → Event (same Person group has no self-edge).
        for rel in merged.relationships:
            assert rel.source != rel.target


class TestMergeByProperty:
    def test_merge_by_location(self):
        g = _build_graph()
        merged = g.merge_nodes(by="location")
        assert len(merged) == 2  # Melbourne, Sydney

    def test_melbourne_group_count(self):
        g = _build_graph()
        merged = g.merge_nodes(by="location")
        melb = merged.get("Melbourne")
        assert melb.properties["count"] == 3  # alice, bob, event

    def test_missing_property_grouped(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
        g._add_node(Entity(id="#b", types=["Person"]))  # No name.
        merged = g.merge_nodes(by="name")
        assert "(no value)" in merged._entities


class TestMergePreservesMetadata:
    def test_source_preserved(self):
        g = Graph(source="test.zip")
        g._add_node(Entity(id="#a", types=["Person"]))
        merged = g.merge_nodes(by="type")
        assert merged.source == "test.zip"

    def test_merged_by_in_properties(self):
        g = _build_graph()
        merged = g.merge_nodes(by="type")
        for entity in merged.entities:
            assert entity.properties["merged_by"] == "type"


class TestMergeEmpty:
    def test_empty_graph(self):
        g = Graph()
        merged = g.merge_nodes(by="type")
        assert len(merged) == 0
        assert len(merged.relationships) == 0
