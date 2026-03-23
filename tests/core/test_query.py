"""Tests for crategraph.core.query — Cypher query support."""

from __future__ import annotations

from unittest.mock import patch

import networkx as nx
import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.core.query import (
    _build_nx_graph,
    _normalise_cypher,
    run_cypher,
)


def _sample_graph() -> Graph:
    """Build a small test graph with entities and relationships."""
    g = Graph()
    g._add_node(Entity(id="#alice", types=["Person"], properties={"name": "Alice", "age": "30"}))
    g._add_node(Entity(id="#bob", types=["Person"], properties={"name": "Bob", "age": "25"}))
    g._add_node(Entity(id="#paper", types=["Document"], properties={"name": "Research Paper"}))
    g._add_edge(Relationship(source="#alice", target="#paper", type="author"))
    g._add_edge(Relationship(source="#bob", target="#paper", type="reviewer"))
    g._add_edge(Relationship(source="#alice", target="#bob", type="knows"))
    return g


class TestBuildNxGraph:
    def test_returns_multidigraph(self):
        g = _sample_graph()
        nxg = _build_nx_graph(g)
        assert isinstance(nxg, nx.MultiDiGraph)

    def test_nodes_have_labels(self):
        g = _sample_graph()
        nxg = _build_nx_graph(g)
        assert nxg.nodes["#alice"]["__labels__"] == {"Person"}

    def test_multi_type_entity_has_all_labels(self):
        g = Graph()
        g._add_node(Entity(id="#x", types=["Person", "Author"]))
        nxg = _build_nx_graph(g)
        assert nxg.nodes["#x"]["__labels__"] == {"Person", "Author"}

    def test_node_properties_are_top_level(self):
        g = _sample_graph()
        nxg = _build_nx_graph(g)
        assert nxg.nodes["#alice"]["name"] == "Alice"
        assert nxg.nodes["#alice"]["age"] == "30"

    def test_nodes_have_entity_id_marker(self):
        g = _sample_graph()
        nxg = _build_nx_graph(g)
        assert nxg.nodes["#alice"]["__entity_id__"] == "#alice"

    def test_edges_have_labels(self):
        g = _sample_graph()
        nxg = _build_nx_graph(g)
        edge_data = list(nxg.edges("#alice", data=True))
        author_edges = [d for _, _, d in edge_data if "author" in d["__labels__"]]
        assert len(author_edges) == 1

    def test_edge_count(self):
        g = _sample_graph()
        nxg = _build_nx_graph(g)
        assert nxg.number_of_edges() == 3

    def test_node_count(self):
        g = _sample_graph()
        nxg = _build_nx_graph(g)
        assert nxg.number_of_nodes() == 3


class TestRunCypher:
    def test_basic_match_returns_graph(self):
        g = _sample_graph()
        result = run_cypher(g, "MATCH (a)-[]->(b) RETURN a, b")
        assert isinstance(result, Graph)
        assert len(result) > 0

    def test_match_by_label(self):
        g = _sample_graph()
        result = run_cypher(g, "MATCH (a:Person) RETURN a")
        assert len(result) == 2
        ids = {e.id for e in result.entities}
        assert ids == {"#alice", "#bob"}

    def test_match_by_edge_type(self):
        g = _sample_graph()
        result = run_cypher(g, "MATCH (a)-[:author]->(b) RETURN a, b")
        ids = {e.id for e in result.entities}
        assert "#alice" in ids
        assert "#paper" in ids

    def test_match_with_where(self):
        g = _sample_graph()
        result = run_cypher(g, 'MATCH (a:Person) WHERE a.name = "Alice" RETURN a')
        assert len(result) == 1
        assert result.entities[0].id == "#alice"

    def test_preserves_relationships(self):
        g = _sample_graph()
        result = run_cypher(g, "MATCH (a:Person)-[]->(b:Document) RETURN a, b")
        assert len(result.relationships) > 0

    def test_result_is_subgraph_of_self(self):
        """query() operates on self, not root."""
        g = _sample_graph()
        people_only = g.select(entity_types=["Person"])
        result = run_cypher(people_only, "MATCH (a)-[]->(b) RETURN a, b")
        for entity in result.entities:
            assert "Person" in entity.types

    def test_empty_result_returns_empty_graph(self):
        g = _sample_graph()
        result = run_cypher(g, "MATCH (a:Nonexistent) RETURN a")
        assert len(result) == 0

    def test_empty_graph_returns_empty_graph(self):
        g = Graph()
        result = run_cypher(g, "MATCH (a) RETURN a")
        assert len(result) == 0

    def test_scalar_only_raises_valueerror(self):
        g = _sample_graph()
        with pytest.raises(ValueError, match="returns a Graph"):
            run_cypher(g, "MATCH (a:Person) RETURN a.name")

    def test_invalid_cypher_propagates_error(self):
        from lark.exceptions import UnexpectedCharacters

        g = _sample_graph()
        with pytest.raises(UnexpectedCharacters):
            run_cypher(g, "THIS IS NOT VALID CYPHER")


