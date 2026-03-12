"""Tests for Graph.profile() — structural profiling."""

from __future__ import annotations

from crategraph.core.analysis import GraphProfile
from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_simple_graph() -> Graph:
    """4 nodes, 4 edges — same fixture as test_analysis.py."""
    g = Graph(source="/tmp/test-crate")
    g._add_node(Entity(id="#a", types=["Person"]))
    g._add_node(Entity(id="#b", types=["Person"]))
    g._add_node(Entity(id="#c", types=["Organisation"]))
    g._add_node(Entity(id="#d", types=["Event"]))
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#a", target="#d", type="attended"))
    g._add_edge(Relationship(source="#b", target="#d", type="attended"))
    return g


def _build_disconnected_graph() -> Graph:
    """One connected pair + two isolates (3 components total)."""
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"]))
    g._add_node(Entity(id="#b", types=["Person"]))
    g._add_node(Entity(id="#c", types=["Organisation"]))
    g._add_node(Entity(id="#d", types=["Event"]))  # isolate
    g._add_edge(Relationship(source="#a", target="#b", type="knows"))
    return g


def _build_multigraph() -> Graph:
    """Parallel edges between same pair."""
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"]))
    g._add_node(Entity(id="#b", types=["Organisation"]))
    g._add_edge(Relationship(source="#a", target="#b", type="memberOf"))
    g._add_edge(Relationship(source="#a", target="#b", type="worksFor"))
    g._add_edge(Relationship(source="#a", target="#b", type="founderOf"))
    return g


class TestGraphProfile:
    def test_returns_graph_profile(self):
        g = _build_simple_graph()
        p = g.profile()
        assert isinstance(p, GraphProfile)

    def test_entity_count(self):
        g = _build_simple_graph()
        assert g.profile().entity_count == 4

    def test_relationship_count(self):
        g = _build_simple_graph()
        assert g.profile().relationship_count == 4

    def test_density_simple(self):
        # 4 nodes, 4 edges, max directed edges = 4*3 = 12
        p = _build_simple_graph().profile()
        assert abs(p.density - 4 / 12) < 1e-9

    def test_density_exceeds_one_with_multi_edges(self):
        # 2 nodes, 3 edges, max simple directed = 2*1 = 2 → density = 1.5
        p = _build_multigraph().profile()
        assert abs(p.density - 3 / 2) < 1e-9

    def test_density_empty(self):
        assert Graph().profile().density == 0.0

    def test_entity_type_count(self):
        p = _build_simple_graph().profile()
        assert p.entity_type_count == 3  # Person, Organisation, Event

    def test_relationship_type_count(self):
        p = _build_simple_graph().profile()
        assert p.relationship_type_count == 2  # memberOf, attended

    def test_component_count_connected(self):
        p = _build_simple_graph().profile()
        assert p.component_count == 1

    def test_component_count_disconnected(self):
        p = _build_disconnected_graph().profile()
        assert p.component_count == 3  # {a,b}, {c}, {d}

    def test_largest_component_fraction_connected(self):
        p = _build_simple_graph().profile()
        assert p.largest_component_fraction == 1.0

    def test_largest_component_fraction_disconnected(self):
        p = _build_disconnected_graph().profile()
        assert abs(p.largest_component_fraction - 0.5) < 1e-9  # {a,b} = 2/4

    def test_max_degree(self):
        p = _build_simple_graph().profile()
        assert p.max_degree == 2

    def test_mean_degree(self):
        # All nodes have degree 2 (unique neighbours)
        p = _build_simple_graph().profile()
        assert abs(p.mean_degree - 2.0) < 1e-9

    def test_median_degree(self):
        p = _build_simple_graph().profile()
        assert abs(p.median_degree - 2.0) < 1e-9

    def test_degree_skewness_uniform(self):
        # All same degree -> skewness ~0
        p = _build_simple_graph().profile()
        assert abs(p.degree_skewness) < 1e-9

    def test_max_edge_multiplicity_simple(self):
        p = _build_simple_graph().profile()
        assert p.max_edge_multiplicity == 1

    def test_max_edge_multiplicity_multi(self):
        p = _build_multigraph().profile()
        assert p.max_edge_multiplicity == 3

    def test_mean_edge_multiplicity_simple(self):
        p = _build_simple_graph().profile()
        assert abs(p.mean_edge_multiplicity - 1.0) < 1e-9

    def test_mean_edge_multiplicity_multi(self):
        p = _build_multigraph().profile()
        assert abs(p.mean_edge_multiplicity - 3.0) < 1e-9

    def test_self_loop_count_none(self):
        p = _build_simple_graph().profile()
        assert p.self_loop_count == 0

    def test_self_loop_count(self):
        g = _build_simple_graph()
        g._add_edge(Relationship(source="#a", target="#a", type="selfRef"))
        assert g.profile().self_loop_count == 1

    def test_isolate_count_none(self):
        p = _build_simple_graph().profile()
        assert p.isolate_count == 0

    def test_isolate_count(self):
        p = _build_disconnected_graph().profile()
        assert p.isolate_count == 2  # #c and #d have no edges

    def test_edge_multiplicity_self_loop_only(self):
        """Self-loop-only graph has no node pairs — multiplicity should be 0."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_edge(Relationship(source="#a", target="#a", type="selfRef"))
        p = g.profile()
        assert p.max_edge_multiplicity == 0
        assert p.mean_edge_multiplicity == 0.0
        assert p.self_loop_count == 1

    def test_source_captured(self):
        p = _build_simple_graph().profile()
        assert p.source == "/tmp/test-crate"

    def test_empty_graph(self):
        p = Graph().profile()
        assert p.entity_count == 0
        assert p.relationship_count == 0
        assert p.component_count == 0
        assert p.max_degree == 0
        assert p.isolate_count == 0


class TestEntityTypeDistribution:
    def test_entity_type_counts(self):
        p = _build_simple_graph().profile()
        assert p.entity_type_counts == {"Person": 2, "Organisation": 1, "Event": 1}

    def test_relationship_type_counts(self):
        p = _build_simple_graph().profile()
        assert p.relationship_type_counts == {"memberOf": 2, "attended": 2}

    def test_top_entity_type_fraction_uniform(self):
        """Person is 2/4 = 0.5 of entities."""
        p = _build_simple_graph().profile()
        assert abs(p.top_entity_type_fraction - 0.5) < 1e-9

    def test_top_entity_type_fraction_dominated(self):
        """Graph dominated by one type."""
        g = Graph()
        for i in range(9):
            g._add_node(Entity(id=f"#f{i}", types=["File"]))
        g._add_node(Entity(id="#d", types=["Dataset"]))
        p = g.profile()
        assert abs(p.top_entity_type_fraction - 0.9) < 1e-9

    def test_top_entity_type_fraction_empty(self):
        assert Graph().profile().top_entity_type_fraction == 0.0

    def test_counts_sorted_by_frequency(self):
        """entity_type_counts should be ordered most-common first."""
        p = _build_simple_graph().profile()
        counts = list(p.entity_type_counts.values())
        assert counts == sorted(counts, reverse=True)

    def test_counts_use_primary_type(self):
        """Multi-type entities are counted by their first type only."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person", "Agent"]))
        g._add_node(Entity(id="#b", types=["Person"]))
        p = g.profile()
        assert p.entity_type_counts == {"Person": 2}
        # But entity_type_count includes all unique types.
        assert p.entity_type_count == 2  # Person, Agent


