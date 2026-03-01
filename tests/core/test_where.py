"""Tests for Graph.where() — property filtering."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(
        Entity(
            id="#a", types=["Person"], properties={"name": "Alice", "birth_year": 1837}
        )
    )
    g._add_node(
        Entity(
            id="#b", types=["Person"], properties={"name": "Bob", "birth_year": 1901}
        )
    )
    g._add_node(
        Entity(
            id="#c", types=["Person"], properties={"name": "Carol", "birth_year": 1850}
        )
    )
    g._add_node(Entity(id="#d", types=["Organisation"], properties={"name": "ACME"}))
    g._add_edge(Relationship(source="#a", target="#d", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#d", type="memberOf"))
    return g


class TestWhereExactMatch:
    def test_match_string(self):
        g = _build_graph()
        result = g.where(name="Alice")
        assert len(result) == 1
        assert result.entities[0].id == "#a"

    def test_match_int(self):
        g = _build_graph()
        result = g.where(birth_year=1837)
        assert len(result) == 1
        assert result.entities[0].id == "#a"

    def test_no_match(self):
        g = _build_graph()
        result = g.where(name="Nonexistent")
        assert len(result) == 0

    def test_missing_property(self):
        g = _build_graph()
        # Organisation has no birth_year.
        result = g.where(birth_year=1837)
        assert "#d" not in result._entities


class TestWhereRange:
    def test_range_inclusive(self):
        g = _build_graph()
        result = g.where(birth_year=(1837, 1850))
        assert len(result) == 2
        ids = {e.id for e in result.entities}
        assert ids == {"#a", "#c"}

    def test_range_single_match(self):
        g = _build_graph()
        result = g.where(birth_year=(1900, 1910))
        assert len(result) == 1
        assert result.entities[0].id == "#b"

    def test_range_no_match(self):
        g = _build_graph()
        result = g.where(birth_year=(2000, 2100))
        assert len(result) == 0


class TestWhereMultipleFilters:
    def test_multiple_conditions(self):
        g = _build_graph()
        result = g.where(name="Alice", birth_year=1837)
        assert len(result) == 1
        assert result.entities[0].id == "#a"

    def test_conflicting_conditions(self):
        g = _build_graph()
        result = g.where(name="Alice", birth_year=1901)
        assert len(result) == 0


class TestWherePreservesEdges:
    def test_edges_between_matching_entities(self):
        g = _build_graph()
        result = g.where(name="Alice")
        # Alice alone — no edges (ACME not in result).
        assert len(result.relationships) == 0

    def test_edges_preserved_when_both_endpoints_match(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"team": "blue"}))
        g._add_node(Entity(id="#b", types=["Person"], properties={"team": "blue"}))
        g._add_edge(Relationship(source="#a", target="#b", type="knows"))
        result = g.where(team="blue")
        assert len(result.relationships) == 1


class TestWhereEmpty:
    def test_no_filters_returns_full_graph(self):
        g = _build_graph()
        result = g.where()
        assert len(result) == len(g)
