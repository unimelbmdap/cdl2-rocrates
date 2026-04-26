"""Tests for crategraph.writers.graphml.GraphMLWriter."""

from __future__ import annotations

import networkx as nx
import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.writers._flatten import decode_pipe_list
from crategraph.writers.graphml import GraphMLWriter

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_graph(*entities: Entity, relationships: list[Relationship] | None = None) -> Graph:
    """Build a minimal Graph from the given entities and relationships."""
    g = Graph()
    for entity in entities:
        g._add_node(entity)
    for rel in relationships or []:
        g._add_edge(rel)
    return g


def _entity(eid: str, **kwargs) -> Entity:
    """Convenience factory for Entity."""
    return Entity(id=eid, **kwargs)


def _rel(source: str, target: str, rel_type: str = "relatesTo", **kwargs) -> Relationship:
    """Convenience factory for Relationship."""
    return Relationship(source=source, target=target, type=rel_type, **kwargs)


# ---------------------------------------------------------------------------
# 1. Round-trip core fields
# ---------------------------------------------------------------------------


class TestRoundTripCoreFields:
    def test_node_ids_present(self, tmp_path):
        a = _entity("node-A", types=["Person"], properties={"name": "Alice"})
        b = _entity("node-B", types=["Person"], properties={"name": "Bob"})
        rel = _rel("node-A", "node-B", "knows")
        g = _make_graph(a, b, relationships=[rel])
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g, str(out))
        loaded = nx.read_graphml(str(out))
        assert "node-A" in loaded.nodes
        assert "node-B" in loaded.nodes

    def test_node_id_label_type_round_trip(self, tmp_path):
        a = _entity("node-A", types=["Person"], properties={"name": "Alice"})
        b = _entity("node-B", types=["Organisation"])
        rel = _rel("node-A", "node-B", "memberOf")
        g = _make_graph(a, b, relationships=[rel])
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g, str(out))
        loaded = nx.read_graphml(str(out))
        assert loaded.nodes["node-A"]["id"] == "node-A"
        assert loaded.nodes["node-A"]["label"] == "Alice"
        assert loaded.nodes["node-A"]["type"] == "Person"
        assert loaded.nodes["node-B"]["type"] == "Organisation"

    def test_edge_source_target_type_round_trip(self, tmp_path):
        a = _entity("A")
        b = _entity("B")
        rel = _rel("A", "B", "authored")
        g = _make_graph(a, b, relationships=[rel])
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g, str(out))
        loaded = nx.read_graphml(str(out))
        edges = list(loaded.edges(data=True))
        assert len(edges) == 1
        src, tgt, data = edges[0]
        assert src == "A"
        assert tgt == "B"
        assert data["type"] == "authored"
        assert data["source"] == "A"
        assert data["target"] == "B"


# ---------------------------------------------------------------------------
# 2. Scalar property round-trip
# ---------------------------------------------------------------------------


class TestScalarPropertyRoundTrip:
    def test_scalar_properties(self, tmp_path):
        a = _entity(
            "node-A",
            properties={"count": 42, "score": 3.14, "is_public": True, "name_val": "Alice"},
        )
        g = _make_graph(a)
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g, str(out))
        loaded = nx.read_graphml(str(out))
        node_data = loaded.nodes["node-A"]
        # GraphML may coerce types — compare via str() where needed.
        assert str(node_data["count"]) == "42"
        assert str(node_data["score"]) == str(3.14)
        # bool may round-trip as "True"/"False" or as 1/0 depending on lxml vs pure-Python.
        assert str(node_data["is_public"]) in ("True", "1", "true")
        assert node_data["name_val"] == "Alice"


# ---------------------------------------------------------------------------
# 3. List-of-scalars round-trip (pipe encoding)
# ---------------------------------------------------------------------------


class TestListOfScalarsRoundTrip:
    def test_tags_pipe_encoded_and_decodable(self, tmp_path):
        a = _entity("node-A", properties={"tags": ["a", "b", "c|d"]})
        g = _make_graph(a)
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g, str(out))
        loaded = nx.read_graphml(str(out))
        encoded = loaded.nodes["node-A"]["tags"]
        assert isinstance(encoded, str)
        assert decode_pipe_list(encoded) == ["a", "b", "c|d"]


