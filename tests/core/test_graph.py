"""Tests for crategraph.core.graph — Graph class core structure."""

from __future__ import annotations

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


class TestGraphCreation:
    def test_empty_graph(self):
        g = Graph()
        assert g.source is None
        assert g.metadata == {}
        assert len(g) == 0

    def test_graph_with_source_and_metadata(self):
        g = Graph(source="crate.zip", metadata={"@context": "https://w3id.org/ro/crate/1.1"})
        assert g.source == "crate.zip"
        assert g.metadata["@context"] == "https://w3id.org/ro/crate/1.1"


class TestTitle:
    def test_uses_name_from_metadata(self):
        g = Graph(metadata={"name": "My Crate"})
        assert g.title == "My Crate"

    def test_falls_back_to_title_key(self):
        g = Graph(metadata={"title": "Other"})
        assert g.title == "Other"

    def test_name_takes_precedence_over_title(self):
        g = Graph(metadata={"name": "TheName", "title": "TheTitle"})
        assert g.title == "TheName"

    def test_unwraps_single_item_list_name(self):
        g = Graph(metadata={"name": ["My Crate"]})
        assert g.title == "My Crate"

    def test_unwraps_single_item_list_title(self):
        g = Graph(metadata={"title": ["Other"]})
        assert g.title == "Other"

    def test_fallback_when_metadata_empty(self):
        assert Graph().title == "Untitled RO-Crate"

    def test_fallback_when_name_and_title_blank(self):
        g = Graph(metadata={"name": "", "title": ""})
        assert g.title == "Untitled RO-Crate"

    def test_ignores_non_string_name(self):
        # If "name" happens to be a dict (e.g. malformed crate), don't
        # return the dict — fall through to title or default.
        g = Graph(metadata={"name": {"@id": "#x"}, "title": "Fallback"})
        assert g.title == "Fallback"

    def test_multi_crate_combines_names(self):
        # Mirrors the metadata shape Crate(*paths) produces in multi-crate mode.
        g = Graph(
            metadata={
                "crate-a": {"name": "Crate A"},
                "crate-b": {"name": "Crate B"},
            }
        )
        assert g.title == "Crate A, Crate B"

    def test_multi_crate_falls_through_to_title_key_per_crate(self):
        g = Graph(
            metadata={
                "crate-a": {"name": "Crate A"},
                "crate-b": {"title": "Crate B"},
            }
        )
        assert g.title == "Crate A, Crate B"

    def test_multi_crate_skips_unnamed_per_crate(self):
        g = Graph(
            metadata={
                "crate-a": {"name": "Crate A"},
                "crate-b": {},
            }
        )
        assert g.title == "Crate A"

    def test_does_not_pick_name_from_unrelated_nested_dict(self):
        # Single-crate metadata may have dict-valued fields (author,
        # publisher, JSON-LD @context, etc.) without a top-level name.
        # The multi-crate fallback must not misfire and pull a name out
        # of these unrelated fields.
        g = Graph(
            metadata={
                "@context": "https://w3id.org/ro/crate/1.1/context",
                "@type": "Dataset",
                "author": {"@id": "#alice", "name": "Alice Smith"},
            }
        )
        assert g.title == "Untitled RO-Crate"


class TestAddNode:
    def test_add_entity(self):
        g = Graph()
        e = Entity(id="#alice", types=["Person"], properties={"name": "Alice"})
        g._add_node(e)
        assert len(g) == 1
        assert g._entities["#alice"] == e

    def test_add_duplicate_entity_updates(self):
        g = Graph()
        e1 = Entity(id="#alice", types=["Person"], properties={"name": "Alice"})
        e2 = Entity(id="#alice", types=["Person"], properties={"name": "Alice B."})
        g._add_node(e1)
        g._add_node(e2)
        assert len(g) == 1
        assert g._entities["#alice"].properties["name"] == "Alice B."


