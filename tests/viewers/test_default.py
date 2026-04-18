"""Tests for DefaultViewer."""

from __future__ import annotations

from pathlib import Path

from crategraph.core.models import ViewInfo
from crategraph.viewers.default import DefaultViewer

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


class TestDefaultViewerSupports:
    def test_supports_existing_png_file(self):
        viewer = DefaultViewer()
        assert viewer.supports(FIXTURES / "sample.png") is True

    def test_supports_existing_csv_file(self):
        viewer = DefaultViewer()
        assert viewer.supports(FIXTURES / "sample.csv") is True

    def test_supports_existing_txt_file(self):
        viewer = DefaultViewer()
        assert viewer.supports(FIXTURES / "sample.txt") is True

    def test_does_not_support_missing_file(self):
        viewer = DefaultViewer()
        assert viewer.supports(FIXTURES / "nonexistent.txt") is False


class TestDefaultViewerView:
    def test_view_png_embeds_base64_image(self):
        viewer = DefaultViewer()
        path = FIXTURES / "sample.png"
        info = viewer.view(path)
        assert isinstance(info, ViewInfo)
        assert "<img" in info.html
        assert "data:image/png;base64," in info.html
        assert info.size_bytes > 0
        assert info.path == str(path)

    def test_view_csv_renders_html_table(self):
        viewer = DefaultViewer()
        path = FIXTURES / "sample.csv"
        info = viewer.view(path)
        assert isinstance(info, ViewInfo)
        assert "<table" in info.html
        assert "Alice" in info.html
        assert "Bob" in info.html
        assert info.size_bytes > 0

    def test_view_txt_renders_pre_block(self):
        viewer = DefaultViewer()
        path = FIXTURES / "sample.txt"
        info = viewer.view(path)
        assert isinstance(info, ViewInfo)
        assert "<pre" in info.html
        assert "sample text file" in info.html.lower()
        assert info.size_bytes > 0

    def test_view_pdf_renders_fallback(self):
        viewer = DefaultViewer()
        path = FIXTURES / "sample.pdf"
        info = viewer.view(path)
        assert isinstance(info, ViewInfo)
        # PDF should render something (even if just metadata/fallback)
        assert info.size_bytes > 0
        assert len(info.html) > 0