# ---------------------------------------------------------------------------
# 4. Unicode round-trip
# ---------------------------------------------------------------------------


class TestUnicodeRoundTrip:
    def test_unicode_label_and_property(self, tmp_path):
        a = _entity(
            "node-A",
            properties={"name": "Café", "bio": "naïve résumé"},
        )
        g = _make_graph(a)
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g, str(out))
        loaded = nx.read_graphml(str(out))
        assert loaded.nodes["node-A"]["label"] == "Café"
        assert loaded.nodes["node-A"]["bio"] == "naïve résumé"


# ---------------------------------------------------------------------------
# 5. FileExistsError when overwrite=False
# ---------------------------------------------------------------------------


class TestFileExistsGuard:
    def test_raises_file_exists_error(self, tmp_path):
        a = _entity("A")
        g = _make_graph(a)
        out = tmp_path / "graph.graphml"
        out.write_text("")  # pre-create the file
        with pytest.raises(FileExistsError):
            GraphMLWriter().write(g, str(out))

    def test_raises_on_second_write_without_overwrite(self, tmp_path):
        a = _entity("A")
        g = _make_graph(a)
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g, str(out))  # first write — OK
        with pytest.raises(FileExistsError):
            GraphMLWriter().write(g, str(out))  # second write — should raise


# ---------------------------------------------------------------------------
# 6. overwrite=True succeeds
# ---------------------------------------------------------------------------


class TestOverwrite:
    def test_overwrite_true_replaces_file(self, tmp_path):
        a = _entity("A", properties={"name": "First"})
        b = _entity("B", properties={"name": "Second"})
        g1 = _make_graph(a)
        g2 = _make_graph(b)
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g1, str(out))
        GraphMLWriter().write(g2, str(out), overwrite=True)  # must not raise
        loaded = nx.read_graphml(str(out))
        assert "B" in loaded.nodes
        assert "A" not in loaded.nodes


# ---------------------------------------------------------------------------
# 7. Parallel same-type edges
# ---------------------------------------------------------------------------


class TestParallelSameTypeEdges:
    def test_parallel_edges_both_present(self, tmp_path):
        """Two 'author' edges between the same pair with different properties."""
        a = _entity("A")
        b = _entity("B")
        rel1 = _rel("A", "B", "author", properties={"year": 2001})
        rel2 = _rel("A", "B", "author", properties={"year": 2003})
        g = _make_graph(a, b, relationships=[rel1, rel2])
        out = tmp_path / "graph.graphml"
        GraphMLWriter().write(g, str(out))
        loaded = nx.read_graphml(str(out), node_type=str)
        # Verify both edges are present.
        ab_edges = [
            (src, tgt, data)
            for src, tgt, _key, data in loaded.edges(keys=True, data=True)
            if src == "A" and tgt == "B"
        ]
        assert len(ab_edges) == 2, (
            f"Expected 2 parallel edges but found {len(ab_edges)}. "
            "The writer should preserve every Graph relationship."
        )
        years = {str(data.get("year")) for _, _, data in ab_edges}
        assert years == {"2001", "2003"}


# ---------------------------------------------------------------------------
# 8. Registry lookup
# ---------------------------------------------------------------------------


class TestRegistryLookup:
    def test_get_writer_returns_graphml_writer(self):
        from crategraph.writers import get_writer

        assert get_writer("graphml") is GraphMLWriter


# ---------------------------------------------------------------------------
# 9. can_write checks
# ---------------------------------------------------------------------------


class TestCanWrite:
    def test_graphml_extension_true(self):
        assert GraphMLWriter().can_write("foo.graphml") is True

    def test_csv_extension_false(self):
        assert GraphMLWriter().can_write("foo.csv") is False

    def test_case_insensitive(self):
        assert GraphMLWriter().can_write("FOO.GRAPHML") is True

    def test_mixed_case(self):
        assert GraphMLWriter().can_write("Graph.GraphML") is True

    def test_no_extension_false(self):
        assert GraphMLWriter().can_write("graphml") is False
