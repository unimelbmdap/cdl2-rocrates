"""Tests for ForceGraph3DRenderer."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#c", types=["Organisation"], properties={"name": "Uni of Melbourne"}))
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    return g


class TestGraphToJson:
    def test_returns_dict_with_nodes_and_links(self):
        g = _build_graph()
        renderer = ForceGraph3DRenderer()
        data = renderer._graph_to_json(g, colour_by="type", size_by="connections")
        assert "nodes" in data
        assert "links" in data

    def test_node_count(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        assert len(data["nodes"]) == 3

    def test_link_count(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        assert len(data["links"]) == 2

    def test_node_has_required_fields(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        node = data["nodes"][0]
        for field in ("id", "name", "val", "color", "degree", "properties"):
            assert field in node, f"Missing field: {field}"

    def test_link_has_required_fields(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        link = data["links"][0]
        for field in ("source", "target", "type", "properties"):
            assert field in link, f"Missing field: {field}"

    def test_node_name_uses_entity_name(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        names = {n["id"]: n["name"] for n in data["nodes"]}
        assert names["#a"] == "Alice"
        assert names["#c"] == "Uni of Melbourne"

    def test_nodes_coloured_by_type(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        colours = {n["id"]: n["color"] for n in data["nodes"]}
        assert colours["#a"] == colours["#b"]  # same type
        assert colours["#a"] != colours["#c"]  # different type

    def test_nodes_coloured_by_community(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(
            g, colour_by="community", size_by="connections"
        )
        for node in data["nodes"]:
            assert "color" in node

    def test_node_val_is_logarithmic(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        vals = {n["id"]: n["val"] for n in data["nodes"]}
        # #c has degree 2, #a has degree 1 — #c should be larger.
        assert vals["#c"] > vals["#a"]

    def test_node_val_bounds(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        for node in data["nodes"]:
            assert 2 <= node["val"] <= 100

    def test_empty_graph(self):
        g = Graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        assert data == {"nodes": [], "links": []}

    def test_json_serialisable(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        # Should not raise.
        json.dumps(data)


class TestColourByGeneric:
    def test_unknown_property_all_same_colour(self):
        g = _build_graph()
        data = ForceGraph3DRenderer()._graph_to_json(
            g, colour_by="nonexistent", size_by="connections"
        )
        colours = {n["color"] for n in data["nodes"]}
        assert len(colours) == 1  # all "(no value)"

    def test_colour_by_arbitrary_property(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "A", "dept": "IT"}))
        g._add_node(Entity(id="#b", types=["Person"], properties={"name": "B", "dept": "IT"}))
        g._add_node(Entity(id="#c", types=["Person"], properties={"name": "C", "dept": "HR"}))
        g._add_edge(Relationship(source="#a", target="#b", type="knows"))
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="dept", size_by="connections")
        colours = {n["id"]: n["color"] for n in data["nodes"]}
        assert colours["#a"] == colours["#b"]
        assert colours["#a"] != colours["#c"]


class TestForceGraph3DRenderer:
    def test_save_to_filepath(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            result = ForceGraph3DRenderer().render(g, filepath=filepath)
            assert result == filepath
            content = Path(filepath).read_text()
            assert "Alice" in content
            assert "3d-force-graph" in content

    def test_inline_render_is_iframe_wrapped(self):
        # Jupyter does not run <script> injected straight into cell output, so
        # the page must be embedded in an <iframe srcdoc> to render inline.
        g = _build_graph()
        html_str = ForceGraph3DRenderer().render(g).data
        assert "<iframe" in html_str
        assert "srcdoc=" in html_str
        assert "<script>" not in html_str

    def test_html_contains_graph_data(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            ForceGraph3DRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            assert '"#a"' in content
            assert '"#b"' in content
            assert '"memberOf"' in content

    def test_html_has_cdn_scripts(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            ForceGraph3DRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            assert "unpkg.com/three" in content
            assert "unpkg.com/3d-force-graph" in content

    def test_html_has_controls(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            ForceGraph3DRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            assert "dark-mode-toggle" in content
            assert "rotate-checkbox" in content

    def test_returns_html_object_when_no_filepath(self):
        g = _build_graph()
        result = ForceGraph3DRenderer().render(g)
        # Should return an IPython.display.HTML or a string containing HTML.
        html_str = result.data if hasattr(result, "data") else str(result)
        assert "3d-force-graph" in html_str

    def test_empty_graph_renders(self):
        g = Graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "empty.html")
            result = ForceGraph3DRenderer().render(g, filepath=filepath)
            assert result == filepath
            content = Path(filepath).read_text()
            assert "No network data" in content or "3d-force-graph" in content

    def test_colour_by_community(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            ForceGraph3DRenderer().render(
                g,
                filepath=filepath,
                colour_by="community",
            )
            content = Path(filepath).read_text()
            assert "Alice" in content

    def test_height_and_width_in_html(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            ForceGraph3DRenderer().render(
                g,
                filepath=filepath,
                height="800px",
                width="50%",
            )
            content = Path(filepath).read_text()
            assert "800px" in content
            assert "50%" in content

    def test_embedded_json_escapes_script_breakout(self):
        g = Graph()
        g._add_node(
            Entity(
                id="#x",
                types=["Person"],
                properties={"name": "</script><script>alert(1)</script>"},
            )
        )
        # Assert on the raw file output: the inline path additionally escapes
        # the whole page inside an iframe srcdoc, which would mask the
        # JSON-level ``</`` escaping this test targets.
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "breakout.html")
            ForceGraph3DRenderer().render(g, filepath=filepath)
            html = Path(filepath).read_text()
        assert "</script><script>alert(1)</script>" not in html
        assert "<\\/script><script>alert(1)<\\/script>" in html


class TestForceGraph3DTitle:
    """The graph title flows into the rendered <title> tag."""

    @staticmethod
    def _title_tag(content: str) -> str:
        import re

        match = re.search(r"<title>(.*?)</title>", content, re.DOTALL)
        assert match is not None, "No <title> tag in rendered HTML"
        return match.group(1)

    def test_template_formats_title(self):
        g = _build_graph()
        g.metadata["name"] = "Project Acme"
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "out.html")
            ForceGraph3DRenderer().render(g, filepath=filepath)
            assert (
                self._title_tag(Path(filepath).read_text())
                == "Project Acme | 3D Network Visualisation"
            )

    def test_template_uses_fallback_when_no_name(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "out.html")
            ForceGraph3DRenderer().render(g, filepath=filepath)
            assert "Untitled RO-Crate" in self._title_tag(Path(filepath).read_text())


class TestBidirectionalLinks:
    def test_bidirectional_link_has_flag(self):
        """Collapsed bidirectional edges should have bidirectional=True in JSON."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
        g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob"}))
        g._add_edge(
            Relationship(
                source="#a",
                target="#b",
                type="2 relationships",
                properties={
                    "collapsed": True,
                    "bidirectional": True,
                    "count": 2,
                    "types": ["author", "reviewer"],
                    "weight": 2,
                },
            )
        )
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        assert len(data["links"]) == 1
        assert data["links"][0]["bidirectional"] is True

    def test_normal_link_not_bidirectional(self):
        """Normal edges should have bidirectional=False."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
        g._add_node(Entity(id="#b", types=["Organisation"], properties={"name": "CSIRO"}))
        g._add_edge(Relationship(source="#a", target="#b", type="author"))
        data = ForceGraph3DRenderer()._graph_to_json(g, colour_by="type", size_by="connections")
        assert data["links"][0]["bidirectional"] is False


class TestEdgeWidth:
    def _graph(self):
        from crategraph.core.graph import Graph
        from crategraph.core.models import Entity, Relationship

        g = Graph()
        g._add_node(Entity(id="#a", types=["T"], properties={}))
        g._add_node(Entity(id="#b", types=["T"], properties={}))
        g._add_node(Entity(id="#c", types=["T"], properties={}))
        g._add_edge(Relationship(source="#a", target="#b", type="r", properties={"weight": 5}))
        g._add_edge(Relationship(source="#b", target="#c", type="r", properties={"weight": 20}))
        return g

    def test_edge_width_none_preserves_legacy_formula(self):
        """Pre-existing 0.4 + 2*log1p(weight) path, rounded to 2 dp.

        Uses a weight=1 edge to *discriminate* the legacy path (which
        gives 0.4 for weight<=1) from the helper path (which would give
        ~2.386). Also asserts byte-identity with a no-argument call so
        future drift between ``edge_width=None`` and "parameter absent"
        is caught.
        """
        import math

        from crategraph.core.graph import Graph
        from crategraph.core.models import Entity, Relationship
        from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer

        g = Graph()
        g._add_node(Entity(id="#a", types=["T"], properties={}))
        g._add_node(Entity(id="#b", types=["T"], properties={}))
        g._add_node(Entity(id="#c", types=["T"], properties={}))
        g._add_node(Entity(id="#d", types=["T"], properties={}))
        g._add_edge(Relationship(source="#a", target="#b", type="r", properties={"weight": 5}))
        g._add_edge(Relationship(source="#b", target="#c", type="r", properties={"weight": 20}))
        # weight=1 → legacy else-branch (width=0.4); helper would give ~2.386.
        g._add_edge(Relationship(source="#c", target="#d", type="r", properties={"weight": 1}))

        data_none = ForceGraph3DRenderer()._graph_to_json(
            g, colour_by="type", size_by="connections", edge_width=None
        )
        widths_none = [link["width"] for link in data_none["links"]]
        assert widths_none == [
            round(0.4 + 2 * math.log1p(5), 2),
            round(0.4 + 2 * math.log1p(20), 2),
            0.4,  # legacy else-branch — helper would give ~2.386 here
        ]

        # Byte-identity with no-argument call — catches drift between
        # ``edge_width=None`` and "parameter absent".
        data_default = ForceGraph3DRenderer()._graph_to_json(
            g, colour_by="type", size_by="connections"
        )
        assert data_default == data_none

    def test_edge_width_scalar_overrides(self):
        from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer

        g = self._graph()
        data = ForceGraph3DRenderer()._graph_to_json(
            g, colour_by="type", size_by="connections", edge_width=3
        )
        assert [link["width"] for link in data["links"]] == [3.0, 3.0]

    def test_edge_width_attribute_uses_unified_formula(self):
        import math

        from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer

        g = self._graph()
        data = ForceGraph3DRenderer()._graph_to_json(
            g, colour_by="type", size_by="connections", edge_width="weight"
        )
        assert [link["width"] for link in data["links"]] == [
            1.0 + 2.0 * math.log1p(5),
            1.0 + 2.0 * math.log1p(20),
        ]

    def test_edge_width_zero_is_honoured_not_coerced_to_default(self):
        """``edge_width=0`` must reach the browser as ``0.0``, not fall back
        to 0.4. The template previously used ``link.width || 0.4`` which
        treats 0 as falsy — guard against regression by asserting the JSON
        and the template expression together."""
        from importlib.resources import files

        from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer

        g = self._graph()
        data = ForceGraph3DRenderer()._graph_to_json(
            g, colour_by="type", size_by="connections", edge_width=0
        )
        assert [link["width"] for link in data["links"]] == [0.0, 0.0]

        template = (
            files("crategraph.renderers.templates")
            .joinpath("forcegraph3d.html")
            .read_text(encoding="utf-8")
        )
        assert "link.width || " not in template, (
            "3D template uses `||` fallback, which coerces 0 to the default. "
            "Use `link.width != null ? link.width : ...` (or `??`) instead."
        )


class TestGraphVisualise3D:
    """Integration tests: Graph.visualise(renderer='3d') full pipeline."""

    def test_visualise_3d(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "output.html")
            result = g.visualise(renderer="3d", filepath=filepath)
            assert result == filepath
            assert Path(filepath).exists()

    def test_visualise_3d_community(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "output.html")
            result = g.visualise(
                renderer="3d",
                filepath=filepath,
                colour_by="community",
            )
            assert result == filepath

    def test_merged_graph_visualise_3d(self):
        g = _build_graph()
        merged = g.merge_nodes(by="type")
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "merged.html")
            result = merged.visualise(renderer="3d", filepath=filepath)
            assert result == filepath
