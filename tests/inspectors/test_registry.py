"""Tests for the inspector registry."""

from __future__ import annotations

from pathlib import Path

from crategraph.core.models import Entity
from crategraph.inspectors import find_inspector
from crategraph.inspectors.markitdown import MarkItDownInspector

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


class TestFindInspector:
    def test_finds_inspector_for_txt_file(self):
        entity = Entity(
            id="sample.txt",
            types=["File"],
            properties={"encodingFormat": "text/plain"},
            source=str(FIXTURES),
        )
        inspector = find_inspector(entity)
        assert inspector is not None
        assert isinstance(inspector, MarkItDownInspector)

    def test_returns_none_for_contextual_entity(self):
        entity = Entity(
            id="#alice",
            types=["Person"],
            properties={"name": "Alice"},
            source=str(FIXTURES),
        )
        inspector = find_inspector(entity)
        assert inspector is None

    def test_returns_none_for_missing_file(self):
        entity = Entity(
            id="nonexistent.txt",
            types=["File"],
            properties={},
            source=str(FIXTURES),
        )
        inspector = find_inspector(entity)
        assert inspector is None
