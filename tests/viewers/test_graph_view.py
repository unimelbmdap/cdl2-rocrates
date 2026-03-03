"""Tests for Graph.view() integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate
from crategraph.core.models import ViewInfo

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


@pytest.fixture
def crate():
    return Crate(str(FIXTURES))


class TestGraphView:
    def test_view_png_by_entity(self, crate):
        entity = crate.get("sample.png")
        info = crate.view(entity)
        assert isinstance(info, ViewInfo)
        assert "<img" in info.html
        assert "data:image/png;base64," in info.html
        assert info.media_type == "image/png"

    def test_view_by_entity_id_string(self, crate):
        info = crate.view("sample.csv")
        assert isinstance(info, ViewInfo)
        assert "<table" in info.html
        assert "Alice" in info.html
        assert info.media_type == "text/csv"

    def test_view_txt(self, crate):
        info = crate.view("sample.txt")
        assert isinstance(info, ViewInfo)
        assert "<pre" in info.html
        assert info.media_type == "text/plain"

    def test_view_pdf(self, crate):
        info = crate.view("sample.pdf")
        assert isinstance(info, ViewInfo)
        assert info.media_type == "application/pdf"

    def test_view_contextual_entity_raises(self, crate):
        with pytest.raises(ValueError, match="contextual entity"):
            crate.view("#alice")

    def test_view_missing_file_raises(self, crate):
        from crategraph.core.models import Entity

        fake = Entity(
            id="missing.txt",
            types=["File"],
            properties={"encodingFormat": "text/plain"},
            source=str(FIXTURES),
        )
        crate._add_node(fake)
        with pytest.raises(FileNotFoundError, match="Cannot find file"):
            crate.view("missing.txt")

    def test_view_nonexistent_entity_raises(self, crate):
        with pytest.raises(KeyError):
            crate.view("no-such-entity")

    def test_view_url_entity_raises(self, crate):
        from crategraph.core.models import Entity

        url_entity = Entity(
            id="https://example.com/resource",
            types=["Dataset"],
            properties={},
            source=str(FIXTURES),
        )
        crate._add_node(url_entity)
        with pytest.raises(ValueError, match="contextual entity"):
            crate.view("https://example.com/resource")

    def test_view_root_dataset_raises(self, crate):
        with pytest.raises(ValueError, match="contextual entity"):
            crate.view("./")

    def test_view_unsupported_format_raises(self, crate):
        import unittest.mock

        with (
            unittest.mock.patch("crategraph.viewers.find_viewer", return_value=None),
            pytest.raises(ValueError, match="format not supported"),
        ):
            crate.view("sample.txt")


class TestMultiCrateView:
    def test_view_in_multi_crate(self):
        """Prefixed IDs use raw_id for path resolution."""
        second = Path(__file__).parent.parent / "fixtures" / "second-crate"
        crate = Crate(str(FIXTURES), str(second))
        file_entities = [e for e in crate.entities if "File" in e.types and "sample.txt" in e.id]
        if not file_entities:
            pytest.skip("No sample.txt File entity in multi-crate fixture")
        entity = file_entities[0]
        info = crate.view(entity)
        assert isinstance(info, ViewInfo)
        assert info.size_bytes > 0
