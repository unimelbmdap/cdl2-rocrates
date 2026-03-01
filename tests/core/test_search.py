"""Tests for Graph.search() — fuzzy content search."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice Smith"}))
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob Melbourne"}))
    g._add_node(
        Entity(
            id="#c",
            types=["Organisation"],
            properties={"name": "University of Melbourne"},
        )
    )
    g._add_node(
        Entity(id="#d", types=["Event"], properties={"name": "Annual Conference 2024"})
    )
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    return g


class TestSearchBasic:
    def test_exact_match(self):
        g = _build_graph()
        result = g.search("Alice Smith")
        assert len(result) == 1
        assert result.entities[0].id == "#a"

    def test_partial_match(self):
        g = _build_graph()
        result = g.search("Melbourne")
        assert len(result) >= 2  # Bob Melbourne + University of Melbourne

    def test_case_insensitive(self):
        g = _build_graph()
        result = g.search("melbourne")
        assert len(result) >= 2

    def test_no_match(self):
        g = _build_graph()
        result = g.search("zzzznonexistent", threshold=90)
        assert len(result) == 0


class TestSearchProperties:
    def test_specific_property(self):
        g = _build_graph()
        result = g.search("Melbourne", properties=["name"])
        assert len(result) >= 2

    def test_nonexistent_property(self):
        g = _build_graph()
        result = g.search("Melbourne", properties=["email"])
        assert len(result) == 0


class TestSearchThreshold:
    def test_high_threshold(self):
        g = _build_graph()
        # High threshold — only exact or very close matches.
        result_high = g.search("Melbourne", threshold=95)
        result_low = g.search("Melbourne", threshold=50)
        assert len(result_high) <= len(result_low)

    def test_fuzzy_match(self):
        g = _build_graph()
        # Slight misspelling should still match with default threshold.
        result = g.search("Melborne")
        assert len(result) >= 1


class TestSearchPreservesEdges:
    def test_edges_between_matches(self):
        g = _build_graph()
        result = g.search("Melbourne")
        # Bob and Uni of Melbourne both match, and they share a memberOf edge.
        member_rels = [r for r in result.relationships if r.type == "memberOf"]
        assert len(member_rels) >= 1
