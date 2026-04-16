"""Tests for Graph.collapse_edges() — parallel edge collapsing."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_parallel_graph() -> Graph:
    """Two nodes with multiple same-direction edges."""
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#b", types=["Organisation"], properties={"name": "CSIRO"}))
    g._add_edge(Relationship(source="#a", target="#b", type="author"))
    g._add_edge(Relationship(source="#a", target="#b", type="editor"))
    g._add_edge(Relationship(source="#a", target="#b", type="reviewer"))
    return g


def _build_bidirectional_graph() -> Graph:
    """Two nodes with edges in both directions."""
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob"}))
    g._add_edge(Relationship(source="#a", target="#b", type="author"))
    g._add_edge(Relationship(source="#b", target="#a", type="reviewer"))
    return g


class TestCollapseParallelEdges:
    def test_parallel_edges_become_one(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        assert len(collapsed.relationships) == 1

    def test_collapsed_edge_has_count(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.properties["count"] == 3

    def test_collapsed_edge_has_types_list(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.properties["types"] == ["author", "editor", "reviewer"]

    def test_collapsed_edge_marked_as_collapsed(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.properties["collapsed"] is True

    def test_same_direction_not_bidirectional(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.properties["bidirectional"] is False

    def test_collapsed_edge_has_weight(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.properties["weight"] == 3

    def test_collapsed_type_label_mixed(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.type == "3 relationships"

    def test_collapsed_type_label_uniform(self):
        """All edges same type -> keep that type as the label."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["Org"]))
        g._add_edge(Relationship(source="#a", target="#b", type="memberOf"))
        g._add_edge(Relationship(source="#a", target="#b", type="memberOf"))
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.type == "memberOf"

    def test_preserves_direction(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.source == "#a"
        assert rel.target == "#b"

    def test_collapsed_edge_id_is_none(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.id is None


class TestCollapseBidirectional:
    def test_bidirectional_becomes_one_edge(self):
        g = _build_bidirectional_graph()
        collapsed = g.collapse_edges()
        assert len(collapsed.relationships) == 1

    def test_bidirectional_flag(self):
        g = _build_bidirectional_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.properties["bidirectional"] is True

    def test_bidirectional_canonical_ordering(self):
        """Source/target ordered alphabetically when bidirectional."""
        g = _build_bidirectional_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.source == "#a"  # #a < #b alphabetically
        assert rel.target == "#b"

    def test_bidirectional_types_sorted(self):
        g = _build_bidirectional_graph()
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.properties["types"] == ["author", "reviewer"]


class TestCollapseNoOp:
    def test_single_edge_unchanged(self):
        """Single edges pass through without collapsed metadata."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["Org"]))
        g._add_edge(Relationship(source="#a", target="#b", type="author"))
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert "collapsed" not in rel.properties
        assert rel.type == "author"

    def test_empty_graph(self):
        g = Graph()
        collapsed = g.collapse_edges()
        assert len(collapsed) == 0
        assert len(collapsed.relationships) == 0

    def test_nodes_preserved(self):
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        assert len(collapsed) == len(g)
        assert set(e.id for e in collapsed.entities) == set(e.id for e in g.entities)


class TestCollapseSelfLoops:
    def test_self_loops_collapse(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_edge(Relationship(source="#a", target="#a", type="selfRef"))
        g._add_edge(Relationship(source="#a", target="#a", type="alias"))
        collapsed = g.collapse_edges()
        assert len(collapsed.relationships) == 1
        rel = collapsed.relationships[0]
        assert rel.properties["bidirectional"] is False

    def test_single_self_loop_unchanged(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_edge(Relationship(source="#a", target="#a", type="selfRef"))
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert "collapsed" not in rel.properties


class TestCollapseAfterMerge:
    def test_sums_existing_weights(self):
        """Edges from merge_nodes() carry weight; collapse_edges() sums them."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["Org"]))
        g._add_edge(Relationship(source="#a", target="#b", type="rel1", properties={"weight": 5}))
        g._add_edge(Relationship(source="#a", target="#b", type="rel2", properties={"weight": 3}))
        collapsed = g.collapse_edges()
        rel = collapsed.relationships[0]
        assert rel.properties["weight"] == 8
        assert rel.properties["count"] == 2


class TestCollapsePreservesMetadata:
    def test_source_preserved(self):
        g = Graph(source="test.zip")
        g._add_node(Entity(id="#a", types=["Person"]))
        collapsed = g.collapse_edges()
        assert collapsed.source == "test.zip"

    def test_metadata_preserved(self):
        g = Graph(metadata={"key": "value"})
        g._add_node(Entity(id="#a", types=["Person"]))
        collapsed = g.collapse_edges()
        assert collapsed.metadata["key"] == "value"


class TestVisualiseConvenience:
    def test_collapse_edges_reduces_relationships(self):
        """collapse_edges=True produces a graph with fewer edges."""
        g = _build_parallel_graph()
        collapsed = g.collapse_edges()
        assert len(collapsed.relationships) < len(g.relationships)

    def test_original_graph_unchanged(self):
        """visualise(collapse_edges=True) does not modify the original graph."""
        g = _build_parallel_graph()
        g.visualise(collapse_edges=True)
        assert len(g.relationships) == 3
