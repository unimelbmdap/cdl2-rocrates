"""Tests for crategraph.readers.ohrm_csv — OHRMCsvReader."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph.readers.ohrm_csv import OHRMCsvReader

EMEL_DIR = Path(__file__).parent.parent.parent / "data" / "EMEL_CSVs"
_has_emel = EMEL_DIR.exists()


class TestOHRMCsvReaderConfig:
    """Unit tests — no real data needed."""

    def test_is_csv_graph_reader(self):
        from crategraph.readers.csv import CsvGraphReader

        reader = OHRMCsvReader()
        assert isinstance(reader, CsvGraphReader)

    def test_has_six_node_tables(self):
        reader = OHRMCsvReader()
        assert len(reader._node_tables) == 6

    def test_has_six_edge_tables(self):
        reader = OHRMCsvReader()
        assert len(reader._edge_tables) == 6

    def test_has_two_linked_metadata_tables(self):
        reader = OHRMCsvReader()
        assert len(reader._linked_metadata_tables) == 2

    def test_has_one_file_entity_table(self):
        reader = OHRMCsvReader()
        assert len(reader._file_entity_tables) == 1

    def test_entity_table_uses_type_col(self):
        reader = OHRMCsvReader()
        entity_def = next(nd for nd in reader._node_tables if nd.table_name == "ENTITY")
        assert entity_def.type_col == "ETYPE"

    def test_can_read_emel(self):
        if not _has_emel:
            pytest.skip("EMEL CSVs not available")
        reader = OHRMCsvReader()
        assert reader.can_read(str(EMEL_DIR))


@pytest.mark.skipif(not _has_emel, reason="EMEL CSVs not available")
class TestOHRMCsvReaderIntegration:
    """Integration tests — require data/EMEL_CSVs."""

    @pytest.fixture()
    def graph(self):
        reader = OHRMCsvReader()
        return reader.read(str(EMEL_DIR))

    def test_loads_entities(self, graph):
        assert len(graph) > 100

    def test_has_relationships(self, graph):
        assert len(graph.relationships) > 50

    def test_has_person_type(self, graph):
        assert "Person" in graph.types

    def test_has_archival_resource_type(self, graph):
        assert "ArchivalResource" in graph.types

    def test_has_published_resource_type(self, graph):
        assert "PublishedResource" in graph.types

    def test_has_function_type(self, graph):
        assert "Function" in graph.types

    def test_entity_has_source_table(self, graph):
        people = graph.select(entity_types=["Person"])
        entity = people.entities[0]
        assert entity.properties["source_table"] == "ENTITY"

    def test_entitynames_nested(self, graph):
        entities_with_names = [e for e in graph.entities if "entitynames" in e.properties]
        assert len(entities_with_names) > 0
        record = entities_with_names[0].properties["entitynames"][0]
        assert "ENALTERNATE" in record or "ENALTERNATETYPE" in record

    def test_file_entities_created(self, graph):
        files = [e for e in graph.entities if "File" in e.types]
        assert len(files) > 0

    def test_file_relationships_created(self, graph):
        file_rels = [r for r in graph.relationships if r.type == "hasFile"]
        assert len(file_rels) > 0

    def test_diverse_relationship_types(self, graph):
        assert len(graph.relationship_types) > 3
