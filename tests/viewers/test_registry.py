"""Tests for the viewer registry."""

from __future__ import annotations

from pathlib import Path

from crategraph.viewers import find_viewer
from crategraph.viewers.default import DefaultViewer

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


class TestFindViewer:
    def test_finds_viewer_for_png_file(self):
        viewer = find_viewer(FIXTURES / "sample.png")
        assert viewer is not None
        assert isinstance(viewer, DefaultViewer)

    def test_finds_viewer_for_csv_file(self):
        viewer = find_viewer(FIXTURES / "sample.csv")
        assert viewer is not None

    def test_finds_viewer_for_txt_file(self):
        viewer = find_viewer(FIXTURES / "sample.txt")
        assert viewer is not None

    def test_returns_none_for_missing_file(self):
        viewer = find_viewer(FIXTURES / "nonexistent.txt")
        assert viewer is None
