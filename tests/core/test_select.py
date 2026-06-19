"""Tests for Graph.select() — structural filtering."""

from __future__ import annotations

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    """Build a test graph with varied entity types and connections."""
    g = Graph(source="test.zip")
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}, source="crate1/"))
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob"}, source="crate1/"))
    g._add_node(
        Entity(
            id="#c",
            types=["Organisation"],
            properties={"name": "ACME"},
            source="crate2/",
        )
    )
    g._add_node(Entity(id="#d", types=["Event"], properties={"name": "Meeting"}, source="crate1/"))
    g._add_node(Entity(id="#e", types=["Person"], properties={"name": "Eve"}, source="crate2/"))
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#a", target="#d", type="attended"))
    g._add_edge(Relationship(source="#b", target="#d", type="attended"))
    g._add_edge(Relationship(source="#e", target="#c", type="employedAt"))
    return g


class TestSelectByEntityType:
    def test_single_type(self):
        g = _build_graph()
        result = g.select(entity_types=["Person"])
        assert len(result) == 3
        assert all(e.type == "Person" for e in result.entities)

    def test_multiple_types(self):
        g = _build_graph()
        result = g.select(entity_types=["Person", "Event"])
        assert len(result) == 4

    def test_invalid_type_raises(self):
        g = _build_graph()
        with pytest.raises(ValueError, match="Person"):
            g.select(entity_types=["Persom"])


class TestSelectByRelationshipType:
    def test_filter_by_relationship_type(self):
        g = _build_graph()
        result = g.select(relationship_types=["memberOf"])
        # alice, bob, acme are connected by memberOf.
        assert "#a" in result._entities
        assert "#b" in result._entities
        assert "#c" in result._entities

    def test_string_shorthand(self):
        g = _build_graph()
        result = g.select(relationship_types="memberOf")
        assert len(result) >= 3

    def test_invalid_relationship_type_raises(self):
        g = _build_graph()
        with pytest.raises(ValueError):
            g.select(relationship_types=["nonexistent"])


class TestSelectBySource:
    def test_filter_by_source(self):
        g = _build_graph()
        result = g.select(source="crate1/")
        assert len(result) == 3  # alice, bob, meeting
        for e in result.entities:
            assert "crate1/" in e.source


class TestSelectByConnectivity:
    def test_min_connections(self):
        g = _build_graph()
        result = g.select(min_connections=2)
        # alice (→acme, →meeting), bob (→acme, →meeting), acme (←alice, ←bob, ←eve)
        assert len(result) >= 2

    def test_max_connections(self):
        g = _build_graph()
        result = g.select(max_connections=1)
        # Only entities with 1 or fewer connections.
        assert all(len(g._neighbours(e.id)) <= 1 for e in result.entities)

    def test_connectivity_ignores_missing_endpoints(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
        with pytest.warns(UserWarning, match="missing endpoint"):
            g._add_edge(Relationship(source="#a", target="#missing", type="knows"))
        result = g.select(min_connections=1)
        assert len(result) == 0


class TestSelectById:
    def test_select_existing_id(self):
        g = _build_graph()
        result = g.select(id="#a")
        assert len(result) == 1
        assert result.entities[0].id == "#a"

    def test_select_nonexistent_id(self):
        g = _build_graph()
        result = g.select(id="#nonexistent")
        assert len(result) == 0


class TestSelectCombined:
    def test_type_and_source(self):
        g = _build_graph()
        result = g.select(entity_types=["Person"], source="crate1/")
        assert len(result) == 2  # alice and bob, not eve (crate2)

    def test_empty_result(self):
        g = _build_graph()
        result = g.select(entity_types=["Organisation"], source="crate1/")
        assert len(result) == 0


class TestSelectPreservesEdges:
    def test_subgraph_keeps_internal_edges(self):
        g = _build_graph()
        result = g.select(entity_types=["Person", "Organisation"])
        # Should keep memberOf and employedAt edges (both endpoints present).
        member_rels = [r for r in result.relationships if r.type == "memberOf"]
        assert len(member_rels) == 2

    def test_subgraph_drops_external_edges(self):
        g = _build_graph()
        result = g.select(entity_types=["Person"])
        # No Organisation node → memberOf edges should be dropped.
        assert all(r.type != "memberOf" for r in result.relationships)


class TestSelectTimeRange:
    def test_time_range_validation(self):
        g = _build_graph()
        with pytest.raises(ValueError, match="Start of range"):
            g.select(time_range=(1901, 1837))

    def test_time_range_filters_year_properties(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Event"], properties={"year": 1900}))
        g._add_node(Entity(id="#b", types=["Event"], properties={"year": 2000}))
        result = g.select(time_range=(1800, 1950))
        assert {e.id for e in result.entities} == {"#a"}

    def test_time_range_matches_overlapping_start_end_dates(self):
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["Membership"],
                properties={"startDate": "1910-01-01", "endDate": "1920-12-31"},
            )
        )
        g._add_node(
            Entity(
                id="#b",
                types=["Membership"],
                properties={"startDate": "1930-01-01", "endDate": "1940-12-31"},
            )
        )
        result = g.select(time_range=(1915, 1925))
        assert {e.id for e in result.entities} == {"#a"}

    def test_time_range_matches_human_format_dates(self):
        # The shared engine now parses human month-name dates the old regex
        # only saw a year in — overlap still works on "1 July 1935" etc.
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["Membership"],
                properties={"startDate": "1 July 1935", "endDate": "6 June 1978"},
            )
        )
        g._add_node(
            Entity(
                id="#b",
                types=["Membership"],
                properties={"startDate": "12 March 2017", "endDate": "3 August 2018"},
            )
        )
        result = g.select(time_range=(1940, 1950))
        assert {e.id for e in result.entities} == {"#a"}

    def test_time_range_matches_isostring_and_bare_year(self):
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["Event"],
                properties={"startDateISOString": "1890-05-04 00:00:00"},
            )
        )
        g._add_node(Entity(id="#b", types=["Event"], properties={"endDate": "1607"}))
        result = g.select(time_range=(1850, 1900))
        assert {e.id for e in result.entities} == {"#a"}
