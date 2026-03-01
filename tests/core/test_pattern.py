"""Tests for Graph.pattern() — relationship pattern matching."""

from __future__ import annotations

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    """Build a test graph with varied types and relationship types."""
    g = Graph(source="test.zip")
    g._add_node(Entity(id="#alice", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#bob", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#acme", types=["Organisation"], properties={"name": "ACME"}))
    g._add_node(
        Entity(id="#globex", types=["Organisation"], properties={"name": "Globex"})
    )
    g._add_node(Entity(id="#meeting", types=["Event"], properties={"name": "Meeting"}))
    g._add_edge(Relationship(source="#alice", target="#acme", type="memberOf"))
    g._add_edge(Relationship(source="#bob", target="#globex", type="memberOf"))
    g._add_edge(Relationship(source="#acme", target="#globex", type="Superior"))
    g._add_edge(Relationship(source="#alice", target="#meeting", type="attended"))
    return g


class TestPatternVia:
    def test_via_only(self):
        g = _build_graph()
        result = g.pattern(via="memberOf")
        assert len(result) == 4  # alice, bob, acme, globex
        assert "#meeting" not in result._entities
        # _subgraph() includes all mutual edges between matched nodes (by design),
        # so the Superior edge between acme and globex is included too.
        assert len(result.relationships) == 3

    def test_via_filters_relationship_type(self):
        g = _build_graph()
        result = g.pattern(via="Superior")
        assert "#acme" in result._entities
        assert "#globex" in result._entities
        assert "#alice" not in result._entities


class TestPatternFromType:
    def test_from_type_only(self):
        g = _build_graph()
        result = g.pattern(from_type="Person")
        # Alice→ACME, Bob→Globex, Alice→Meeting: sources are People
        ids = set(result._entities.keys())
        assert "#alice" in ids
        assert "#bob" in ids
        assert "#acme" in ids  # target of alice memberOf
        assert "#meeting" in ids  # target of alice attended

    def test_from_type_excludes_non_matching_sources(self):
        g = _build_graph()
        result = g.pattern(from_type="Organisation")
        # Only ACME→Globex Superior has Organisation as source
        assert "#acme" in result._entities
        assert "#globex" in result._entities
        assert "#alice" not in result._entities


class TestPatternToType:
    def test_to_type_only(self):
        g = _build_graph()
        result = g.pattern(to_type="Organisation")
        # Alice→ACME, Bob→Globex, ACME→Globex: all target Organisation
        assert "#acme" in result._entities
        assert "#globex" in result._entities
        assert "#alice" in result._entities
        assert "#bob" in result._entities

    def test_to_type_excludes_non_matching_targets(self):
        g = _build_graph()
        result = g.pattern(to_type="Event")
        # Only Alice→Meeting
        assert "#alice" in result._entities
        assert "#meeting" in result._entities
        assert "#bob" not in result._entities


class TestPatternCombined:
    def test_from_and_via(self):
        g = _build_graph()
        result = g.pattern(from_type="Person", via="memberOf")
        # Alice→ACME and Bob→Globex matched, plus Superior edge between acme/globex
        # (subgraph includes all mutual edges between matched nodes).
        assert len(result.relationships) == 3
        assert "#alice" in result._entities
        assert "#bob" in result._entities

    def test_from_via_and_to(self):
        g = _build_graph()
        result = g.pattern(
            from_type="Organisation", via="Superior", to_type="Organisation"
        )
        assert len(result.relationships) == 1
        assert "#acme" in result._entities
        assert "#globex" in result._entities
        assert "#alice" not in result._entities

    def test_no_matches(self):
        g = _build_graph()
        result = g.pattern(from_type="Event", via="Superior")
        assert len(result) == 0
        assert len(result.relationships) == 0


class TestPatternNoArgs:
    def test_no_args_returns_full_graph(self):
        g = _build_graph()
        result = g.pattern()
        assert len(result) == len(g)
        assert len(result.relationships) == len(g.relationships)


class TestPatternMultiTypeEntities:
    def test_matches_multi_type_entity(self):
        g = Graph()
        g._add_node(Entity(id="#doc", types=["PublishedResource", "Report"]))
        g._add_node(Entity(id="#org", types=["Organisation"]))
        g._add_edge(Relationship(source="#org", target="#doc", type="published"))
        result = g.pattern(to_type="PublishedResource")
        assert "#doc" in result._entities
        assert "#org" in result._entities


class TestPatternValidation:
    def test_invalid_from_type_raises(self):
        g = _build_graph()
        with pytest.raises(ValueError, match="Person"):
            g.pattern(from_type="Persom")

    def test_invalid_via_raises(self):
        g = _build_graph()
        with pytest.raises(ValueError):
            g.pattern(via="nonexistent")

    def test_invalid_to_type_raises(self):
        g = _build_graph()
        with pytest.raises(ValueError, match="Organisation"):
            g.pattern(to_type="Organsiation")


class TestPatternComposition:
    def test_pattern_then_where(self):
        g = _build_graph()
        result = g.pattern(from_type="Person", via="memberOf").where(name="Alice")
        assert len(result) == 1
        assert result.entities[0].id == "#alice"

    def test_pattern_preserves_root_for_expand(self):
        g = _build_graph()
        result = g.pattern(from_type="Organisation", via="Superior")
        expanded = result.expand()
        # Expanding from acme and globex should pull in their neighbours
        assert len(expanded) > len(result)
