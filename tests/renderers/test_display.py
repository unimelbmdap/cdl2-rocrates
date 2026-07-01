"""Tests for the inline-display iframe helper."""

from __future__ import annotations

from crategraph.renderers._display import wrap_iframe

_PAGE = "<!DOCTYPE html><html><body><script>渲染()</script></body></html>"


class TestSandbox:
    def test_iframe_is_sandboxed_without_same_origin(self):
        data = wrap_iframe(_PAGE).data
        assert "sandbox=" in data
        assert "allow-scripts" in data
        # allow-same-origin would let the frame's scripts reach the notebook
        # page's origin, defeating the isolation.
        assert "allow-same-origin" not in data


class TestDimensionHardening:
    def test_hostile_dimensions_cannot_break_out_of_attribute(self):
        data = wrap_iframe(_PAGE, width='1" onload="alert(1)px', height='2" onerror="x()px').data
        assert "onload=" not in data
        assert "onerror=" not in data

    def test_valid_pixel_dimensions_are_kept(self):
        data = wrap_iframe(_PAGE, width="800px", height="500px").data
        assert "width:800px" in data
        assert "height:500px" in data

    def test_viewport_height_falls_back_to_pixels(self):
        # 100vh is meaningless for an embedded frame; fall back to a pixel height.
        data = wrap_iframe(_PAGE, width="100%", height="100vh").data
        assert "width:100%" in data
        assert "height:600px" in data
