"""Tests for FileInfo dataclass and Inspector ABC."""

from __future__ import annotations

from crategraph.core.models import FileInfo


class TestFileInfo:
    def test_create_file_info(self):
        info = FileInfo(
            path="/tmp/sample.txt",
            content="Hello world",
            title="Sample",
            size_bytes=11,
            media_type="text/plain",
        )
        assert info.path == "/tmp/sample.txt"
        assert info.content == "Hello world"
        assert info.title == "Sample"
        assert info.size_bytes == 11
        assert info.media_type == "text/plain"

    def test_file_info_is_frozen(self):
        info = FileInfo(
            path="/tmp/sample.txt",
            content="Hello",
            title=None,
            size_bytes=5,
            media_type=None,
        )
        import pytest

        with pytest.raises(AttributeError):
            info.path = "/other"

    def test_file_info_title_optional(self):
        info = FileInfo(
            path="/tmp/sample.txt",
            content="Hello",
            title=None,
            size_bytes=5,
            media_type=None,
        )
        assert info.title is None
        assert info.media_type is None

    def test_file_info_repr_html(self):
        info = FileInfo(
            path="/tmp/sample.txt",
            content="Some **markdown** content",
            title="My File",
            size_bytes=1024,
            media_type="text/plain",
        )
        html = info._repr_html_()
        assert "sample.txt" in html
        assert "1,024" in html or "1024" in html
        assert "text/plain" in html
        assert "Some **markdown** content" in html or "markdown" in html

    def test_file_info_repr(self):
        info = FileInfo(
            path="/tmp/sample.txt",
            content="Hello",
            title=None,
            size_bytes=42,
            media_type="text/plain",
        )
        r = repr(info)
        assert "sample.txt" in r
