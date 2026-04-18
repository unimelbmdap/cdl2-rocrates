"""Tests for Graph analysis methods: summary, most_connected, coverage."""

from __future__ import annotations

from crategraph.core import analysis as analysis_mod
from crategraph.core.analysis import GraphSummary
from crategraph.core.graph import Graph
from crategraph.core.models import CoverageResult, Entity, Relationship


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"]))
    g._add_node(Entity(id="#b", types=["Person"]))
    g._add_node(Entity(id="#c", types=["Organisation"]))
    g._add_node(Entity(id="#d", types=["Event"]))
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#a", target="#d", type="attended"))
    g._add_edge(Relationship(source="#b", target="#d", type="attended"))
    return g


class TestSummary:
    def test_returns_graph_summary(self):
        g = _build_graph()
        s = g.summary()
        assert isinstance(s, GraphSummary)

    def test_entity_count(self):
        g = _build_graph()
        s = g.summary()
        assert s.entity_count == 4

    def test_relationship_count(self):
        g = _build_graph()
        s = g.summary()
        assert s.relationship_count == 4

    def test_entity_type_counts(self):
        g = _build_graph()
        s = g.summary()
        assert s.entity_type_counts["Person"] == 2
        assert s.entity_type_counts["Organisation"] == 1
        assert s.entity_type_counts["Event"] == 1

    def test_relationship_type_counts(self):
        g = _build_graph()
        s = g.summary()
        assert s.relationship_type_counts["memberOf"] == 2
        assert s.relationship_type_counts["attended"] == 2

    def test_summary_has_most_connected(self):
        g = _build_graph()
        s = g.summary()
        assert isinstance(s.most_connected, list)
        assert len(s.most_connected) == 3
        for name, degree in s.most_connected:
            assert isinstance(name, str)
            assert degree == 2

    def test_summary_most_connected_empty_graph(self):
        g = Graph()
        s = g.summary()
        assert s.most_connected == []

    def test_summary_shows_source(self):
        g = Graph(source="test-crate.json")
        g._add_node(Entity(id="#a", types=["Person"]))
        s = g.summary()
        r = repr(s)
        assert "test-crate.json" in r

    def test_summary_no_source_line_when_none(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        s = g.summary()
        r = repr(s)
        assert "Source" not in r

    def test_summary_repr_header(self):
        g = _build_graph()
        s = g.summary()
        r = repr(s)
        assert "=== Graph Summary ===" in r

    def test_summary_repr_counts(self):
        g = _build_graph()
        s = g.summary()
        r = repr(s)
        assert "Entities: 4" in r
        assert "Relationships: 4" in r

    def test_summary_repr_entity_types(self):
        g = _build_graph()
        s = g.summary()
        r = repr(s)
        assert "Person" in r
        assert "Organisation" in r

    def test_summary_repr_sparkline_bars(self):
        g = _build_graph()
        s = g.summary()
        r = repr(s)
        assert "\u2592" in r

    def test_summary_repr_most_connected(self):
        g = _build_graph()
        s = g.summary()
        r = repr(s)
        assert "Most connected:" in r

    def test_summary_repr_collapses_extra_types(self):
        """When there are more than 5 types, show top 5 and collapse the rest."""
        g = Graph()
        for i in range(7):
            g._add_node(Entity(id=f"#{i}", types=[f"Type{i}"]))
        s = g.summary()
        r = repr(s)
        assert "+2 more" in r

    def test_summary_html_is_pre_block(self):
        g = _build_graph()
        s = g.summary()
        html = s._repr_html_()
        assert "<pre" in html
        assert "<table" not in html

    def test_summary_html_contains_types(self):
        g = _build_graph()
        s = g.summary()
        html = s._repr_html_()
        assert "Person" in html
        assert "memberOf" in html

    def test_empty_graph_summary(self):
        g = Graph()
        s = g.summary()
        assert s.entity_count == 0
        assert s.relationship_count == 0


class TestMostConnected:
    def test_returns_sorted_list(self):
        g = _build_graph()
        result = g.most_connected(n=10)
        assert len(result) == 4
        # Degrees should be descending.
        degrees = [d for _, d in result]
        assert degrees == sorted(degrees, reverse=True)

    def test_top_n_limit(self):
        g = _build_graph()
        result = g.most_connected(n=2)
        assert len(result) == 2

    def test_most_connected_entities(self):
        g = _build_graph()
        result = g.most_connected(n=2)
        # alice and bob each have 2 connections; org and event also have 2.
        # All have degree 2, so top 2 is any of them.
        for _, degree in result:
            assert degree >= 2

    def test_empty_graph(self):
        g = Graph()
        result = g.most_connected()
        assert result == []


class TestDetectCommunities:
    def test_returns_dict_mapping_ids_to_ints(self):
        g = _build_graph()
        result = analysis_mod.detect_communities(g)
        assert isinstance(result, dict)
        for key, value in result.items():
            assert isinstance(key, str)
            assert isinstance(value, int)

    def test_all_entities_assigned(self):
        g = _build_graph()
        result = analysis_mod.detect_communities(g)
        assert set(result.keys()) == set(g._entities.keys())

    def test_empty_graph(self):
        g = Graph()
        result = analysis_mod.detect_communities(g)
        assert result == {}

    def test_single_node(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        result = analysis_mod.detect_communities(g)
        assert result == {"#a": 0}

    def test_connected_nodes_same_community(self):
        """Densely connected nodes should share a community."""
        g = Graph()
        for i in range(4):
            g._add_node(Entity(id=f"#a{i}", types=["Person"]))
        for i in range(4):
            for j in range(i + 1, 4):
                g._add_edge(Relationship(source=f"#a{i}", target=f"#a{j}", type="knows"))
        result = analysis_mod.detect_communities(g)
        communities = set(result.values())
        assert len(communities) == 1

    def test_resolution_parameter(self):
        g = _build_graph()
        result = analysis_mod.detect_communities(g, resolution=1.0)
        assert isinstance(result, dict)

    def test_deterministic_with_seed(self):
        g = _build_graph()
        r1 = analysis_mod.detect_communities(g, seed=42)
        r2 = analysis_mod.detect_communities(g, seed=42)
        assert r1 == r2


class TestGraphDetectCommunities:
    def test_returns_new_graph(self):
        g = _build_graph()
        result = g.detect_communities()
        assert result is not g

    def test_entities_have_community_property(self):
        g = _build_graph()
        for e in g.detect_communities().entities:
            assert "community" in e.properties
            assert isinstance(e.properties["community"], int)

    def test_original_unchanged(self):
        g = _build_graph()
        g.detect_communities()
        for e in g.entities:
            assert "community" not in e.properties

    def test_preserves_entity_count(self):
        g = _build_graph()
        assert len(g.detect_communities()) == len(g)

    def test_preserves_relationships(self):
        g = _build_graph()
        assert len(g.detect_communities().relationships) == len(g.relationships)

    def test_internal_graph_nodes_use_updated_entities(self):
        g = _build_graph()
        result = g.detect_communities()
        for eid, entity in result._entities.items():
            assert result._graph.nodes[eid]["entity"] is entity
            assert (
                result._graph.nodes[eid]["entity"].properties["community"]
                == entity.properties["community"]
            )

    def test_seed_deterministic(self):
        g = _build_graph()
        r1 = g.detect_communities(seed=42)
        r2 = g.detect_communities(seed=42)
        for eid in g._entities:
            assert r1.get(eid).properties["community"] == r2.get(eid).properties["community"]

    def test_empty_graph(self):
        assert len(Graph().detect_communities()) == 0


def _build_coverage_graph() -> Graph:
    """Build a graph with known coverage gaps for testing.

    Structure:
    - 5 Persons, 10 Functions, 2 Organisations
    - 6 reified "EFRship" edges: Person→Function (3 of 5 Persons, 6 of 10 Functions)
    - 5 inline "worksFor" edges: Person→Organisation (all 5 Persons, both Orgs)
    """
    g = Graph()

    # Entities.
    for i in range(5):
        g._add_node(Entity(id=f"#person-{i}", types=["Person"]))
    for i in range(10):
        g._add_node(Entity(id=f"#func-{i}", types=["Function"]))
    for i in range(2):
        g._add_node(Entity(id=f"#org-{i}", types=["Organisation"]))

    # 6 reified EFRship edges (persons 0-2 → functions 0-5).
    for i in range(6):
        g._add_edge(
            Relationship(
                source=f"#person-{i % 3}",
                target=f"#func-{i}",
                type="EFRship",
                id=f"#efr-{i}",
            )
        )

    # 5 inline worksFor edges (all persons → orgs, round-robin).
    for i in range(5):
        g._add_edge(
            Relationship(
                source=f"#person-{i}",
                target=f"#org-{i % 2}",
                type="worksFor",
            )
        )

    return g


class TestCoverage:
    def test_returns_list_of_coverage_results(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        assert isinstance(results, list)
        assert all(isinstance(r, CoverageResult) for r in results)

    def test_reified_only_by_default(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        # Only reified EFRship should appear, not inline worksFor.
        rel_types = {r.pattern.relationship_type for r in results}
        assert "EFRship" in rel_types
        assert "worksFor" not in rel_types

    def test_inline_relations_true(self):
        g = _build_coverage_graph()
        results = g.coverage(inline_relations=True, min_occurrences=1)
        rel_types = {r.pattern.relationship_type for r in results}
        assert "EFRship" in rel_types
        assert "worksFor" in rel_types

    def test_inline_relations_specific_list(self):
        g = _build_coverage_graph()
        results = g.coverage(inline_relations=["worksFor"], min_occurrences=1)
        rel_types = {r.pattern.relationship_type for r in results}
        assert "EFRship" in rel_types
        assert "worksFor" in rel_types

    def test_inline_relations_list_excludes_unlisted(self):
        g = _build_coverage_graph()
        results = g.coverage(inline_relations=["author"], min_occurrences=1)
        rel_types = {r.pattern.relationship_type for r in results}
        assert "EFRship" in rel_types
        assert "worksFor" not in rel_types

    def test_min_occurrences_filters(self):
        g = _build_coverage_graph()
        # EFRship has 6 occurrences, worksFor has 5.
        results_high = g.coverage(inline_relations=True, min_occurrences=6)
        rel_types = {r.pattern.relationship_type for r in results_high}
        assert "EFRship" in rel_types
        assert "worksFor" not in rel_types

    def test_both_sides_measured(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        sides = {r.side for r in results}
        assert sides == {"source", "target"}

    def test_source_side_coverage(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        source_results = [r for r in results if r.side == "source"]
        efr_source = next(r for r in source_results if r.pattern.relationship_type == "EFRship")
        # Persons 0, 1, 2 are sources (3 of 5).
        assert efr_source.entity_type == "Person"
        assert efr_source.reached == 3
        assert efr_source.total == 5

    def test_target_side_coverage(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        target_results = [r for r in results if r.side == "target"]
        efr_target = next(r for r in target_results if r.pattern.relationship_type == "EFRship")
        # Functions 0-5 are targets (6 of 10).
        assert efr_target.entity_type == "Function"
        assert efr_target.reached == 6
        assert efr_target.total == 10

    def test_fraction_property(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        efr_target = next(
            r for r in results if r.pattern.relationship_type == "EFRship" and r.side == "target"
        )
        assert efr_target.fraction == 6 / 10

    def test_unreached_property(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        efr_target = next(
            r for r in results if r.pattern.relationship_type == "EFRship" and r.side == "target"
        )
        assert efr_target.unreached == 4

    def test_sorted_by_fraction_ascending(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        fractions = [r.fraction for r in results]
        assert fractions == sorted(fractions)

    def test_pattern_fields(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        efr = results[0].pattern
        assert efr.relationship_type == "EFRship"
        assert efr.source_type == "Person"
        assert efr.target_type == "Function"
        assert efr.occurrences == 6
        assert efr.reified is True

    def test_empty_graph(self):
        g = Graph()
        results = g.coverage(min_occurrences=1)
        assert results == []

    def test_no_reified_relationships(self):
        """Graph with only inline relationships returns empty when default."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["Org"]))
        for _ in range(5):
            g._add_edge(Relationship(source="#a", target="#b", type="worksFor"))
        results = g.coverage(min_occurrences=1)
        assert results == []

    def test_full_coverage(self):
        """When all entities of a type are reached, fraction is 1.0."""
        g = Graph()
        for i in range(3):
            g._add_node(Entity(id=f"#p-{i}", types=["Person"]))
            g._add_node(Entity(id=f"#o-{i}", types=["Org"]))
            g._add_edge(
                Relationship(source=f"#p-{i}", target=f"#o-{i}", type="member", id=f"#r-{i}")
            )
        results = g.coverage(min_occurrences=1)
        for r in results:
            assert r.fraction == 1.0
            assert r.unreached == 0

    def test_repr(self):
        g = _build_coverage_graph()
        results = g.coverage(min_occurrences=1)
        r = repr(results[0])
        assert "EFRship" in r
        assert "%" in r
