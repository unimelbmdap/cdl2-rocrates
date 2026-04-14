"""Tests for crategraph.writers.csv_writer.CsvWriter."""

from __future__ import annotations

import csv

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.writers._flatten import decode_pipe_list
from crategraph.writers.csv_writer import CsvWriter

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
# 1. Two files created
# ---------------------------------------------------------------------------


class TestFilesCreated:
    def test_nodes_and_edges_csv_exist(self, tmp_path):
        """Both nodes.csv and edges.csv are created after a successful write."""
        a = _entity("A", types=["Person"], properties={"name": "Alice"})
        b = _entity("B", types=["Person"], properties={"name": "Bob"})
        rel = _rel("A", "B", "knows")
        g = _make_graph(a, b, relationships=[rel])
        out = tmp_path / "output"
        g.write(str(out), format="csv")
        assert (out / "nodes.csv").exists()
        assert (out / "edges.csv").exists()


# ---------------------------------------------------------------------------
# 2. Deterministic node header order
# ---------------------------------------------------------------------------


class TestNodeHeaderOrder:
    def test_promoted_columns_first_then_alphabetical(self, tmp_path):
        """nodes.csv header: id, label, type, types first; then extra keys alphabetically."""
        a = _entity(
            "A",
            types=["Person"],
            properties={"name": "Alice", "zebra": 1, "apple": 2},
        )
        g = _make_graph(a)
        out = tmp_path / "output"
        CsvWriter().write(g, str(out))
        nodes_csv = out / "nodes.csv"
        with nodes_csv.open(encoding="utf-8", newline="") as f:
            header = f.readline().strip().split(",")
        promoted = ["id", "label", "type", "types"]
        assert header[: len(promoted)] == promoted
        extra_cols = header[len(promoted) :]
        assert extra_cols == sorted(extra_cols), "Extra columns should be alphabetical"


# ---------------------------------------------------------------------------
# 3. Edge header order
# ---------------------------------------------------------------------------


class TestEdgeHeaderOrder:
    def test_promoted_columns_first_then_alphabetical(self, tmp_path):
        """edges.csv header: source, target, type, rel_id first; then extra keys alphabetically."""
        a = _entity("A")
        b = _entity("B")
        rel = _rel("A", "B", "authored", properties={"year": 2020, "note": "first"})
        g = _make_graph(a, b, relationships=[rel])
        out = tmp_path / "output"
        CsvWriter().write(g, str(out))
        edges_csv = out / "edges.csv"
        with edges_csv.open(encoding="utf-8", newline="") as f:
            header = f.readline().strip().split(",")
        promoted = ["source", "target", "type", "rel_id"]
        assert header[: len(promoted)] == promoted
        extra_cols = header[len(promoted) :]
        assert extra_cols == sorted(extra_cols), "Extra columns should be alphabetical"


# ---------------------------------------------------------------------------
# 4. Cell contents round-trip
# ---------------------------------------------------------------------------


