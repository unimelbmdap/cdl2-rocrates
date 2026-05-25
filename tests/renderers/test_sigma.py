"""Tests for SigmaRenderer."""

from __future__ import annotations

import base64
import gzip
import json
import re
import tempfile
from pathlib import Path

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.renderers.sigma import SigmaRenderer

_PACKED_RE = re.compile(r'window\.graphDataPacked\s*=\s*"([^"]+)"')


def _unpack_graph_data(html: str) -> dict:
    """Extract and decompress the gzip+base64 graph payload from rendered HTML.

    Mirrors what the JS-side ``unpackGraphData`` does at page load. Tests
    that used to assert on plain JSON substrings in the HTML now decompress
    first.
    """
    match = _PACKED_RE.search(html)
    if match is None:
        raise AssertionError("HTML did not contain a window.graphDataPacked assignment")
    return json.loads(gzip.decompress(base64.b64decode(match.group(1))))


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
            data = _unpack_graph_data(content)
            assert any(n["label"] == "Alice" for n in data["nodes"])

    def test_html_contains_graph_data(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            data = _unpack_graph_data(content)
            ids = {n["id"] for n in data["nodes"]}
            assert "#a" in ids
            assert "#b" in ids

    def test_html_contains_vendored_bundle(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            SigmaRenderer().render(g, filepath=filepath)
            content = Path(filepath).read_text()
            # The vendored bundle should be inlined.
            assert "graphology" in content.lower() or "sigma" in content.lower()

    def test_packed_payload_uses_zero_mtime(self):
        """gzip.compress embeds an mtime in its header by default; without
        mtime=0 the same graph renders to different bytes seconds apart,
        making docs/caching/regression diffs noisy.

        Asserted at the header level (bytes 4-7 of the gzip stream) so the
        check is independent of FA2 layout stochasticity, which would
        otherwise make two renders differ for unrelated reasons.
        """
        import struct

        g = _build_graph()
        result = SigmaRenderer().render(g)
        match = _PACKED_RE.search(result.data)
        assert match is not None
        raw = base64.b64decode(match.group(1))
        # Gzip stream layout: magic (2) + method (1) + flags (1) + mtime (4) + xfl (1) + os (1)
        mtime = struct.unpack("<I", raw[4:8])[0]
        assert mtime == 0, f"expected mtime=0 in gzip header, got {mtime}"

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
            data = _unpack_graph_data(content)
            assert any(n["label"] == "Alice" for n in data["nodes"])

    def test_script_tag_in_entity_name_cannot_break_out(self):
        """A </script> in node data must not escape into HTML script context.

        The graph payload is gzip-compressed and base64-encoded into a JS
        string literal — base64 cannot contain `</script>` or quote
        characters, so the old ``_safe_json`` ``<\\/`` escape is no longer
        the line of defence. The packing format itself makes this
        attack-class structurally impossible.
        """
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
        # The script tag string must not appear anywhere in the HTML text.
        assert "</script><script>" not in content
        # And when decompressed, the original string survives intact —
        # confirming round-trip fidelity for adversarial inputs.
        data = _unpack_graph_data(content)
        assert any(n["label"] == "</script><script>alert(1)//" for n in data["nodes"])


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
            data = _unpack_graph_data(content)
            ids = {n["id"] for n in data["nodes"]}
            assert "#a" in ids
            assert "#b" in ids

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

    def test_bundle_forwards_node_properties(self):
        from importlib.resources import files

        bundle = (
            files("crategraph.renderers.templates")
            .joinpath("vendor/sigma-fa2.min.js")
            .read_text(encoding="utf-8")
        )
        # esbuild minifies the `n` parameter name, so we check for the
        # property-assignment pattern `properties:<var>.properties` which is
        # unique to the node-properties forwarding line in buildGraph.
        assert "properties" in bundle and ".properties" in bundle, (
            "sigma bundle appears stale — buildGraph must forward "
            "node properties. Rebuild with:\n"
            "  cd js/sigma && npm install && npm run build && "
            "cp dist/sigma-fa2.min.js ../../crategraph/renderers/templates/vendor/"
        )
        # More precisely, verify the assignment pattern survives minification.
        assert "properties:e.properties" in bundle or "properties:n.properties" in bundle, (
            "sigma bundle appears stale — buildGraph must forward "
            "node properties (expected `properties:<var>.properties` in bundle). "
            "Rebuild with:\n"
            "  cd js/sigma && npm install && npm run build && "
            "cp dist/sigma-fa2.min.js ../../crategraph/renderers/templates/vendor/"
        )

    def test_bundle_forwards_edge_type(self):
        from importlib.resources import files

        bundle = (
            files("crategraph.renderers.templates")
            .joinpath("vendor/sigma-fa2.min.js")
            .read_text(encoding="utf-8")
        )
        # We grep for the property-assignment pattern `relType:e.type`. The
        # attribute on the graphology edge is `relType`, not `type` — sigma
        # reserves `data.type` for the edge-program selector ("line", "arrow"),
        # and putting domain relationship types there crashes the WebGL render
        # at `edgePrograms[data.type].process`. The key-value pattern
        # `relType:e.type` is unique to OUR attribute object literal inside
        # buildGraph's `addDirectedEdgeWithKey` call. esbuild preserves
        # property names and object key literals, so this survives --minify.
        assert "relType:e.type" in bundle, (
            "sigma bundle appears stale — buildGraph must forward edge "
            "relationship type as `relType` (expected `relType:e.type` in "
            "bundle). Rebuild with:\n"
            "  cd js/sigma && npm install && npm run build && "
            "cp dist/sigma-fa2.min.js ../../crategraph/renderers/templates/vendor/"
        )

    def test_bundle_uses_directed_multigraph(self):
        from importlib.resources import files

        bundle = (
            files("crategraph.renderers.templates")
            .joinpath("vendor/sigma-fa2.min.js")
            .read_text(encoding="utf-8")
        )
        # We grep for `{multi:!0,type:"directed"}` — the minified form of our
        # Graph constructor literal `{ multi: true, type: "directed" }`.
        # esbuild replaces boolean `true` with `!0` under --minify, but
        # preserves string literals and property names.  The bare method name
        # `addDirectedEdgeWithKey` also appears in graphology's own library code
        # (where it is *defined*), so it would pass even against a stale bundle.
        # The constructor object literal is unique to OUR buildGraph call and
        # was absent in the pre-Task-4 bundle.
        assert 'multi:!0,type:"directed"' in bundle, (
            "sigma bundle appears stale — buildGraph must construct a directed "
            'multigraph (expected `multi:!0,type:"directed"` in bundle). '
            "Rebuild with:\n"
            "  cd js/sigma && npm install && npm run build && "
            "cp dist/sigma-fa2.min.js ../../crategraph/renderers/templates/vendor/"
        )

    def test_bundle_contains_data_node_id_marker(self):
        from importlib.resources import files

        bundle = (
            files("crategraph.renderers.templates")
            .joinpath("vendor/sigma-fa2.min.js")
            .read_text(encoding="utf-8")
        )
        # The clickable references in the details panel set this
        # attribute; its literal value survives minification because it
        # is an HTML attribute name, not an identifier.
        assert "data-node-id" in bundle, (
            "sigma bundle appears stale — appendClickableRef sets "
            "data-node-id. Rebuild with:\n"
            "  cd js/sigma && npm install && npm run build && "
            "cp dist/sigma-fa2.min.js ../../crategraph/renderers/templates/vendor/"
        )

    def test_bundle_reads_packed_graph_data(self):
        from importlib.resources import files

        bundle = (
            files("crategraph.renderers.templates")
            .joinpath("vendor/sigma-fa2.min.js")
            .read_text(encoding="utf-8")
        )
        # `graphDataPacked` is the new window-global the JS reads from
        # to find the gzip-compressed graph payload. If this marker is
        # missing, the bundle is still on the old plain-JSON path and
        # the page will fail with `undefined is not an object` at load.
        assert "graphDataPacked" in bundle, (
            "sigma bundle appears stale — JS must read window.graphDataPacked. "
            "Rebuild with:\n"
            "  cd js/sigma && npm install && npm run build && "
            "cp dist/sigma-fa2.min.js ../../crategraph/renderers/templates/vendor/"
        )


class TestSerialisedProperties:
    """Each node carries its entity properties when include_properties is set
    (the default). Internal keys and the redundant `name` key are stripped.
    Non-JSON-safe values are stringified so json.dumps cannot raise."""

    def test_properties_always_present_even_when_empty(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Thing"], properties={"_is_root": True}))
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        node = data["nodes"][0]
        assert "properties" in node
        assert node["properties"] == {}

    def test_underscore_prefixed_keys_stripped(self):
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["File"],
                properties={"_is_root": True, "_internal": "x", "encoding": "utf-8"},
            )
        )
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        props = data["nodes"][0]["properties"]
        assert "_is_root" not in props
        assert "_internal" not in props
        assert props["encoding"] == "utf-8"

    def test_name_key_stripped(self):
        # name is already in the node `label`; do not duplicate it.
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice", "age": 30}))
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        props = data["nodes"][0]["properties"]
        assert "name" not in props
        assert props["age"] == 30

    def test_reference_value_preserved_verbatim(self):
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["CreativeWork"],
                properties={"name": "Doc", "author": {"@id": "#b"}},
            )
        )
        g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Author"}))
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        node_a = next(n for n in data["nodes"] if n["id"] == "#a")
        assert node_a["properties"]["author"] == {"@id": "#b"}

    def test_list_of_references_preserved(self):
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["CreativeWork"],
                properties={
                    "name": "Doc",
                    "authors": [{"@id": "#b"}, {"@id": "#c"}],
                },
            )
        )
        g._add_node(Entity(id="#b", types=["Person"], properties={"name": "X"}))
        g._add_node(Entity(id="#c", types=["Person"], properties={"name": "Y"}))
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        node_a = next(n for n in data["nodes"] if n["id"] == "#a")
        assert node_a["properties"]["authors"] == [{"@id": "#b"}, {"@id": "#c"}]

    def test_non_json_safe_values_are_stringified(self):
        import json
        from datetime import date
        from pathlib import PurePosixPath

        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["File"],
                properties={
                    "name": "Doc",
                    "path": PurePosixPath("/data/foo.csv"),
                    "created": date(2024, 9, 1),
                },
            )
        )
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        props = data["nodes"][0]["properties"]
        # Stringified — exact str() output is fine to assert because
        # both stdlib types have stable __str__.
        assert props["path"] == "/data/foo.csv"
        assert props["created"] == "2024-09-01"
        # And the result round-trips through json (this is the real reason
        # we normalise — render() does json.dumps internally).
        json.dumps(data)

    def test_nested_non_json_safe_values_normalised(self):
        from datetime import date

        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["File"],
                properties={
                    "name": "Doc",
                    "dates": [date(2024, 1, 1), date(2024, 6, 1)],
                    "meta": {"created": date(2024, 9, 1), "rev": 3},
                },
            )
        )
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        props = data["nodes"][0]["properties"]
        assert props["dates"] == ["2024-01-01", "2024-06-01"]
        assert props["meta"] == {"created": "2024-09-01", "rev": 3}

    def test_include_properties_false_omits_field(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Thing"], properties={"description": "x"}))
        data = SigmaRenderer().graph_to_json(
            g, colour_by="type", size_by="connections", include_properties=False
        )
        node = data["nodes"][0]
        assert "properties" not in node

    def test_render_simple_excludes_properties_from_html(self):
        # Smoke test: render(..., simple=True) should not embed
        # property values in the output HTML.
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["File"],
                properties={"name": "Doc", "secret": "DO-NOT-EMBED-IN-THUMBNAIL"},
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "thumb.html"
            SigmaRenderer().render(g, filepath=str(path), simple=True)
            html = path.read_text(encoding="utf-8")
        assert "DO-NOT-EMBED-IN-THUMBNAIL" not in html

    def test_render_default_excludes_properties_from_html(self):
        # Default is include_properties=False — properties stay in the
        # source graph but the HTML payload omits them. Keeps output
        # size manageable on metadata-rich crates.
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["File"],
                properties={"name": "Doc", "secret": "DO-NOT-EMBED-BY-DEFAULT"},
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.html"
            SigmaRenderer().render(g, filepath=str(path))
            html = path.read_text(encoding="utf-8")
        assert "DO-NOT-EMBED-BY-DEFAULT" not in html

    def test_render_include_properties_true_embeds_in_html(self):
        # Opt-in: include_properties=True ships entity properties in the
        # JSON payload (decompressed from the packed payload) so the
        # click-node details panel can render them.
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["File"],
                properties={"name": "Doc", "secret": "SHOULD-EMBED-WHEN-OPTED-IN"},
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.html"
            SigmaRenderer().render(g, filepath=str(path), include_properties=True)
            html = path.read_text(encoding="utf-8")
        data = _unpack_graph_data(html)
        assert data["nodes"][0]["properties"]["secret"] == "SHOULD-EMBED-WHEN-OPTED-IN"

    def test_render_simple_wins_over_include_properties_true(self):
        # Simple template has no panel — include_properties=True must be
        # ignored, not embedded.
        g = Graph()
        g._add_node(
            Entity(
                id="#a",
                types=["File"],
                properties={"name": "Doc", "secret": "SHOULD-NOT-LEAK-INTO-SIMPLE"},
            )
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "out.html"
            SigmaRenderer().render(g, filepath=str(path), simple=True, include_properties=True)
            html = path.read_text(encoding="utf-8")
        assert "SHOULD-NOT-LEAK-INTO-SIMPLE" not in html


class TestSerialisedEdgeType:
    """Edges in the JSON carry their relationship type so the JS side
    can group neighbours in the details panel."""

    def test_each_edge_has_type_field(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        for edge in data["edges"]:
            assert "type" in edge

    def test_edge_type_matches_relationship(self):
        g = _build_graph()
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        # _build_graph creates two "memberOf" edges.
        assert {edge["type"] for edge in data["edges"]} == {"memberOf"}

    def test_parallel_edges_with_different_types_both_appear(self):
        g = Graph()
        g._add_node(Entity(id="#x", types=["Person"], properties={"name": "X"}))
        g._add_node(Entity(id="#y", types=["Person"], properties={"name": "Y"}))
        g._add_edge(Relationship(source="#x", target="#y", type="knows"))
        g._add_edge(Relationship(source="#x", target="#y", type="employs"))
        data = SigmaRenderer().graph_to_json(g, colour_by="type", size_by="connections")
        types = [edge["type"] for edge in data["edges"]]
        assert sorted(types) == ["employs", "knows"]
