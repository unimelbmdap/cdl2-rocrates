"""Tests for crategraph.readers.csv — CsvGraphReader."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph.readers.shared.csv_loader import CsvGraphReader
from crategraph.readers.shared.tabular import (
    EdgeDef,
    FileEntityDef,
    LinkedMetadataDef,
    NodeDef,
    _clean_str,
    _split_etype,
)

# --- Helper function tests ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.0, "1"),
        (1, "1"),
        ("hello", "hello"),
        (3.14, "3.14"),
        ("  spaced  ", "spaced"),
        (float("inf"), "inf"),
        (float("nan"), "nan"),
    ],
)
def test_clean_str(value, expected):
    assert _clean_str(value) == expected


@pytest.mark.parametrize(
    ("input_str", "expected"),
    [
        ("Person - Businessperson", ["Person", "Businessperson"]),
        ("Person-Organisation", ["Person", "Organisation"]),
        ("Corporate Body", ["Corporate_Body"]),
        ("Person", ["Person"]),
        ("", ["Unknown"]),
        ("  -  -  ", ["Unknown"]),
    ],
)
def test_split_etype(input_str, expected):
    assert _split_etype(input_str) == expected


# --- Dataclass tests ---


class TestNodeDef:
    def test_basic_creation(self):
        nd = NodeDef(table_name="People", id_col="PersonID")
        assert nd.table_name == "People"
        assert nd.id_col == "PersonID"
        assert nd.fixed_types is None
        assert nd.type_col is None

    def test_with_fixed_types(self):
        nd = NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])
        assert nd.fixed_types == ["Person"]

    def test_with_type_col(self):
        nd = NodeDef(table_name="Entities", id_col="EID", type_col="EntityType")
        assert nd.type_col == "EntityType"

    def test_frozen(self):
        nd = NodeDef(table_name="People", id_col="PersonID")
        with pytest.raises(AttributeError):
            nd.table_name = "Other"


class TestEdgeDef:
    def test_basic_creation(self):
        ed = EdgeDef(table_name="Links", source_col="SrcID", target_col="TgtID")
        assert ed.table_name == "Links"
        assert ed.source_col == "SrcID"
        assert ed.target_col == "TgtID"
        assert ed.type_col is None

    def test_with_type_col(self):
        ed = EdgeDef(
            table_name="Links", source_col="SrcID", target_col="TgtID", type_col="LinkType"
        )
        assert ed.type_col == "LinkType"

    def test_frozen(self):
        ed = EdgeDef(table_name="Links", source_col="SrcID", target_col="TgtID")
        with pytest.raises(AttributeError):
            ed.table_name = "Other"


# --- can_read tests ---


class TestCanRead:
    def test_directory_with_matching_csv(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        reader = CsvGraphReader(node_tables=[NodeDef(table_name="People", id_col="PersonID")])
        assert reader.can_read(str(tmp_path))

    def test_directory_without_matching_csv(self, tmp_path: Path):
        (tmp_path / "Unrelated.csv").write_text("X,Y\n1,2\n")
        reader = CsvGraphReader(node_tables=[NodeDef(table_name="People", id_col="PersonID")])
        assert not reader.can_read(str(tmp_path))

    def test_nonexistent_path(self):
        reader = CsvGraphReader(node_tables=[NodeDef(table_name="People", id_col="PersonID")])
        assert not reader.can_read("/nonexistent/path")

    def test_case_insensitive(self, tmp_path: Path):
        (tmp_path / "people.csv").write_text("PersonID,Name\n1,Alice\n")
        reader = CsvGraphReader(node_tables=[NodeDef(table_name="People", id_col="PersonID")])
        assert reader.can_read(str(tmp_path))

    def test_nested_subdirectory(self, tmp_path: Path):
        sub = tmp_path / "data" / "tables"
        sub.mkdir(parents=True)
        (sub / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        reader = CsvGraphReader(node_tables=[NodeDef(table_name="People", id_col="PersonID")])
        assert reader.can_read(str(tmp_path))

    def test_file_path_returns_false(self, tmp_path: Path):
        csv_file = tmp_path / "People.csv"
        csv_file.write_text("PersonID,Name\n1,Alice\n")
        reader = CsvGraphReader(node_tables=[NodeDef(table_name="People", id_col="PersonID")])
        assert not reader.can_read(str(csv_file))

    def test_no_tables_configured(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        reader = CsvGraphReader()
        assert not reader.can_read(str(tmp_path))


# --- read() node loading tests ---


class TestReadNodes:
    def _make_reader(self, **kwargs):
        return CsvGraphReader(**kwargs)

    def test_loads_nodes_from_csv(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n2,Bob\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])]
        )
        graph = reader.read(str(tmp_path))
        assert len(graph) == 2

    def test_entity_has_fixed_types(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])]
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert entity.types == ["Person"]

    def test_entity_has_properties(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name,Age\n1,Alice,30\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])]
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert entity.properties["Name"] == "Alice"
        assert entity.properties["Age"] == 30

    def test_nan_values_dropped_from_properties(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name,Email\n1,Alice,\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])]
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert "Email" not in entity.properties

    def test_rows_with_nan_id_skipped(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n,Bob\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])]
        )
        graph = reader.read(str(tmp_path))
        assert len(graph) == 1

    def test_source_table_stored_in_properties(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])]
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert entity.properties["source_table"] == "People"

    def test_type_col_splits_on_dash(self, tmp_path: Path):
        (tmp_path / "Entities.csv").write_text("EID,EType\n1,Person-Organisation\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="Entities", id_col="EID", type_col="EType")]
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert entity.types == ["Person", "Organisation"]

    def test_type_col_replaces_spaces_with_underscores(self, tmp_path: Path):
        (tmp_path / "Entities.csv").write_text("EID,EType\n1,Published Resource\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="Entities", id_col="EID", type_col="EType")]
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert entity.types == ["Published_Resource"]

    def test_empty_type_col_becomes_unknown(self, tmp_path: Path):
        (tmp_path / "Entities.csv").write_text("EID,EType\n1,\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="Entities", id_col="EID", type_col="EType")]
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert entity.types == ["Unknown"]

    def test_type_col_excluded_from_properties(self, tmp_path: Path):
        (tmp_path / "Entities.csv").write_text("EID,EType,Name\n1,Person,Alice\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="Entities", id_col="EID", type_col="EType")]
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert "EType" not in entity.properties
        assert entity.properties["Name"] == "Alice"

    def test_multiple_node_tables(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Orgs.csv").write_text("OrgID,OrgName\nA,ACME\n")
        reader = self._make_reader(
            node_tables=[
                NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"]),
                NodeDef(table_name="Orgs", id_col="OrgID", fixed_types=["Organisation"]),
            ]
        )
        graph = reader.read(str(tmp_path))
        assert len(graph) == 2
        assert graph.get("1").types == ["Person"]
        assert graph.get("A").types == ["Organisation"]

    def test_missing_csv_warns(self, tmp_path: Path):
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="Missing", id_col="ID", fixed_types=["Thing"])]
        )
        with pytest.warns(UserWarning, match="not found"):
            graph = reader.read(str(tmp_path))
        assert len(graph) == 0

    def test_csv_in_subdirectory(self, tmp_path: Path):
        sub = tmp_path / "data"
        sub.mkdir()
        (sub / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])]
        )
        graph = reader.read(str(tmp_path))
        assert len(graph) == 1


# --- read() edge loading tests ---


class TestReadEdges:
    def _make_reader(self, **kwargs):
        return CsvGraphReader(**kwargs)

    def _write_nodes_and_edges(self, tmp_path: Path, *, edge_csv: str):
        """Write a standard People node CSV and a custom edge CSV."""
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n2,Bob\n")
        (tmp_path / "Links.csv").write_text(edge_csv)

    def test_loads_edges(self, tmp_path: Path):
        self._write_nodes_and_edges(tmp_path, edge_csv="SrcID,TgtID\n1,2\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            edge_tables=[EdgeDef(table_name="Links", source_col="SrcID", target_col="TgtID")],
        )
        graph = reader.read(str(tmp_path))
        assert len(graph.relationships) == 1

    def test_edge_source_and_target(self, tmp_path: Path):
        self._write_nodes_and_edges(tmp_path, edge_csv="SrcID,TgtID\n1,2\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            edge_tables=[EdgeDef(table_name="Links", source_col="SrcID", target_col="TgtID")],
        )
        graph = reader.read(str(tmp_path))
        rel = graph.relationships[0]
        assert rel.source == "1"
        assert rel.target == "2"

    def test_edge_type_defaults_to_table_name(self, tmp_path: Path):
        self._write_nodes_and_edges(tmp_path, edge_csv="SrcID,TgtID\n1,2\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            edge_tables=[EdgeDef(table_name="Links", source_col="SrcID", target_col="TgtID")],
        )
        graph = reader.read(str(tmp_path))
        assert graph.relationships[0].type == "Links"

    def test_edge_type_from_type_col(self, tmp_path: Path):
        self._write_nodes_and_edges(tmp_path, edge_csv="SrcID,TgtID,LinkType\n1,2,worksFor\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            edge_tables=[
                EdgeDef(
                    table_name="Links",
                    source_col="SrcID",
                    target_col="TgtID",
                    type_col="LinkType",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        assert graph.relationships[0].type == "worksFor"

    def test_edge_type_col_empty_falls_back(self, tmp_path: Path):
        self._write_nodes_and_edges(tmp_path, edge_csv="SrcID,TgtID,LinkType\n1,2,\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            edge_tables=[
                EdgeDef(
                    table_name="Links",
                    source_col="SrcID",
                    target_col="TgtID",
                    type_col="LinkType",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        assert graph.relationships[0].type == "Links"

    def test_edge_properties_preserved(self, tmp_path: Path):
        self._write_nodes_and_edges(tmp_path, edge_csv="SrcID,TgtID,Weight\n1,2,5\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            edge_tables=[EdgeDef(table_name="Links", source_col="SrcID", target_col="TgtID")],
        )
        graph = reader.read(str(tmp_path))
        rel = graph.relationships[0]
        assert rel.properties["Weight"] == 5
        assert rel.properties["source_table"] == "Links"

    def test_edge_type_col_excluded_from_properties(self, tmp_path: Path):
        self._write_nodes_and_edges(tmp_path, edge_csv="SrcID,TgtID,LinkType\n1,2,worksFor\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            edge_tables=[
                EdgeDef(
                    table_name="Links",
                    source_col="SrcID",
                    target_col="TgtID",
                    type_col="LinkType",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        rel = graph.relationships[0]
        assert "LinkType" not in rel.properties

    def test_rows_with_nan_source_or_target_skipped(self, tmp_path: Path):
        self._write_nodes_and_edges(tmp_path, edge_csv="SrcID,TgtID\n1,2\n,2\n1,\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            edge_tables=[EdgeDef(table_name="Links", source_col="SrcID", target_col="TgtID")],
        )
        graph = reader.read(str(tmp_path))
        assert len(graph.relationships) == 1


# --- read() linked metadata tests ---


class TestReadLinkedMetadata:
    def _make_reader(self, **kwargs):
        return CsvGraphReader(**kwargs)

    def test_metadata_nested_on_parent(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Aliases.csv").write_text(
            "PersonID,AliasName,AliasType\n1,A. Smith,formal\n1,Ali,informal\n"
        )
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            linked_metadata_tables=[
                LinkedMetadataDef(
                    table_name="Aliases", parent_id_col="PersonID", property_name="aliases"
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert "aliases" in entity.properties
        aliases = entity.properties["aliases"]
        assert len(aliases) == 2
        assert aliases[0]["AliasName"] == "A. Smith"
        assert aliases[1]["AliasName"] == "Ali"

    def test_metadata_excludes_parent_id_col(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Aliases.csv").write_text("PersonID,AliasName\n1,Ali\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            linked_metadata_tables=[
                LinkedMetadataDef(
                    table_name="Aliases", parent_id_col="PersonID", property_name="aliases"
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        aliases = graph.get("1").properties["aliases"]
        assert "PersonID" not in aliases[0]

    def test_metadata_nan_values_dropped(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Aliases.csv").write_text("PersonID,AliasName,Note\n1,Ali,\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            linked_metadata_tables=[
                LinkedMetadataDef(
                    table_name="Aliases", parent_id_col="PersonID", property_name="aliases"
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        aliases = graph.get("1").properties["aliases"]
        assert "Note" not in aliases[0]

    def test_metadata_no_matching_parent_silently_skipped(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Aliases.csv").write_text("PersonID,AliasName\n999,Ghost\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            linked_metadata_tables=[
                LinkedMetadataDef(
                    table_name="Aliases", parent_id_col="PersonID", property_name="aliases"
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert "aliases" not in entity.properties

    def test_entity_without_metadata_unchanged(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n2,Bob\n")
        (tmp_path / "Aliases.csv").write_text("PersonID,AliasName\n1,Ali\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            linked_metadata_tables=[
                LinkedMetadataDef(
                    table_name="Aliases", parent_id_col="PersonID", property_name="aliases"
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        bob = graph.get("2")
        assert "aliases" not in bob.properties
        assert bob.properties["Name"] == "Bob"


# --- read() file entity tests ---


class TestReadFileEntities:
    def _make_reader(self, **kwargs):
        return CsvGraphReader(**kwargs)

    def test_file_entity_created(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Docs.csv").write_text("PersonID,FilePath,Version\n1,docs/report.pdf,1\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            file_entity_tables=[
                FileEntityDef(
                    table_name="Docs",
                    parent_id_col="PersonID",
                    file_path_col="FilePath",
                    relationship_type="hasDocument",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        file_entity = graph.get("docs/report.pdf")
        assert file_entity is not None

    def test_file_entity_has_file_type(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Docs.csv").write_text("PersonID,FilePath\n1,docs/report.pdf\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            file_entity_tables=[
                FileEntityDef(
                    table_name="Docs",
                    parent_id_col="PersonID",
                    file_path_col="FilePath",
                    relationship_type="hasDocument",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        file_entity = graph.get("docs/report.pdf")
        assert file_entity.types == ["File"]

    def test_file_entity_has_source_table(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Docs.csv").write_text("PersonID,FilePath\n1,docs/report.pdf\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            file_entity_tables=[
                FileEntityDef(
                    table_name="Docs",
                    parent_id_col="PersonID",
                    file_path_col="FilePath",
                    relationship_type="hasDocument",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        file_entity = graph.get("docs/report.pdf")
        assert file_entity.properties["source_table"] == "Docs"

    def test_file_entity_relationship_created(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Docs.csv").write_text("PersonID,FilePath\n1,docs/report.pdf\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            file_entity_tables=[
                FileEntityDef(
                    table_name="Docs",
                    parent_id_col="PersonID",
                    file_path_col="FilePath",
                    relationship_type="hasDocument",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        rels = [r for r in graph.relationships if r.type == "hasDocument"]
        assert len(rels) == 1
        assert rels[0].source == "1"
        assert rels[0].target == "docs/report.pdf"

    def test_multiple_versions_per_parent(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Docs.csv").write_text(
            "PersonID,FilePath,Version\n1,docs/v1.pdf,1\n1,docs/v2.pdf,2\n"
        )
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            file_entity_tables=[
                FileEntityDef(
                    table_name="Docs",
                    parent_id_col="PersonID",
                    file_path_col="FilePath",
                    relationship_type="hasDocument",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        rels = [r for r in graph.relationships if r.type == "hasDocument"]
        assert len(rels) == 2
        # Both file entities exist.
        assert graph.get("docs/v1.pdf") is not None
        assert graph.get("docs/v2.pdf") is not None

    def test_file_entity_properties_preserved(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Docs.csv").write_text(
            "PersonID,FilePath,Version,MimeType\n1,docs/report.pdf,3,application/pdf\n"
        )
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            file_entity_tables=[
                FileEntityDef(
                    table_name="Docs",
                    parent_id_col="PersonID",
                    file_path_col="FilePath",
                    relationship_type="hasDocument",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        file_entity = graph.get("docs/report.pdf")
        assert file_entity.properties["Version"] == 3
        assert file_entity.properties["MimeType"] == "application/pdf"
        # parent_id_col and file_path_col should be excluded.
        assert "PersonID" not in file_entity.properties
        assert "FilePath" not in file_entity.properties

    def test_row_with_nan_filepath_skipped(self, tmp_path: Path):
        (tmp_path / "People.csv").write_text("PersonID,Name\n1,Alice\n")
        (tmp_path / "Docs.csv").write_text("PersonID,FilePath\n1,docs/report.pdf\n1,\n")
        reader = self._make_reader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
            file_entity_tables=[
                FileEntityDef(
                    table_name="Docs",
                    parent_id_col="PersonID",
                    file_path_col="FilePath",
                    relationship_type="hasDocument",
                )
            ],
        )
        graph = reader.read(str(tmp_path))
        # Only one file entity and one relationship should be created.
        file_entities = [e for e in graph.entities if e.types == ["File"]]
        assert len(file_entities) == 1
        rels = [r for r in graph.relationships if r.type == "hasDocument"]
        assert len(rels) == 1


# --- Encoding fallback tests ---


class TestEncodingFallback:
    def test_latin1_csv_loads_with_fallback(self, tmp_path: Path):
        csv_content = "PersonID,Name\n1,Ren\xe9\n"
        (tmp_path / "People.csv").write_bytes(csv_content.encode("latin-1"))
        reader = CsvGraphReader(
            node_tables=[NodeDef(table_name="People", id_col="PersonID", fixed_types=["Person"])],
        )
        graph = reader.read(str(tmp_path))
        entity = graph.get("1")
        assert entity.properties["Name"] == "René"