class TestCellContents:
    def test_scalar_and_list_properties_round_trip(self, tmp_path):
        """Known entity properties survive a write → DictReader round-trip."""
        a = _entity(
            "alice-001",
            types=["Person"],
            properties={"name": "Alice", "age": 30, "tags": ["a", "b"]},
        )
        g = _make_graph(a)
        out = tmp_path / "output"
        CsvWriter().write(g, str(out))
        with (out / "nodes.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 1
        row = rows[0]
        assert row["age"] == "30", "Integers are string-typed in CSV"
        assert row["name"] == "Alice"
        assert decode_pipe_list(row["tags"]) == ["a", "b"]
        assert row["id"] == "alice-001"


# ---------------------------------------------------------------------------
# 5. Non-empty directory without overwrite raises
# ---------------------------------------------------------------------------


class TestOverwriteGuard:
    def test_second_write_without_overwrite_raises(self, tmp_path):
        """A second call to an existing non-empty directory raises FileExistsError."""
        a = _entity("A")
        g = _make_graph(a)
        out = tmp_path / "output"
        CsvWriter().write(g, str(out))
        with pytest.raises(FileExistsError):
            CsvWriter().write(g, str(out))


# ---------------------------------------------------------------------------
# 6. overwrite=True replaces contents
# ---------------------------------------------------------------------------


class TestOverwriteTrue:
    def test_overwrite_true_replaces_contents(self, tmp_path):
        """With overwrite=True, the second write succeeds and reflects the new graph."""
        a = _entity("entity-original", types=["TypeA"])
        b = _entity("entity-replacement", types=["TypeB"])
        g1 = _make_graph(a)
        g2 = _make_graph(b)
        out = tmp_path / "output"
        CsvWriter().write(g1, str(out))
        CsvWriter().write(g2, str(out), overwrite=True)
        with (out / "nodes.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        ids = [r["id"] for r in rows]
        assert "entity-replacement" in ids
        assert "entity-original" not in ids


# ---------------------------------------------------------------------------
# 7. Non-directory path that exists raises
# ---------------------------------------------------------------------------


class TestNonDirectoryPathRaises:
    def test_existing_file_path_raises(self, tmp_path):
        """Writing to a path that exists as a plain file raises FileExistsError."""
        plain_file = tmp_path / "x.csv"
        plain_file.write_text("not a directory")
        g = _make_graph(_entity("A"))
        with pytest.raises(FileExistsError, match="not a directory"):
            CsvWriter().write(g, str(plain_file))


# ---------------------------------------------------------------------------
# 8. Empty edges.csv still has a header
# ---------------------------------------------------------------------------


class TestEmptyEdgesHeader:
    def test_zero_relationships_produces_header_only(self, tmp_path):
        """A Graph with no relationships still produces edges.csv with a header row."""
        a = _entity("A")
        g = _make_graph(a)
        out = tmp_path / "output"
        CsvWriter().write(g, str(out))
        edges_csv = out / "edges.csv"
        assert edges_csv.exists()
        with edges_csv.open(encoding="utf-8", newline="") as f:
            lines = [line for line in f if line.strip()]
        # Only the header line — no data rows.
        assert len(lines) == 1, f"Expected 1 header line, got {len(lines)}: {lines}"
        header = lines[0].strip().split(",")
        for col in ("source", "target", "type", "rel_id"):
            assert col in header, f"Promoted column {col!r} missing from edges.csv header"


# ---------------------------------------------------------------------------
# 9. Parallel same-type edges (CRITICAL)
# ---------------------------------------------------------------------------


class TestParallelSameTypeEdges:
    def test_parallel_edges_produce_two_rows(self, tmp_path):
        """Two same-type edges between the same pair produce two rows in edges.csv."""
        a = _entity("A")
        b = _entity("B")
        rel1 = _rel("A", "B", "author", properties={"year": 2001})
        rel2 = _rel("A", "B", "author", properties={"year": 2003})
        g = _make_graph(a, b, relationships=[rel1, rel2])
        out = tmp_path / "output"
        CsvWriter().write(g, str(out))
        with (out / "edges.csv").open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2, (
            f"Expected 2 edge rows but found {len(rows)}. "
            "The writer may be iterating graph._graph.edges instead of graph.relationships."
        )
        years = {r["year"] for r in rows}
        assert years == {"2001", "2003"}


# ---------------------------------------------------------------------------
# 10. Non-existent path is created
# ---------------------------------------------------------------------------


class TestDirectoryCreation:
    def test_nested_path_is_created(self, tmp_path):
        """Writing to a non-existent nested path creates the full directory tree."""
        a = _entity("A")
        g = _make_graph(a)
        out = tmp_path / "nested" / "deep" / "out"
        assert not out.exists()
        CsvWriter().write(g, str(out))
        assert out.is_dir()
        assert (out / "nodes.csv").exists()
        assert (out / "edges.csv").exists()


# ---------------------------------------------------------------------------
# 11. Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_get_writer_returns_csv_writer(self):
        """get_writer('csv') resolves to CsvWriter."""
        from crategraph.writers import get_writer

        assert get_writer("csv") is CsvWriter


# ---------------------------------------------------------------------------
# 12. can_write checks
# ---------------------------------------------------------------------------


class TestCanWrite:
    def test_trailing_slash_true(self):
        assert CsvWriter().can_write("foo/") is True

    def test_existing_directory_true(self, tmp_path):
        assert CsvWriter().can_write(str(tmp_path)) is True

    def test_graphml_extension_false(self):
        assert CsvWriter().can_write("foo.graphml") is False

    def test_csv_extension_false(self):
        """Single-file .csv naming does not imply directory semantics."""
        assert CsvWriter().can_write("foo.csv") is False
