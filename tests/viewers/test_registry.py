"""Tests for the viewer registry."""

from __future__ import annotations

from pathlib import Path

from crategraph.core.models import Entity
from crategraph.viewers import find_viewer
from crategraph.viewers.default import DefaultViewer

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


class TestFindViewer:
    def test_finds_viewer_for_png_file(self):
        entity = Entity(
            id="sample.png",
            types=["File"],
            properties={"encodingFormat": "image/png"},
            source=str(FIXTURES),
        )
        viewer = find_viewer(entity)
        assert viewer is not None
        assert isinstance(viewer, DefaultViewer)

    def test_finds_viewer_for_csv_file(self):
        entity = Entity(
            id="sample.csv",
            types=["File"],
            properties={"encodingFormat": "text/csv"},
            source=str(FIXTURES),
        )
        viewer = find_viewer(entity)
        assert viewer is not None

    def test_finds_viewer_for_txt_file(self):
        entity = Entity(
            id="sample.txt",
            types=["File"],
            properties={"encodingFormat": "text/plain"},
            source=str(FIXTURES),
        )
        viewer = find_viewer(entity)
        assert viewer is not None

    def test_returns_none_for_contextual_entity(self):
        entity = Entity(
            id="#alice",
            types=["Person"],
            properties={"name": "Alice"},
            source=str(FIXTURES),
        )
        viewer = find_viewer(entity)
        assert viewer is None

    def test_returns_none_for_missing_file(self):
        entity = Entity(
            id="nonexistent.txt",
            types=["File"],
            properties={},
            source=str(FIXTURES),
        )
        viewer = find_viewer(entity)
        assert viewer is None
