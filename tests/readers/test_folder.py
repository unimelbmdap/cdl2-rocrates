"""Tests for crategraph.readers.folder — SimpleFolderReader."""

from __future__ import annotations

from pathlib import Path

from crategraph.readers.folder import SimpleFolderReader

FIXTURES = Path(__file__).parent.parent / "fixtures"
SIMPLE = FIXTURES / "simple-folder"
MINIMAL_CRATE = FIXTURES / "minimal-crate"


class TestCanRead:
    def test_plain_directory(self):
        reader = SimpleFolderReader()
        assert reader.can_read(str(SIMPLE))

    def test_file_path(self, tmp_path: Path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        reader = SimpleFolderReader()
        assert not reader.can_read(str(f))

    def test_nonexistent_path(self, tmp_path: Path):
        reader = SimpleFolderReader()
        assert not reader.can_read(str(tmp_path / "does-not-exist"))

    def test_defers_to_rocrate_reader(self):
        """Directories containing ro-crate-metadata.json are claimed by
        ROCrateReader; SimpleFolderReader must decline so a Corpus with
        both readers routes authored crates correctly."""
        reader = SimpleFolderReader()
        assert not reader.can_read(str(MINIMAL_CRATE))


class TestRootEntity:
    def test_returns_graph(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        from crategraph.core.graph import Graph

        assert isinstance(g, Graph)

    def test_root_entity_exists(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        assert "./" in g._entities

    def test_root_entity_shape(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        root = g._entities["./"]
        assert root.types == ("Dataset",)
        assert root.properties["name"] == "simple-folder"
        assert root.properties["_is_root"] is True
        assert root.source == str(SIMPLE.resolve())

    def test_graph_source_is_absolute_resolved_path(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        assert g.source == str(SIMPLE.resolve())

    def test_metadata_root_id(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        assert g.metadata["_root_id"] == "./"

    def test_metadata_name(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        assert g.metadata["name"] == "simple-folder"


class TestReadBasicTree:
    """Default skip_hidden=True — hidden entries excluded."""

    def _load(self):
        return SimpleFolderReader().read(str(SIMPLE))

    def test_entity_count(self):
        g = self._load()
        # 1 root + 3 Dataset subdirs (data/, data/raw/, empty/)
        # + 4 Files (notes.md, data/survey.csv,
        #   data/raw/readings.txt, data/raw/NOTES)
        # = 8
        assert len(g._entities) == 8

    def test_subdir_entity_ids_have_trailing_slash(self):
        g = self._load()
        assert "data/" in g._entities
        assert "data/raw/" in g._entities
        assert "empty/" in g._entities

    def test_file_entity_ids_have_no_trailing_slash(self):
        g = self._load()
        assert "notes.md" in g._entities
        assert "data/survey.csv" in g._entities
        assert "data/raw/readings.txt" in g._entities
        assert "data/raw/NOTES" in g._entities

    def test_subdir_is_dataset(self):
        g = self._load()
        assert g._entities["data/"].types == ("Dataset",)
        assert g._entities["data/"].properties["name"] == "data"

    def test_file_is_file_type(self):
        g = self._load()
        assert g._entities["notes.md"].types == ("File",)

    def test_file_content_size_matches_stat(self):
        g = self._load()
        expected = (SIMPLE / "data" / "survey.csv").stat().st_size
        assert g._entities["data/survey.csv"].properties["contentSize"] == expected

    def test_file_encoding_format_known_extension(self):
        g = self._load()
        assert g._entities["data/survey.csv"].properties["encodingFormat"] == "text/csv"

    def test_file_encoding_format_omitted_when_unknown(self):
        g = self._load()
        # NOTES has no extension -> mimetypes.guess_type returns (None, None).
        assert "encodingFormat" not in g._entities["data/raw/NOTES"].properties

    def test_hidden_excluded_by_default(self):
        g = self._load()
        assert ".hidden_file" not in g._entities
        assert ".hidden_dir/" not in g._entities
        assert ".hidden_dir/secret.txt" not in g._entities


class TestHasPartEdges:
    def _load(self):
        return SimpleFolderReader().read(str(SIMPLE))

    def test_every_edge_is_haspart(self):
        g = self._load()
        assert all(r.type == "hasPart" for r in g._relationships)

    def test_edge_count_equals_non_root_entity_count(self):
        g = self._load()
        non_root = [e for e in g._entities.values() if not e.properties.get("_is_root")]
        assert len(g._relationships) == len(non_root)

    def test_root_outgoing_edges(self):
        g = self._load()
        out = {r.target for r in g._relationships if r.source == "./"}
        assert out == {"notes.md", "data/", "empty/"}

    def test_data_subdir_outgoing_edges(self):
        g = self._load()
        out = {r.target for r in g._relationships if r.source == "data/"}
        assert out == {"data/survey.csv", "data/raw/"}

    def test_raw_subdir_outgoing_edges(self):
        g = self._load()
        out = {r.target for r in g._relationships if r.source == "data/raw/"}
        assert out == {"data/raw/readings.txt", "data/raw/NOTES"}

    def test_empty_subdir_has_no_outgoing(self):
        g = self._load()
        out = [r for r in g._relationships if r.source == "empty/"]
        assert out == []

    def test_relationships_have_null_id(self):
        g = self._load()
        assert all(r.id is None for r in g._relationships)
