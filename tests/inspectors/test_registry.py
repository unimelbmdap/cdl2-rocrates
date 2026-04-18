"""Tests for the inspector registry."""

from __future__ import annotations

from pathlib import Path

from crategraph.inspectors import find_inspector
from crategraph.inspectors.markitdown import MarkItDownInspector

FIXTURES = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


class TestFindInspector:
    def test_finds_inspector_for_txt_file(self):
        inspector = find_inspector(FIXTURES / "sample.txt")
        assert inspector is not None
        assert isinstance(inspector, MarkItDownInspector)

    def test_returns_none_for_missing_file(self):
        inspector = find_inspector(FIXTURES / "nonexistent.txt")
        assert inspector is None
