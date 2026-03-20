"""Tests for crategraph.readers.ohrm_sql — OHRMSqlReader."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph.readers.ohrm_sql import OHRMSqlReader

# Point at a known OHRM crate with SQL data.
AABR_SQL_DIR = (
    Path(__file__).parent.parent.parent
    / "data"
    / "ohrm"
    / "AABR-ro-crate"
    / "ohrm"
    / "web"
    / "sql"
)
_has_aabr = AABR_SQL_DIR.exists()


class TestOHRMSqlReaderConfig:
    """Unit tests — no real data needed."""

    def test_is_sql_graph_reader(self):
        from crategraph.readers.shared.sql_loader import SqlGraphReader

        reader = OHRMSqlReader()
        assert isinstance(reader, SqlGraphReader)

    def test_has_six_node_tables(self):
        reader = OHRMSqlReader()
        assert len(reader._node_tables) == 6

    def test_has_six_edge_tables(self):
        reader = OHRMSqlReader()
        assert len(reader._edge_tables) == 6

    def test_has_two_linked_metadata_tables(self):
        reader = OHRMSqlReader()
        assert len(reader._linked_metadata_tables) == 2

    def test_has_one_file_entity_table(self):
        reader = OHRMSqlReader()
        assert len(reader._file_entity_tables) == 1

    def test_entity_table_uses_type_col(self):
        reader = OHRMSqlReader()
        entity_def = reader._node_tables[0]
        assert entity_def.table_name == "ENTITY"
        assert entity_def.type_col == "ETYPE"

    @pytest.mark.skipif(not _has_aabr, reason="AABR SQL data not available")
    def test_can_read_aabr(self):
        reader = OHRMSqlReader()
        assert reader.can_read(str(AABR_SQL_DIR))


@pytest.mark.skipif(not _has_aabr, reason="AABR SQL data not available")
class TestOHRMSqlReaderIntegration:
    """Integration tests — require AABR OHRM SQL dump."""

    @pytest.fixture(scope="class")
    def graph(self):
        reader = OHRMSqlReader()
        return reader.read(str(AABR_SQL_DIR))

    def test_loads_entities(self, graph):
        assert len(graph.entities) > 50

    def test_has_relationships(self, graph):
        assert len(graph.relationships) > 20

    def test_has_person_type(self, graph):
        types = {t for e in graph.entities for t in e.types}
        assert "Person" in types

    def test_has_institution_type(self, graph):
        types = {t for e in graph.entities for t in e.types}
        assert "Institution" in types

    def test_has_published_resource_type(self, graph):
        types = {t for e in graph.entities for t in e.types}
        assert "PublishedResource" in types

    def test_entity_has_source_table(self, graph):
        entity = graph.entities[0]
        assert "source_table" in entity.properties
