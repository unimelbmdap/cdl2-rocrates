"""Tests for Graph.inspect() integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate
from crategraph.core.graph import Graph
from crategraph.core.models import Entity, FileInfo

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


@pytest.fixture
def crate():
    return Crate(str(FIXTURES))


class TestGraphInspect:
    def test_inspect_txt_by_entity(self, crate):
        entity = crate.get("sample.txt")
        info = crate.inspect(entity)
        assert isinstance(info, FileInfo)
        assert "sample text file" in info.content.lower()
        assert info.media_type == "text/plain"

    def test_inspect_by_entity_id_string(self, crate):
        info = crate.inspect("sample.csv")
        assert isinstance(info, FileInfo)
        assert "Alice" in info.content or "alice" in info.content.lower()
        assert info.media_type == "text/csv"

    def test_inspect_pdf(self, crate):
        info = crate.inspect("sample.pdf")
        assert isinstance(info, FileInfo)
        assert info.media_type == "application/pdf"

    def test_inspect_png(self, crate):
        info = crate.inspect("sample.png")
        assert isinstance(info, FileInfo)
        assert info.media_type == "image/png"

    def test_inspect_contextual_entity_raises(self, crate):
        with pytest.raises(ValueError, match="contextual entity"):
            crate.inspect("#alice")

    def test_inspect_missing_file_raises(self, crate):
        from crategraph.core.models import Entity

        fake = Entity(
            id="missing.txt",
            types=["File"],
            properties={"encodingFormat": "text/plain"},
            source=str(FIXTURES),
        )
        crate._add_node(fake)
        with pytest.raises(FileNotFoundError, match="Cannot find file"):
            crate.inspect("missing.txt")

    def test_inspect_nonexistent_entity_raises(self, crate):
        with pytest.raises(KeyError):
            crate.inspect("no-such-entity")

    def test_inspect_url_entity_raises(self, crate):
        from crategraph.core.models import Entity

        url_entity = Entity(
            id="https://example.com/resource",
            types=["Dataset"],
            properties={},
            source=str(FIXTURES),
        )
        crate._add_node(url_entity)
        with pytest.raises(ValueError, match="contextual entity"):
            crate.inspect("https://example.com/resource")

    def test_inspect_root_dataset_raises(self):
        crate = Crate(str(FIXTURES), include_root=True)
        with pytest.raises(ValueError, match="contextual entity"):
            crate.inspect("./")

    def test_inspect_unsupported_format_raises(self, crate):
        import unittest.mock

        with (
            unittest.mock.patch("crategraph.inspectors.find_inspector", return_value=None),
            pytest.raises(ValueError, match="format not supported"),
        ):
            crate.inspect("sample.txt")

    def test_inspect_uses_graph_source_fallback(self):
        graph = Graph(source=str(FIXTURES))
        graph._add_node(
            Entity(
                id="sample.txt",
                types=["File"],
                properties={"encodingFormat": "text/plain"},
            )
        )
        info = graph.inspect("sample.txt")
        assert isinstance(info, FileInfo)
        assert info.size_bytes > 0


class TestMultiCrateInspect:
    def test_inspect_in_multi_crate(self):
        """Prefixed IDs use raw_id for path resolution."""
        second = Path(__file__).parent.parent / "fixtures" / "second-crate"
        crate = Crate(str(FIXTURES), str(second))
        # Find a File entity from minimal-crate.
        file_entities = [e for e in crate.entities if "File" in e.types and "sample.txt" in e.id]
        if not file_entities:
            pytest.skip("No sample.txt File entity in multi-crate fixture")
        entity = file_entities[0]
        info = crate.inspect(entity)
        assert isinstance(info, FileInfo)
        assert info.size_bytes > 0
