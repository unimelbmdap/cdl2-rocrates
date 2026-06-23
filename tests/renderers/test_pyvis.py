"""Tests for PyvisRenderer and Graph.visualise()."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

pyvis = pytest.importorskip("pyvis", reason="pyvis not installed")
from pyvis.network import Network  # noqa: E402

from crategraph.core.graph import Graph  # noqa: E402
from crategraph.core.models import Entity, Relationship  # noqa: E402
from crategraph.renderers.pyvis import PyvisRenderer  # noqa: E402


def _build_graph() -> Graph:
    g = Graph()
    g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
    g._add_node(Entity(id="#b", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#c", types=["Organisation"], properties={"name": "Uni of Melbourne"}))
    g._add_edge(Relationship(source="#a", target="#c", type="memberOf"))
    g._add_edge(Relationship(source="#b", target="#c", type="memberOf"))
    return g


class TestPyvisRenderer:
    def test_returns_network(self):
        g = _build_graph()
        renderer = PyvisRenderer()
        result = renderer.render(g)
        assert isinstance(result, Network)

    def test_node_count(self):
        g = _build_graph()
        result = PyvisRenderer().render(g)
        assert len(result.nodes) == 3

    def test_edge_count(self):
        g = _build_graph()
        result = PyvisRenderer().render(g)
        assert len(result.edges) == 2

    def test_node_labels(self):
        g = _build_graph()
        result = PyvisRenderer().render(g)
        labels = {n["label"] for n in result.nodes}
        assert "Alice" in labels
        assert "Bob" in labels
        assert "Uni of Melbourne" in labels

    def test_nodes_coloured_by_type(self):
        g = _build_graph()
        result = PyvisRenderer().render(g)
        colours = {n["id"]: n["color"] for n in result.nodes}
        # Two Person nodes should share a colour, Organisation differs.
        assert colours["#a"] == colours["#b"]
        assert colours["#a"] != colours["#c"]

    def test_save_to_filepath(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "test.html")
            result = PyvisRenderer().render(g, filepath=filepath)
            assert result == filepath
            content = Path(filepath).read_text()
            assert "Alice" in content
            assert "vis-network" in content.lower() or "vis.Network" in content

    def test_empty_graph(self):
        g = Graph()
        result = PyvisRenderer().render(g)
        assert isinstance(result, Network)
        assert len(result.nodes) == 0


class TestRendererDispatch:
    def test_explicit_pyvis_renderer(self):
        g = _build_graph()
        result = g.visualise(renderer="pyvis")
        assert isinstance(result, Network)

    def test_invalid_renderer_raises(self):
        import pytest

        g = _build_graph()
        with pytest.raises(ValueError, match="Unknown renderer"):
            g.visualise(renderer="bogus")


class TestPyvisColourByCommunity:
    def test_colour_by_community_runs(self):
        g = _build_graph()
        result = PyvisRenderer().render(g, colour_by="community")
        assert isinstance(result, Network)
        assert len(result.nodes) == 3

    def test_colour_by_community_assigns_colours(self):
        g = _build_graph()
        result = PyvisRenderer().render(g, colour_by="community")
        colours = {n["id"]: n["color"] for n in result.nodes}
        # All nodes should have a colour assigned.
        for colour in colours.values():
            assert colour.startswith("#")


class TestPyvisColourByGeneric:
    def test_unknown_property_all_same_colour(self):
        g = _build_graph()
        result = PyvisRenderer().render(g, colour_by="nonexistent")
        colours = {n["color"] for n in result.nodes}
        assert len(colours) == 1  # all "(no value)"

    def test_colour_by_arbitrary_property(self):
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "A", "dept": "IT"}))
        g._add_node(Entity(id="#b", types=["Person"], properties={"name": "B", "dept": "IT"}))
        g._add_node(Entity(id="#c", types=["Person"], properties={"name": "C", "dept": "HR"}))
        g._add_edge(Relationship(source="#a", target="#b", type="knows"))
        result = PyvisRenderer().render(g, colour_by="dept")
        colours = {n["id"]: n["color"] for n in result.nodes}
        assert colours["#a"] == colours["#b"]
        assert colours["#a"] != colours["#c"]


class TestBidirectionalEdges:
    def test_bidirectional_edge_no_arrows(self):
        """Collapsed bidirectional edges should have no arrow."""
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
        renderer = PyvisRenderer()
        net = renderer.render(g)
        edges = net.get_edges()
        assert len(edges) == 1
        assert edges[0].get("arrows") == ""

    def test_unidirectional_edge_keeps_arrows(self):
        """Normal or collapsed unidirectional edges keep default arrows."""
        g = Graph()
        g._add_node(Entity(id="#a", types=["Person"], properties={"name": "Alice"}))
        g._add_node(Entity(id="#b", types=["Organisation"], properties={"name": "CSIRO"}))
        g._add_edge(Relationship(source="#a", target="#b", type="author"))
        renderer = PyvisRenderer()
        net = renderer.render(g)
        edges = net.get_edges()
        assert len(edges) == 1
        assert "arrows" not in edges[0] or edges[0]["arrows"] != ""


class TestGraphVisualise:
    def test_returns_network(self):
        g = _build_graph()
        result = g.visualise(renderer="pyvis")
        assert isinstance(result, Network)

    def test_filepath_kwarg(self):
        g = _build_graph()
        with tempfile.TemporaryDirectory() as tmpdir:
            filepath = str(Path(tmpdir) / "output.html")
            result = g.visualise(renderer="pyvis", filepath=filepath)
            assert result == filepath
            assert Path(filepath).exists()

    def test_merged_graph_visualise(self):
        g = _build_graph()
        merged = g.merge_nodes(by="type")
        result = merged.visualise(renderer="pyvis")
        assert isinstance(result, Network)
        assert len(result.nodes) == 2  # Person, Organisation


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

    def test_edge_width_none_preserves_legacy_log1p_formula(self):
        """When edge_width=None, the pre-existing hardcoded path runs.

        Uses weight=1 edges (where the legacy formula gives 1 but the
        helper gives ~2.386) to *discriminate* the two paths — not just
        agree numerically by coincidence. Also asserts byte-identity
        with a no-argument call so future drift between ``None`` and
        "parameter absent" is caught.
        """
        import math

        from crategraph.core.graph import Graph
        from crategraph.core.models import Entity, Relationship
        from crategraph.renderers.pyvis import PyvisRenderer

        g = Graph()
        g._add_node(Entity(id="#a", types=["T"], properties={}))
        g._add_node(Entity(id="#b", types=["T"], properties={}))
        g._add_node(Entity(id="#c", types=["T"], properties={}))
        g._add_node(Entity(id="#d", types=["T"], properties={}))
        # weight=5 and weight=20 → both use log1p formula.
        g._add_edge(Relationship(source="#a", target="#b", type="r", properties={"weight": 5}))
        g._add_edge(Relationship(source="#b", target="#c", type="r", properties={"weight": 20}))
        # weight=1 → legacy fires `else` branch (width=1); helper would give 1 + 2*log1p(1).
        g._add_edge(Relationship(source="#c", target="#d", type="r", properties={"weight": 1}))

        net_none = PyvisRenderer().render(g, edge_width=None, notebook=False)
        widths_none = [e["width"] for e in net_none.edges]
        assert widths_none == [
            1 + 2 * math.log1p(5),
            1 + 2 * math.log1p(20),
            1,  # legacy else-branch — helper would give ~2.386 here
        ]

        # Byte-identity with no-argument call — catches drift between
        # ``edge_width=None`` and "parameter absent".
        net_default = PyvisRenderer().render(g, notebook=False)
        assert [e["width"] for e in net_default.edges] == widths_none

    def test_edge_width_scalar_overrides_every_edge(self):
        from crategraph.renderers.pyvis import PyvisRenderer

        g = self._graph()
        net = PyvisRenderer().render(g, edge_width=3, notebook=False)
        assert [e["width"] for e in net.edges] == [3.0, 3.0]

    def test_edge_width_attribute_applies_unified_formula(self):
        import math

        from crategraph.renderers.pyvis import PyvisRenderer

        g = self._graph()
        net = PyvisRenderer().render(g, edge_width="weight", notebook=False)
        # Unified formula produces the same output as the legacy pyvis one
        # for weight values — this locks the equivalence.
        assert [e["width"] for e in net.edges] == [
            1 + 2 * math.log1p(5),
            1 + 2 * math.log1p(20),
        ]


class TestOverwriteGuard:
    def test_raises_when_file_exists_and_overwrite_false(self, tmp_path):
        out = tmp_path / "out.html"
        out.write_text("existing")
        with pytest.raises(FileExistsError):
            PyvisRenderer().render(_build_graph(), filepath=str(out))
        assert out.read_text() == "existing"

    def test_overwrite_true_replaces_file(self, tmp_path):
        out = tmp_path / "out.html"
        out.write_text("existing")
        result = PyvisRenderer().render(_build_graph(), filepath=str(out), overwrite=True)
        assert result == str(out)
        assert out.read_text() != "existing"