class TestAddEdge:
    def test_add_relationship(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["File"]))
        r = Relationship(source="#a", target="#b", type="author")
        g._add_edge(r)
        assert len(g._relationships) == 1
        assert g._relationships[0] == r

    def test_add_multiple_edges(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["File"]))
        r1 = Relationship(source="#a", target="#b", type="author")
        r2 = Relationship(source="#a", target="#b", type="contributor")
        g._add_edge(r1)
        g._add_edge(r2)
        assert len(g._relationships) == 2

    def test_missing_endpoint_is_skipped(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        r = Relationship(source="#a", target="#missing", type="author")
        with pytest.warns(UserWarning, match="missing endpoint"):
            g._add_edge(r)
        assert len(g._relationships) == 0
        assert "#missing" not in g._entities


class TestNeighbours:
    def _build_graph(self) -> Graph:
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["File"]))
        g._add_node(Entity(id="#c", types=["Dataset"]))
        g._add_edge(Relationship(source="#a", target="#b", type="author"))
        g._add_edge(Relationship(source="#b", target="#c", type="hasPart"))
        return g

    def test_neighbours_of_node(self):
        g = self._build_graph()
        neighbours = g._neighbours("#a")
        assert "#b" in neighbours

    def test_neighbours_of_middle_node(self):
        g = self._build_graph()
        neighbours = g._neighbours("#b")
        # MultiDiGraph: successors + predecessors
        assert "#a" in neighbours or "#c" in neighbours

    def test_neighbours_of_unknown_node(self):
        g = self._build_graph()
        neighbours = g._neighbours("#unknown")
        assert neighbours == set()


class TestSubgraph:
    def _build_graph(self) -> Graph:
        g = Graph(source="test.zip", metadata={"key": "value"})
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["File"]))
        g._add_node(Entity(id="#c", types=["Dataset"]))
        g._add_edge(Relationship(source="#a", target="#b", type="author"))
        g._add_edge(Relationship(source="#b", target="#c", type="hasPart"))
        return g

    def test_subgraph_contains_only_specified_nodes(self):
        g = self._build_graph()
        sub = g._subgraph({"#a", "#b"})
        assert len(sub) == 2
        assert "#a" in sub._entities
        assert "#b" in sub._entities
        assert "#c" not in sub._entities

    def test_subgraph_retains_relevant_edges(self):
        g = self._build_graph()
        sub = g._subgraph({"#a", "#b"})
        assert len(sub._relationships) == 1
        assert sub._relationships[0].type == "author"

    def test_subgraph_drops_cross_boundary_edges(self):
        g = self._build_graph()
        sub = g._subgraph({"#a"})
        assert len(sub._relationships) == 0

    def test_subgraph_preserves_source_and_metadata(self):
        g = self._build_graph()
        sub = g._subgraph({"#a"})
        assert sub.source == "test.zip"
        assert sub.metadata == {"key": "value"}

    def test_subgraph_returns_new_graph(self):
        g = self._build_graph()
        sub = g._subgraph({"#a", "#b"})
        assert sub is not g


class TestLen:
    def test_len_counts_entities(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["File"]))
        assert len(g) == 2


class TestEntities:
    def test_entities_property(self):
        g = Graph()
        e = Entity(id="#a", types=["Person"])
        g._add_node(e)
        entities = g.entities
        assert len(entities) == 1
        assert entities[0] == e

    def test_relationships_property(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"]))
        g._add_node(Entity(id="#b", types=["File"]))
        r = Relationship(source="#a", target="#b", type="author")
        g._add_edge(r)
        rels = g.relationships
        assert len(rels) == 1
        assert rels[0] == r


class TestFiles:
    def test_files_returns_only_data_entities(self):
        g = Graph()
        g._add_node(Entity(id="./", types=["Dataset"], properties={"_is_root": True}))
        g._add_node(Entity(id="#alice", types=["Person"]))
        g._add_node(
            Entity(id="data.csv", types=["File"], properties={"encodingFormat": "text/csv"})
        )
        g._add_node(Entity(id="subdir/", types=["Dataset"]))
        files = g.files
        assert len(files) == 2
        ids = [e.id for e in files]
        assert "data.csv" in ids
        assert "subdir/" in ids
        assert "./" not in ids
        assert "#alice" not in ids

    def test_files_sorted_by_id(self):
        g = Graph()
        g._add_node(Entity(id="z.txt", types=["File"]))
        g._add_node(Entity(id="a.txt", types=["File"]))
        files = g.files
        assert [e.id for e in files] == ["a.txt", "z.txt"]

    def test_files_empty_graph(self):
        g = Graph()
        files = g.files
        assert len(files) == 0

    def test_files_returns_list(self):
        g = Graph()
        g._add_node(Entity(id="data.csv", types=["File"]))
        assert isinstance(g.files, list)
