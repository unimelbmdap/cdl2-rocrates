"""Tests for Graph.exclude() — inverse structural filtering."""

from __future__ import annotations

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    """Build a graph with removable relationship and entity types."""
    g = Graph(source="test.zip")
    g._add_node(Entity(id="#alice", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#bob", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#gavan", types=["Person"], properties={"name": "Gavan"}))
    g._add_node(Entity(id="#acme", types=["Organisation"], properties={"name": "ACME"}))
    g._add_node(Entity(id="#meeting", types=["Event"], properties={"name": "Meeting"}))
    g._add_node(Entity(id="#orphan", types=["Note"], properties={"name": "Orphan"}))
    g._add_edge(Relationship(source="#alice", target="#acme", type="memberOf"))
    g._add_edge(Relationship(source="#bob", target="#acme", type="memberOf"))
    g._add_edge(Relationship(source="#alice", target="#meeting", type="attended"))
    g._add_edge(Relationship(source="#gavan", target="#meeting", type="preparedBy"))
    return g


class TestExcludeByRelationshipType:
    def test_excludes_relationship_type(self):
        g = _build_graph()
        result = g.exclude(relationship_types=["preparedBy"])
        assert all(r.type != "preparedBy" for r in result.relationships)
        assert "#gavan" not in result._entities
        assert "#meeting" in result._entities

    def test_string_shorthand(self):
        g = _build_graph()
        result = g.exclude(relationship_types="preparedBy")
        assert all(r.type != "preparedBy" for r in result.relationships)

    def test_invalid_relationship_type_raises(self):
        g = _build_graph()
        with pytest.raises(ValueError):
            g.exclude(relationship_types=["nonexistent"])

    def test_drop_isolated_false_keeps_new_isolates(self):
        g = _build_graph()
        result = g.exclude(relationship_types=["preparedBy"], drop_isolated=False)
        assert "#gavan" in result._entities
        assert len(result._neighbours("#gavan")) == 0

    def test_preserves_pre_existing_isolates(self):
        g = _build_graph()
        result = g.exclude(relationship_types=["preparedBy"])
        assert "#orphan" in result._entities
        assert len(result._neighbours("#orphan")) == 0

    def test_internal_graph_drops_excluded_edges(self):
        g = _build_graph()
        result = g.exclude(relationship_types=["preparedBy"], drop_isolated=False)
        assert len(result.relationships) == 3
        assert result._graph.number_of_edges() == 3
        assert "#meeting" not in result._neighbours("#gavan")


class TestExcludeByEntityType:
    def test_excludes_entity_type_and_incident_relationships(self):
        g = _build_graph()
        result = g.exclude(entity_types=["Organisation"])
        assert "#acme" not in result._entities
        assert all("Organisation" not in e.types for e in result.entities)
        assert all("#acme" not in (r.source, r.target) for r in result.relationships)

    def test_entity_type_string_shorthand(self):
        g = _build_graph()
        result = g.exclude(entity_types="Organisation")
        assert "#acme" not in result._entities

    def test_invalid_entity_type_raises(self):
        g = _build_graph()
        with pytest.raises(ValueError, match="Organisation"):
            g.exclude(entity_types=["Organsiation"])

    def test_entity_exclusion_drops_nodes_made_isolated(self):
        g = _build_graph()
        result = g.exclude(entity_types=["Organisation"])
        assert "#bob" not in result._entities
        assert "#alice" in result._entities
        assert "#meeting" in result._entities


class TestExcludeComposition:
    def test_exclude_preserves_original_root_for_expand(self):
        g = _build_graph()
        result = g.exclude(relationship_types=["preparedBy"])
        expanded = result.select(id="#meeting").expand()
        assert "#gavan" in expanded._entities
        assert any(r.type == "preparedBy" for r in expanded.relationships)

    def test_no_args_returns_equivalent_graph(self):
        g = _build_graph()
        result = g.exclude()
        assert len(result) == len(g)
        assert len(result.relationships) == len(g.relationships)
        assert result is not g
