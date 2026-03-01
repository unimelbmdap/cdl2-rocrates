"""Tests for the SVG renderer."""

from __future__ import annotations

import tempfile
from pathlib import Path

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
    g._add_node(
        Entity(
            id="Person", types=["Person"], properties={"label": "Person", "count": 5}
        )
    )
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

    def test_no_filepath_returns_ipython_svg(self):
        r = SvgRenderer()
        result = r.render(_build_graph())
        assert hasattr(result, "data")  # IPython.display.SVG
