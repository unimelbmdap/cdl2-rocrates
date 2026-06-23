"""Tests for the SVG renderer."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.renderers.svg import SvgRenderer


def _build_graph() -> Graph:
    """Small graph with mixed types and edges — NOT a merged graph."""
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#c", types=["Organisation"], properties={"name": "CSIRO"}))
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    return g


def _build_merged_graph() -> Graph:
    """Graph that looks like merge_by_primary_type output (has count property)."""
    g = Graph()
    g._add_node(Entity(id="Person", types=["Person"], properties={"label": "Person", "count": 5}))
    g._add_node(
        Entity(
            id="Organisation",
            types=["Organisation"],
            properties={"label": "Organisation", "count": 2},
        )
    )
    g._add_edge(
        Relationship(
            source="Person",
            target="Organisation",
            type="merged",
            properties={"weight": 3},
        )
    )
    return g


class TestSvgRendererBasic:
    def test_returns_svg_string_for_raw_graph(self):
        r = SvgRenderer()
        result = r.render(_build_graph())
        svg = result.data if hasattr(result, "data") else str(result)
        assert svg.startswith("<svg")
        assert svg.strip().endswith("</svg>")

    def test_contains_circles_for_each_node(self):
        r = SvgRenderer()
        svg = r.render(_build_graph())
        svg = svg.data if hasattr(svg, "data") else str(svg)
        assert svg.count("<circle") == 3

    def test_contains_edges(self):
        r = SvgRenderer()
        svg = r.render(_build_graph())
        svg = svg.data if hasattr(svg, "data") else str(svg)
        assert "<line" in svg

    def test_contains_node_labels(self):
        r = SvgRenderer()
        svg = r.render(_build_graph())
        svg = svg.data if hasattr(svg, "data") else str(svg)
        assert "#a" in svg or "Alice" in svg

    def test_empty_graph(self):
        r = SvgRenderer()
        svg = r.render(Graph())
        svg = svg.data if hasattr(svg, "data") else str(svg)
        assert "Empty graph" in svg

    def test_viewbox_present(self):
        r = SvgRenderer()
        svg = r.render(_build_graph())
        svg = svg.data if hasattr(svg, "data") else str(svg)
        assert "viewBox" in svg


class TestSvgRendererSizing:
    def test_raw_graph_uses_degree_for_sizing(self):
        r = SvgRenderer()
        svg = r.render(_build_graph())
        svg = svg.data if hasattr(svg, "data") else str(svg)
        import re

        circles = re.findall(r'<circle[^>]*r="([\d.]+)"', svg)
        radii = [float(r_) for r_ in circles]
        assert len(radii) == 3
        assert max(radii) > min(radii)

    def test_merged_graph_uses_count_for_sizing(self):
        r = SvgRenderer()
        svg = r.render(_build_merged_graph())
        svg = svg.data if hasattr(svg, "data") else str(svg)
        import re

        circles = re.findall(r'<circle[^>]*r="([\d.]+)"', svg)
        radii = [float(r_) for r_ in circles]
        assert len(radii) == 2
        assert radii[0] > radii[1] or radii[1] > radii[0]


class TestSvgRendererColourBy:
    def test_colour_by_type(self):
        r = SvgRenderer()
        svg = r.render(_build_graph(), colour_by="type")
        svg = svg.data if hasattr(svg, "data") else str(svg)
        assert 'fill="#' in svg

    def test_colour_by_property(self):
        r = SvgRenderer()
        svg = r.render(_build_graph(), colour_by="name")
        svg = svg.data if hasattr(svg, "data") else str(svg)
        assert 'fill="#' in svg


class TestSvgRendererFilepath:
    def test_save_to_filepath(self):
        r = SvgRenderer()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.svg")
            result = r.render(_build_graph(), filepath=path)
            assert result == path
            content = Path(path).read_text()
            assert "<svg" in content

    def test_raises_when_file_exists_and_overwrite_false(self, tmp_path):
        out = tmp_path / "out.svg"
        out.write_text("existing")
        with pytest.raises(FileExistsError):
            SvgRenderer().render(_build_graph(), filepath=str(out))
        assert out.read_text() == "existing"

    def test_overwrite_true_replaces_file(self, tmp_path):
        out = tmp_path / "out.svg"
        out.write_text("existing")
        result = SvgRenderer().render(_build_graph(), filepath=str(out), overwrite=True)
        assert result == str(out)
        assert "<svg" in out.read_text()

    def test_no_filepath_returns_ipython_svg(self):
        r = SvgRenderer()
        result = r.render(_build_graph())
        assert hasattr(result, "data")  # IPython.display.SVG


class TestEdgeWidth:
    def _graph(self):
        from crategraph.core.graph import Graph
        from crategraph.core.models import Entity, Relationship

        g = Graph()
        g._add_node(Entity(id="#a", types=["T"], properties={}))
        g._add_node(Entity(id="#b", types=["T"], properties={}))
        g._add_node(Entity(id="#c", types=["T"], properties={}))
        g._add_node(Entity(id="#d", types=["T"], properties={}))
        g._add_edge(Relationship(source="#a", target="#b", type="r", properties={"weight": 5}))
        g._add_edge(Relationship(source="#b", target="#c", type="r", properties={"weight": 20}))
        # weight=1 — discriminator edge: legacy gives 1 + 3*(1/20) = 1.15, helper gives ~2.386.
        g._add_edge(Relationship(source="#c", target="#d", type="r", properties={"weight": 1}))
        return g

    def _extract_stroke_widths(self, svg_str: str) -> list[float]:
        import re

        return [float(m) for m in re.findall(r'<line[^>]*stroke-width="([\d.]+)"', svg_str)]

    def test_edge_width_none_preserves_legacy_linear_formula(self):
        """Pre-existing 1 + 3*(weight/max_weight) path, in viewBox units."""
        from crategraph.renderers.svg import SvgRenderer

        g = self._graph()
        svg_obj = SvgRenderer().render(g, edge_width=None)
        svg_str = svg_obj.data if hasattr(svg_obj, "data") else str(svg_obj)
        widths = self._extract_stroke_widths(svg_str)
        # max_weight=20 → widths = [1 + 3*(5/20), 1 + 3*(20/20), 1 + 3*(1/20)] = [1.75, 4.0, 1.15]
        # rendered as "1.8", "4.0", "1.1" (the renderer uses :.1f; Python uses banker's rounding).
        assert widths == [1.8, 4.0, 1.1]

    def test_edge_width_none_matches_no_argument(self):
        """edge_width=None must use the legacy formula path (same as no argument).

        Since layout is non-deterministic, we compare stroke-widths, not byte-identity.
        """
        from crategraph.renderers.svg import SvgRenderer

        g = self._graph()
        svg_none = SvgRenderer().render(g, edge_width=None)
        svg_default = SvgRenderer().render(g)
        data_none = svg_none.data if hasattr(svg_none, "data") else str(svg_none)
        data_default = svg_default.data if hasattr(svg_default, "data") else str(svg_default)
        # Both should use the legacy formula, so stroke-widths must be identical.
        widths_none = self._extract_stroke_widths(data_none)
        widths_default = self._extract_stroke_widths(data_default)
        assert widths_none == widths_default == [1.8, 4.0, 1.1]

    def test_edge_width_scalar_is_css_pixels_at_default_display(self):
        """edge_width=3 should render at 3 CSS pixels. Since the
        default viewBox is 2x the display size, we write 6.0 into
        stroke-width so the browser scales it down to 3 CSS pixels."""
        from crategraph.renderers.svg import SvgRenderer

        g = self._graph()
        svg_obj = SvgRenderer().render(g, edge_width=3)
        svg_str = svg_obj.data if hasattr(svg_obj, "data") else str(svg_obj)
        widths = self._extract_stroke_widths(svg_str)
        assert widths == [6.0, 6.0, 6.0]

    def test_edge_width_attribute_compensates_for_viewbox(self):
        import math

        from crategraph.renderers.svg import SvgRenderer

        g = self._graph()
        svg_obj = SvgRenderer().render(g, edge_width="weight")
        svg_str = svg_obj.data if hasattr(svg_obj, "data") else str(svg_obj)
        widths = self._extract_stroke_widths(svg_str)
        # Per-edge: (1 + 2*log1p(v)) * 2 (viewBox compensation). Values for v=5, v=20, v=1.
        expected = [
            round((1.0 + 2.0 * math.log1p(5)) * 2.0, 1),
            round((1.0 + 2.0 * math.log1p(20)) * 2.0, 1),
            round((1.0 + 2.0 * math.log1p(1)) * 2.0, 1),
        ]
        assert widths == expected
