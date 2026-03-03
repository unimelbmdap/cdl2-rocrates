"""Tests for ViewInfo dataclass and Viewer ABC."""

from __future__ import annotations

from crategraph.core.models import ViewInfo


class TestViewInfo:
    def test_create_view_info(self):
        info = ViewInfo(
            path="/tmp/sample.png",
            html="<img src='data:image/png;base64,abc'/>",
            title="Sample",
            size_bytes=75,
            media_type="image/png",
        )
        assert info.path == "/tmp/sample.png"
        assert info.html == "<img src='data:image/png;base64,abc'/>"
        assert info.title == "Sample"
        assert info.size_bytes == 75
        assert info.media_type == "image/png"

    def test_view_info_is_frozen(self):
        import pytest

        info = ViewInfo(
            path="/tmp/sample.png",
            html="<img/>",
            title=None,
            size_bytes=5,
            media_type=None,
        )
        with pytest.raises(AttributeError):
            info.path = "/other"

    def test_view_info_title_optional(self):
        info = ViewInfo(
            path="/tmp/sample.png",
            html="<img/>",
            title=None,
            size_bytes=5,
            media_type=None,
        )
        assert info.title is None
        assert info.media_type is None

    def test_view_info_repr_html_returns_html_directly(self):
        raw_html = "<img src='data:image/png;base64,abc'/>"
        info = ViewInfo(
            path="/tmp/sample.png",
            html=raw_html,
            title="My Image",
            size_bytes=1024,
            media_type="image/png",
        )
        result = info._repr_html_()
        # Should contain the raw HTML, not escaped text in a <pre> block
        assert "<img" in result
        assert "sample.png" in result
        assert "1,024" in result or "1024" in result

    def test_view_info_repr(self):
        info = ViewInfo(
            path="/tmp/sample.png",
            html="<img/>",
            title=None,
            size_bytes=42,
            media_type="image/png",
        )
        r = repr(info)
        assert "sample.png" in r
        assert "ViewInfo" in r