class TestDataEntityFraction:
    def test_mixed_data_and_contextual(self):
        g = Graph()
        g._add_node(Entity(id="data.csv", types=["File"]))
        g._add_node(Entity(id="subdir/", types=["Dataset"]))
        g._add_node(Entity(id="#alice", types=["Person"]))
        g._add_node(Entity(id="#org", types=["Organisation"]))
        p = g.profile()
        assert p.data_entity_count == 2
        assert abs(p.data_entity_fraction - 0.5) < 1e-9

    def test_root_dataset_excluded(self):
        g = Graph()
        g._add_node(Entity(id="./", types=["Dataset"]))
        g._add_node(Entity(id="file.txt", types=["File"]))
        p = g.profile()
        assert p.data_entity_count == 1
        assert abs(p.data_entity_fraction - 0.5) < 1e-9

    def test_all_contextual(self):
        p = _build_simple_graph().profile()
        assert p.data_entity_count == 0
        assert p.data_entity_fraction == 0.0

    def test_empty_graph(self):
        p = Graph().profile()
        assert p.data_entity_count == 0
        assert p.data_entity_fraction == 0.0


class TestGraphProfileRepr:
    def test_repr_contains_density(self):
        r = repr(_build_simple_graph().profile())
        assert "density" in r.lower()

    def test_repr_contains_components(self):
        r = repr(_build_simple_graph().profile())
        assert "component" in r.lower()

    def test_repr_html_is_pre_block(self):
        html = _build_simple_graph().profile()._repr_html_()
        assert "<pre" in html
