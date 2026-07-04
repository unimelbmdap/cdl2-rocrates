"""Tests for lazy _source_names and the memoised _source_name helper."""

from __future__ import annotations

from crategraph.core.graph import Graph, _source_name
from crategraph.core.models import Entity, Relationship


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], source="/data/crates/alpha"))
    g._add_node(Entity(id="#b", types=["Person"], source="/data/crates/alpha"))
    g._add_node(Entity(id="#c", types=["File"], source="/data/crates/beta"))
    g._add_node(Entity(id="#d", types=["File"]))  # source=None
    g._add_edge(Relationship(source="#a", target="#b", type="knows"))
    return g


class TestSourceName:
    def test_extracts_final_path_component(self):
        assert _source_name("/data/crates/alpha") == "alpha"

    def test_memoised_same_result_on_repeat(self):
        first = _source_name("/data/crates/beta")
        second = _source_name("/data/crates/beta")
        assert first == second == "beta"


class TestLazySourceNames:
    def test_sources_sorted_and_deduped(self):
        g = _build_graph()
        assert g.sources == ["alpha", "beta"]

    def test_cache_starts_unbuilt(self):
        g = _build_graph()
        assert g._source_names is None

    def test_add_node_invalidates(self):
        g = _build_graph()
        assert g.sources == ["alpha", "beta"]  # builds the cache
        g._add_node(Entity(id="#e", types=["File"], source="/data/crates/gamma"))
        assert g._source_names is None
        assert g.sources == ["alpha", "beta", "gamma"]

    def test_derived_graph_starts_unbuilt_and_correct(self):
        g = _build_graph()
        derived = g.select(entity_types=["Person"])
        assert derived._source_names is None
        assert derived.sources == ["alpha"]

    def test_none_sources_ignored(self):
        g = Graph()
        g._add_node(Entity(id="#only", types=["File"]))
        assert g.sources == []
