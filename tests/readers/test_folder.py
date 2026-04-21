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
