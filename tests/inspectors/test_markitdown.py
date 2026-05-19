"""Tests for MarkItDownInspector."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph.core.models import FileInfo
from crategraph.inspectors.markitdown import MarkItDownInspector

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


class TestMarkItDownInspectorSupports:
    def test_supports_existing_txt_file(self):
        inspector = MarkItDownInspector()
        assert inspector.supports(FIXTURES / "sample.txt") is True

    def test_does_not_support_missing_file(self):
        inspector = MarkItDownInspector()
        assert inspector.supports(FIXTURES / "nonexistent.txt") is False


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

    def test_inspect_text_file_falls_back_to_utf8_when_markitdown_decoding_fails(
        self, tmp_path, monkeypatch
    ):
        import markitdown

        class FailingMarkItDown:
            def convert(self, path):
                raise RuntimeError("PlainTextConverter threw UnicodeDecodeError")

        monkeypatch.setattr(markitdown, "MarkItDown", FailingMarkItDown)

        path = tmp_path / "sample.txt"
        path.write_text("Temperature below 16°C\n", encoding="utf-8")

        info = MarkItDownInspector().inspect(path)

        assert info.content == "Temperature below 16°C\n"
        assert info.media_type == "text/plain"

    def test_inspect_without_markitdown_raises(self):
        import unittest.mock

        with unittest.mock.patch.dict("sys.modules", {"markitdown": None}):
            inspector = MarkItDownInspector()
            with pytest.raises(ImportError, match="pip install crategraph"):
                inspector.inspect(FIXTURES / "sample.txt")
