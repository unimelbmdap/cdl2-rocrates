"""Tests for SigmaRenderer."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.renderers.sigma import SigmaRenderer


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#c", types=["Organisation"], properties={"name": "Uni of Melbourne"}))
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    return g


class TestGraphToJson:
    def test_returns_dict_with_nodes_and_edges(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        assert "nodes" in data
        assert "edges" in data

    def test_node_count(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        assert len(data["nodes"]) == 3

    def test_edge_count(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        assert len(data["edges"]) == 2

    def test_node_has_required_fields(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        node = data["nodes"][0]
        for field in ("id", "label", "x", "y", "size", "color", "entityType", "degree"):
            assert field in node, f"Missing field: {field}"

    def test_node_uses_entity_type_not_type(self):
        """Sigma reserves 'type' for render programs — we must use 'entityType'."""
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        node = data["nodes"][0]
        assert "entityType" in node
        assert "type" not in node

    def test_edge_has_required_fields(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        edge = data["edges"][0]
        for field in ("id", "source", "target", "color"):
            assert field in edge, f"Missing field: {field}"

    def test_node_name_uses_entity_name(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        labels = {n["id"]: n["label"] for n in data["nodes"]}
        assert labels["#a"] == "Alice"
        assert labels["#c"] == "Uni of Melbourne"

    def test_nodes_coloured_by_type(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        colours = {n["id"]: n["color"] for n in data["nodes"]}
        assert colours["#a"] == colours["#b"]  # same type
        assert colours["#a"] != colours["#c"]  # different type

    def test_nodes_coloured_by_community(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="community", size_by="connections")
        for node in data["nodes"]:
            assert "color" in node

    def test_node_size_scales_with_degree(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        sizes = {n["id"]: n["size"] for n in data["nodes"]}
        # #c has degree 2, #a has degree 1 — #c should be larger.
        assert sizes["#c"] > sizes["#a"]

    def test_node_size_bounds(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        for node in data["nodes"]:
            assert 3.0 <= node["size"] <= 20.0

    def test_node_size_uniform_when_not_connections(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="custom_prop")
        for node in data["nodes"]:
            assert node["size"] == 6.0

    def test_node_size_single_node(self):
        """A lone node with degree 0 should get minimum size."""
        g = Graph()
        g._add_node(Entity(id="#lone", types=["Thing"], properties={"name": "Solo"}))
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        assert data["nodes"][0]["size"] == 3.0

    def test_node_colour_has_alpha(self):
        """Node colours should be rgba with 0.6 opacity."""
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        for node in data["nodes"]:
            assert node["color"].startswith("rgba(")
            assert node["color"].endswith(",0.6)")

    def test_edge_colour_is_dimmed_hex(self):
        """Edge colours should be darkened hex derived from source node."""
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        for edge in data["edges"]:
            assert edge["color"].startswith("#")
            assert len(edge["color"]) == 7

    def test_empty_graph(self):
        g = Graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        assert data == {"nodes": [], "edges": []}

    def test_json_serialisable(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        json.dumps(data)  # should not raise


class TestSigmaRenderer:
    def test_save_to_filepath(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            result = SigmaRenderer().render(g, filepath=filepath)
            assert result == filepath
            content = Path(filepath).read_text()
            assert "Alice" in content

    def test_html_contains_graph_data(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            assert '"#a"' in content
            assert '"#b"' in content

    def test_html_contains_vendored_bundle(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            # The vendored bundle should be inlined.
            assert "graphology" in content.lower() or "sigma" in content.lower()

    def test_returns_html_object_when_no_filepath(self):
        g = _build_graph()
        result = SigmaRenderer().render(g)
        html_str = result.data if hasattr(result, "data") else str(result)
        assert "sigma-container" in html_str

    def test_animated_false_by_default(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            assert '"animated": false' in content or '"animated":false' in content

    def test_animated_true_passed_to_template(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath, animated=True)
            content = Path(filepath).read_text()
            assert '"animated": true' in content or '"animated":true' in content

    def test_height_and_width_in_html(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath, height="800px", width="50%")
            content = Path(filepath).read_text()
            assert "800px" in content
            assert "50%" in content

    def test_empty_graph_renders(self):
        g = Graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "empty.html")
            result = SigmaRenderer().render(g, filepath=filepath)
            assert result == filepath

    def test_theme_toggle_button_present(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            assert 'id="btn-theme"' in content

    def test_light_theme_css_present(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            assert '[data-theme="light"]' in content

    def test_colour_by_community(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath, colour_by="community")
            content = Path(filepath).read_text()
            assert "Alice" in content

    def test_script_tag_in_entity_name_is_escaped(self):
        """Verify </script> in node data cannot break out of the JSON script block."""
        g = Graph()
        g._add_node(
            Entity(
                id="#xss",
                types=["Thing"],
                properties={"name": "</script><script>alert(1)//"},
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "xss.html")
            SigmaRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            assert "</script><script>" not in content
            assert "<\\/script>" in content


class TestGraphVisualiseSigma:
    """Integration tests: Graph.visualise(renderer='2d') full pipeline (sigma is default)."""

    def test_visualise_default_is_sigma(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "output.html")
            result = g.visualise(filepath=filepath)
            assert result == filepath
            assert Path(filepath).exists()
            content = Path(filepath).read_text()
            assert "sigma" in content.lower() or "graphology" in content.lower()

    def test_visualise_2d(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "output.html")
            result = g.visualise(renderer="2d", filepath=filepath)
            assert result == filepath
            assert Path(filepath).exists()

    def test_visualise_2d_community(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "output.html")
            result = g.visualise(renderer="2d", filepath=filepath, colour_by="community")
            assert result == filepath

    def test_visualise_2d_animated(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "output.html")
            result = g.visualise(renderer="2d", filepath=filepath, animated=True)
            assert result == filepath
            content = Path(filepath).read_text()
            assert '"animated": true' in content or '"animated":true' in content

    def test_merged_graph_visualise_2d(self):
        g = _build_graph()
        merged = g.merge_nodes(by="type")
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "merged.html")
            result = merged.visualise(renderer="2d", filepath=filepath)
            assert result == filepath


class TestSigmaSimple:
    """Tests for the simple/thumbnail sigma template."""

    def test_simple_renders_to_filepath(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "thumb.html")
            result = SigmaRenderer().render(g, filepath=filepath, simple=True)
            assert result == filepath
            assert Path(filepath).exists()

    def test_simple_contains_graph_data(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "thumb.html")
            SigmaRenderer().render(g, filepath=filepath, simple=True)
            content = Path(filepath).read_text()
            assert '"#a"' in content
            assert '"#b"' in content

    def test_simple_has_no_panels(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "thumb.html")
            SigmaRenderer().render(g, filepath=filepath, simple=True)
            content = Path(filepath).read_text()
            assert 'id="legend"' not in content
            assert 'id="details"' not in content
            assert 'id="info"' not in content

    def test_simple_config_flag(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "thumb.html")
            SigmaRenderer().render(g, filepath=filepath, simple=True)
            content = Path(filepath).read_text()
            assert '"simple": true' in content or '"simple":true' in content

    def test_simple_empty_graph(self):
        g = Graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "empty.html")
            result = SigmaRenderer().render(g, filepath=filepath, simple=True)
            assert result == filepath

    def test_simple_returns_html_object_when_no_filepath(self):
        g = _build_graph()
        result = SigmaRenderer().render(g, simple=True)
        html_str = result.data if hasattr(result, "data") else str(result)
        assert "sigma-container" in html_str
        assert 'id="legend"' not in html_str


class TestSigmaTitle:
    """The graph title flows into the rendered <title> tag."""

    @staticmethod
    def _title_tag(content: str) -> str:
        import re

        match = re.search(r"<title>(.*?)</title>", content, re.DOTALL)
        assert match is not None, "No <title> tag in rendered HTML"
        return match.group(1)

    def test_full_template_includes_graph_title(self):
        g = _build_graph()
        g.metadata["name"] = "Project Acme"
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "out.html")
            SigmaRenderer().render(g, filepath=filepath)
            assert "Project Acme" in self._title_tag(Path(filepath).read_text())

    def test_simple_template_formats_title(self):
        g = _build_graph()
        g.metadata["name"] = "Project Acme"
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "out.html")
            SigmaRenderer().render(g, filepath=filepath, simple=True)
            assert self._title_tag(Path(filepath).read_text()) == "Project Acme | Graph Thumbnail"

    def test_full_template_uses_fallback_when_no_name(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "out.html")
            SigmaRenderer().render(g, filepath=filepath)
            assert "Untitled RO-Crate" in self._title_tag(Path(filepath).read_text())


class TestEdgeWidth:
    """edge_width API integration — per-edge ``size`` in the sigma JSON."""

    def test_edge_width_none_omits_size_from_edges(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(
            g, colour_by="type", size_by="connections", edge_width=None
        )
        for edge in data["edges"]:
            assert "size" not in edge, (
                "Expected no 'size' key when edge_width is None (bundle applies its own default)"
            )

    def test_edge_width_scalar_sets_every_edge_size(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(
            g, colour_by="type", size_by="connections", edge_width=3
        )
        assert data["edges"], "test graph should have edges"
        for edge in data["edges"]:
            assert edge["size"] == 3.0

    def test_edge_width_attribute_applies_log1p_formula(self):
        import math

        from crategraph.core.graph import Graph
        from crategraph.core.models import Entity, Relationship

        g = Graph()
        g._add_node(Entity(id="#a", types=["T"], properties={}))
        g._add_node(Entity(id="#b", types=["T"], properties={}))
        g._add_node(Entity(id="#c", types=["T"], properties={}))
        g._add_edge(Relationship(source="#a", target="#b", type="r", properties={"weight": 5}))
        g._add_edge(Relationship(source="#b", target="#c", type="r", properties={"weight": 20}))

        data = SigmaRenderer().graph_to_json(
            g, colour_by="type", size_by="connections", edge_width="weight"
        )
        sizes = [edge["size"] for edge in data["edges"]]
        assert sizes == [
            1.0 + 2.0 * math.log1p(5),
            1.0 + 2.0 * math.log1p(20),
        ]

    def test_edge_width_attribute_missing_falls_back_to_one(self):
        g = _build_graph()  # edges have no 'weight' property
        data = SigmaRenderer().graph_to_json(
            g, colour_by="type", size_by="connections", edge_width="weight"
        )
        for edge in data["edges"]:
            assert edge["size"] == 1.0


class TestBundleFreshness:
    """Catch the case where `js/sigma/src/main.js` was edited but the
    rebuilt bundle at `crategraph/renderers/templates/vendor/sigma-fa2.min.js`
    wasn't regenerated.

    The edge_width feature's JS change forwards ``e.size`` from the input
    JSON. If the bundle is stale (built before that change) then Python
    tests and docs imply the feature works, but the browser silently
    renders every edge at the old hardcoded ``0.3`` default.
    """

    def test_bundle_forwards_edge_size(self):
        from importlib.resources import files

        bundle = (
            files("crategraph.renderers.templates")
            .joinpath("vendor/sigma-fa2.min.js")
            .read_text(encoding="utf-8")
        )
        # The rebuilt bundle must reference `e.size` somewhere; a stale
        # bundle only has the hardcoded `size:.3` (or `size:0.3`).
        assert "e.size" in bundle, (
            "sigma bundle appears stale — rebuild with:\n"
            "  cd js/sigma && npm install && npm run build && "
            "cp dist/sigma-fa2.min.js ../../crategraph/renderers/templates/vendor/"
        )