class TestGraphQueryMethod:
    def test_query_method_exists(self):
        g = _sample_graph()
        result = g.query("MATCH (a:Person) RETURN a")
        assert isinstance(result, Graph)
        assert len(result) == 2

    def test_chaining_select_then_query(self):
        g = _sample_graph()
        result = g.select(entity_types=["Person"]).query("MATCH (a)-[]->(b) RETURN a, b")
        for entity in result.entities:
            assert "Person" in entity.types

    def test_chaining_query_then_expand(self):
        g = _sample_graph()
        alice_only = g.query('MATCH (a:Person) WHERE a.name = "Alice" RETURN a')
        assert len(alice_only) == 1
        expanded = alice_only.expand()
        assert len(expanded) > 1


class TestNormaliseCypher:
    def test_full_cypher_unchanged(self):
        cypher = "MATCH (a:Person) RETURN a"
        assert _normalise_cypher(cypher) == cypher

    def test_full_cypher_case_insensitive(self):
        cypher = "MATCH (a) return a"
        assert _normalise_cypher(cypher) == cypher

    def test_bare_pattern_wrapped(self):
        result = _normalise_cypher("(a:Person)-[:author]->(b)")
        assert result == "MATCH (a:Person)-[:author]->(b) RETURN a, b"

    def test_single_node_pattern(self):
        result = _normalise_cypher("(n:Person)")
        assert result == "MATCH (n:Person) RETURN n"

    def test_deduplicates_variables(self):
        result = _normalise_cypher("(a)-[]->(b)-[]->(a)")
        assert result == "MATCH (a)-[]->(b)-[]->(a) RETURN a, b"

    def test_no_variables_unchanged(self):
        cypher = "not a pattern at all"
        assert _normalise_cypher(cypher) == cypher

    def test_match_without_return_raises(self):
        with pytest.raises(ValueError, match="no RETURN clause"):
            _normalise_cypher("MATCH (a:Person)-[:author]->(b)")


class TestShorthandIntegration:
    def test_shorthand_returns_graph(self):
        g = _sample_graph()
        result = g.query("(a:Person)")
        assert isinstance(result, Graph)
        assert len(result) == 2

    def test_shorthand_with_edge_type(self):
        g = _sample_graph()
        result = g.query("(a)-[:author]->(b)")
        ids = {e.id for e in result.entities}
        assert "#alice" in ids
        assert "#paper" in ids

    def test_shorthand_logs_expansion(self, caplog):
        import logging

        g = _sample_graph()
        with caplog.at_level(logging.DEBUG, logger="crategraph.core.query"):
            g.query("(a:Person)")
        assert "Expanded pattern shorthand" in caplog.text


class TestMissingDependency:
    def test_import_error_with_install_instructions(self):
        g = _sample_graph()
        with (
            patch.dict("sys.modules", {"grandcypher": None}),
            pytest.raises(ImportError, match=r"uv add crategraph\[cypher\]"),
        ):
            g.query("MATCH (a) RETURN a")
