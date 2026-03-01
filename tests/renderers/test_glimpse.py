"""Tests for glimpse transform and Graph.glimpse() integration."""

from __future__ import annotations

import tempfile
from pathlib import Path

from crategraph.core.analysis import merge_by_primary_type
from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#c", types=["Organisation"], properties={"name": "CSIRO"}))
    g._add_node(
        Entity(
            id="#d",
            types=["PublishedResource", "Report"],
            properties={"name": "Report 1"},
        )
    )
    g._add_node(
        Entity(id="#e", types=["PublishedResource", "Book"], properties={"name": "Book 1"})
    )
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#a", target="#d", type="author"))
    g._add_edge(Relationship(source="#b", target="#e", type="author"))
    return g


class TestMergeByPrimaryType:
    def test_groups_by_first_type(self):
        g = _build_graph()
        merged = merge_by_primary_type(g)
        ids = {e.id for e in merged.entities}
        assert "Person" in ids
        assert "Organisation" in ids
        assert "PublishedResource" in ids
        assert "PublishedResource, Report" not in ids

    def test_node_count_property(self):
        g = _build_graph()
        merged = merge_by_primary_type(g)
        counts = {e.id: e.properties["count"] for e in merged.entities}
        assert counts["Person"] == 2
        assert counts["Organisation"] == 1
        assert counts["PublishedResource"] == 2

    def test_edges_between_groups(self):
        g = _build_graph()
        merged = merge_by_primary_type(g)
        assert len(merged.relationships) > 0

    def test_no_self_loops(self):
        g = _build_graph()
        merged = merge_by_primary_type(g)
        for rel in merged.relationships:
            assert rel.source != rel.target

    def test_edge_weights(self):
        g = _build_graph()
        merged = merge_by_primary_type(g)
        org_edges = [
            r for r in merged.relationships if {r.source, r.target} == {"Person", "Organisation"}
        ]
        assert len(org_edges) == 1
        assert org_edges[0].properties["weight"] == 2

    def test_empty_graph(self):
        merged = merge_by_primary_type(Graph())
        assert len(merged) == 0

    def test_entities_with_no_types(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=[], properties={"name": "Mystery"}))
        merged = merge_by_primary_type(g)
        assert len(merged) == 1
        assert merged.entities[0].id == "Unknown"


class TestGraphGlimpse:
    def test_returns_svg_object(self):
        g = _build_graph()
        result = g.glimpse()
        svg_str = result.data if hasattr(result, "data") else str(result)
        assert "<svg" in svg_str

    def test_save_to_filepath(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "glimpse.svg")
            result = g.glimpse(filepath=filepath)
            assert result == filepath
            content = Path(filepath).read_text()
            assert "<svg" in content
            assert "Person" in content

    def test_empty_graph_glimpse(self):
        g = Graph()
        result = g.glimpse()
        svg_str = result.data if hasattr(result, "data") else str(result)
        assert "Empty graph" in svg_str

    def test_subgraph_glimpse(self):
        g = _build_graph()
        sub = g.select(entity_types=["Person"])
        result = sub.glimpse()
        svg_str = result.data if hasattr(result, "data") else str(result)
        assert "Person" in svg_str

    def test_visualise_svg_renderer(self):
        """visualise(renderer='svg') works on any graph."""
        g = _build_graph()
        result = g.visualise(renderer="svg")
        svg_str = result.data if hasattr(result, "data") else str(result)
        assert "<svg" in svg_str
        assert "<circle" in svg_str
