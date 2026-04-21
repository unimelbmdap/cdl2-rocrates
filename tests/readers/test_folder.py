"""Tests for crategraph.readers.folder — SimpleFolderReader."""

from __future__ import annotations

import os
import warnings as _warnings
from pathlib import Path

import pytest

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


class TestSkipHidden:
    def test_include_hidden_entries(self):
        g = SimpleFolderReader(skip_hidden=False).read(str(SIMPLE))
        assert ".hidden_file" in g._entities
        assert ".hidden_dir/" in g._entities
        assert ".hidden_dir/secret.txt" in g._entities

    def test_include_hidden_entity_count(self):
        g = SimpleFolderReader(skip_hidden=False).read(str(SIMPLE))
        # Default tree (8) + .hidden_file + .hidden_dir/ +
        # .hidden_dir/secret.txt + empty/.gitkeep = 12.
        assert len(g._entities) == 12

    def test_default_remains_skip_hidden_true(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        assert ".hidden_file" not in g._entities


def _make_symlink_or_skip(src: Path, dst: Path) -> None:
    """Create a symlink or skip the test on OSes that forbid it."""
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not supported in this environment: {exc}")


class TestSkipSymlinks:
    def _build_tree(self, tmp_path: Path) -> Path:
        root = tmp_path / "tree"
        root.mkdir()
        (root / "real_file.txt").write_text("content")
        real_subdir = root / "real_subdir"
        real_subdir.mkdir()
        (real_subdir / "inner.txt").write_text("inner")
        return root

    def test_symlinked_file_is_skipped(self, tmp_path: Path):
        root = self._build_tree(tmp_path)
        _make_symlink_or_skip(root / "real_file.txt", root / "link_to_file")
        g = SimpleFolderReader().read(str(root))
        assert "link_to_file" not in g._entities
        assert "real_file.txt" in g._entities

    def test_symlinked_directory_is_skipped(self, tmp_path: Path):
        root = self._build_tree(tmp_path)
        _make_symlink_or_skip(root / "real_subdir", root / "link_to_dir")
        g = SimpleFolderReader().read(str(root))
        assert "link_to_dir/" not in g._entities
        # The real dir and its contents are still present.
        assert "real_subdir/" in g._entities
        assert "real_subdir/inner.txt" in g._entities

    def test_symlink_outside_root_is_skipped(self, tmp_path: Path):
        root = self._build_tree(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("not mine")
        _make_symlink_or_skip(outside, root / "link_out")
        g = SimpleFolderReader().read(str(root))
        assert "link_out" not in g._entities

    def test_symlink_filtering_is_silent(self, tmp_path: Path):
        root = self._build_tree(tmp_path)
        _make_symlink_or_skip(root / "real_file.txt", root / "link_to_file")
        with _warnings.catch_warnings(record=True) as recorded:
            _warnings.simplefilter("always")
            SimpleFolderReader().read(str(root))
        symlink_warnings = [w for w in recorded if "link_to_file" in str(w.message)]
        assert symlink_warnings == []


class TestDeterministicOrder:
    def test_entity_order_is_stable(self):
        ids1 = list(SimpleFolderReader().read(str(SIMPLE))._entities.keys())
        ids2 = list(SimpleFolderReader().read(str(SIMPLE))._entities.keys())
        assert ids1 == ids2

    def test_relationship_order_is_stable(self):
        rels1 = [
            (r.source, r.target, r.type)
            for r in SimpleFolderReader().read(str(SIMPLE))._relationships
        ]
        rels2 = [
            (r.source, r.target, r.type)
            for r in SimpleFolderReader().read(str(SIMPLE))._relationships
        ]
        assert rels1 == rels2

    def test_entities_are_alphabetically_ordered_within_parent(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        root_children = [r.target for r in g._relationships if r.source == "./"]
        assert root_children == sorted(root_children)


class TestIntegrationContract:
    def test_graph_source_is_absolute_resolved(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        assert g.source == str(SIMPLE.resolve())

    def test_every_entity_source_matches_graph_source(self):
        g = SimpleFolderReader().read(str(SIMPLE))
        for entity in g._entities.values():
            assert entity.source == g.source

    def test_resolve_entity_path_for_file(self):
        from crategraph.core._files import resolve_entity_path

        g = SimpleFolderReader().read(str(SIMPLE))
        csv_entity = g._entities["data/survey.csv"]
        resolved = resolve_entity_path(csv_entity, fallback_source=g.source)
        assert resolved is not None
        assert resolved == (SIMPLE / "data" / "survey.csv").resolve()
        assert resolved.is_file()

    def test_resolve_entity_path_for_root_is_none(self):
        from crategraph.core._files import resolve_entity_path

        g = SimpleFolderReader().read(str(SIMPLE))
        root = g._entities["./"]
        assert resolve_entity_path(root, fallback_source=g.source) is None

    def test_graph_view_on_csv_returns_viewinfo(self):
        from crategraph.core.models import ViewInfo

        g = SimpleFolderReader().read(str(SIMPLE))
        info = g.view("data/survey.csv")
        assert isinstance(info, ViewInfo)
        assert info.media_type == "text/csv"
        assert "<table" in info.html


class TestErrorHandling:
    def test_nonexistent_path_raises(self, tmp_path: Path):
        missing = tmp_path / "no-such-dir"
        with pytest.raises(FileNotFoundError):
            SimpleFolderReader().read(str(missing))

    def test_file_path_raises_not_a_directory(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        with pytest.raises(NotADirectoryError):
            SimpleFolderReader().read(str(f))

    def test_on_walk_error_emits_warning(self, tmp_path: Path, monkeypatch):
        """When Path.walk invokes its on_error callback, the reader
        should warn and skip the offending subtree rather than raise."""
        root = tmp_path / "tree"
        root.mkdir()
        (root / "ok.txt").write_text("readable")

        original_walk = Path.walk

        def fake_walk(self, *args, on_error=None, **kwargs):
            if on_error is not None:
                on_error(PermissionError("simulated permission denied"))
            yield from original_walk(self, *args, on_error=on_error, **kwargs)

        monkeypatch.setattr(Path, "walk", fake_walk)

        with pytest.warns(UserWarning, match="simulated permission denied"):
            g = SimpleFolderReader().read(str(root))

        # The readable file is still included — walk continues after the warning.
        assert "ok.txt" in g._entities

    def test_stat_oserror_emits_warning_and_skips_file(self, tmp_path: Path, monkeypatch):
        """If stat() fails for a file, the reader warns and continues."""
        root = tmp_path / "tree"
        root.mkdir()
        bad = root / "bad.txt"
        bad.write_text("x")
        (root / "good.txt").write_text("y")

        original_stat = Path.stat

        def fake_stat(self, *args, follow_symlinks: bool = True, **kwargs):
            # Only intercept the real stat() call (follow_symlinks=True).
            # is_symlink() uses lstat() which passes follow_symlinks=False —
            # let that through so the symlink filter operates correctly.
            if self.name == "bad.txt" and follow_symlinks:
                raise OSError("simulated stat failure")
            return original_stat(self, *args, follow_symlinks=follow_symlinks, **kwargs)

        monkeypatch.setattr(Path, "stat", fake_stat)

        with pytest.warns(UserWarning, match="simulated stat failure"):
            g = SimpleFolderReader().read(str(root))

        assert "bad.txt" not in g._entities
        assert "good.txt" in g._entities
