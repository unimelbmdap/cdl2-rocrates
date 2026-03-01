"""Tests for MarkItDownInspector."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph.core.models import Entity, FileInfo
from crategraph.inspectors.markitdown import MarkItDownInspector

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


class TestMarkItDownInspectorSupports:
    def test_supports_existing_txt_file(self):
        inspector = MarkItDownInspector()
        entity = Entity(
            id="sample.txt",
            types=["File"],
            properties={"encodingFormat": "text/plain"},
            source=str(FIXTURES),
        )
        assert inspector.supports(entity) is True

    def test_does_not_support_missing_file(self):
        inspector = MarkItDownInspector()
        entity = Entity(
            id="nonexistent.txt",
            types=["File"],
            properties={},
            source=str(FIXTURES),
        )
        assert inspector.supports(entity) is False

    def test_does_not_support_contextual_entity(self):
        inspector = MarkItDownInspector()
        entity = Entity(
            id="#alice",
            types=["Person"],
            properties={"name": "Alice"},
            source=str(FIXTURES),
        )
        assert inspector.supports(entity) is False


class TestMarkItDownInspectorInspect:
    def test_inspect_txt_file(self):
        inspector = MarkItDownInspector()
        path = FIXTURES / "sample.txt"
        info = inspector.inspect(path)
        assert isinstance(info, FileInfo)
        assert "sample text file" in info.content.lower()
        assert info.size_bytes > 0
        assert info.path == str(path)

    def test_inspect_csv_file(self):
        inspector = MarkItDownInspector()
        path = FIXTURES / "sample.csv"
        info = inspector.inspect(path)
        assert isinstance(info, FileInfo)
        assert "Alice" in info.content or "alice" in info.content.lower()
        assert info.size_bytes > 0

    def test_inspect_pdf_file(self):
        inspector = MarkItDownInspector()
        path = FIXTURES / "sample.pdf"
        info = inspector.inspect(path)
        assert isinstance(info, FileInfo)
        assert info.size_bytes > 0
        assert isinstance(info.content, str)

    def test_inspect_png_file(self):
        inspector = MarkItDownInspector()
        path = FIXTURES / "sample.png"
        info = inspector.inspect(path)
        assert isinstance(info, FileInfo)
        assert info.size_bytes > 0
        assert isinstance(info.content, str)

    def test_inspect_without_markitdown_raises(self):
        import unittest.mock

        with unittest.mock.patch.dict("sys.modules", {"markitdown": None}):
            inspector = MarkItDownInspector()
            with pytest.raises(ImportError, match="pip install crategraph"):
                inspector.inspect(FIXTURES / "sample.txt")
