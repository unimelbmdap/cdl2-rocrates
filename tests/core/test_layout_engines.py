"""Tests for the pluggable layout engine registry.

Covers registry ordering/resolution, the rust ForceAtlas2 engine (real
computation, determinism, progress callback), and the NetworkX fallback
engine (settings translation, dropped-settings warning, availability probe).
"""

import sys
from unittest import mock

import pytest

from crategraph.core.layout_engines import ENGINES, resolve_engine

TRIANGLE = (3, [(0, 1), (1, 2), (2, 0)])


def test_registry_order_and_names():
    assert [e.name for e in ENGINES] == ["forceatlas2", "nx"]


def test_resolve_default_prefers_rust_when_available():
    assert resolve_engine(None).name == "forceatlas2"  # dev env has the package


def test_resolve_unknown_engine_lists_options():
    with pytest.raises(ValueError, match=r"forceatlas2.*nx"):
        resolve_engine("bogus")


def test_rust_engine_computes_deterministic_layout():
    engine = resolve_engine("forceatlas2")
    n, edges = TRIANGLE
    settings = {"gravity": 0.3, "scalingRatio": 10, "strongGravityMode": True}
    a = engine.compute(n, edges, iterations=20, settings=settings, progress_cb=None)
    b = engine.compute(n, edges, iterations=20, settings=settings, progress_cb=None)
    assert set(a) == {0, 1, 2} and a == b  # index-keyed, reproducible


def test_rust_engine_progress_callback_fires():
    engine = resolve_engine("forceatlas2")
    calls = []
    engine.compute(
        *TRIANGLE[:1],
        TRIANGLE[1],
        iterations=5,
        settings={},
        progress_cb=lambda i, t: calls.append((i, t)),
    )
    assert calls[-1] == (5, 5)


def test_resolve_falls_back_to_nx_when_rust_missing():
    with mock.patch.dict(sys.modules, {"crategraph_forceatlas2": None}):
        engine = resolve_engine(None)
        assert engine.name == "nx"


def test_nx_engine_maps_and_drops_settings(monkeypatch):
    import networkx as nx

    engine = resolve_engine("nx")
    n, edges = TRIANGLE

    original = nx.forceatlas2_layout
    captured = {}

    def spy(graph, *args, **kwargs):
        captured.update(kwargs)
        return original(graph, *args, **kwargs)

    monkeypatch.setattr(nx, "forceatlas2_layout", spy)

    with pytest.warns(UserWarning, match=r"barnesHutOptimize.*barnesHutTheta.*slowDown") as record:
        pos = engine.compute(
            n,
            edges,
            iterations=10,
            settings={
                "gravity": 0.3,
                "strongGravityMode": True,
                "scalingRatio": 10,
                "barnesHutTheta": 0.9,
                "barnesHutOptimize": True,
                "slowDown": 1,
            },
            progress_cb=None,
        )
    assert set(pos) == {0, 1, 2}
    # A single warning pinning every dropped key present in this call.
    (warning,) = [w for w in record.list if issubclass(w.category, UserWarning)]
    message = str(warning.message)
    assert "barnesHutOptimize" in message
    assert "barnesHutTheta" in message
    assert "slowDown" in message
    # A mapped key (scalingRatio -> scaling_ratio) actually reaches nx.
    assert captured["scaling_ratio"] == 10


def test_nx_engine_unavailable_without_forceatlas2_layout():
    import networkx as nx

    engine = resolve_engine("nx")
    with mock.patch.object(nx, "forceatlas2_layout", None, create=True):
        ok, _hint = engine.available()
        assert ok is False
        with pytest.raises(ValueError, match="install"):
            resolve_engine("nx")


# --- presentation.layout() dispatch: profile, precedence, id<->index remap ---


def _spy_engine(monkeypatch):
    """Register a spy engine capturing compute() kwargs; returns the capture dict."""
    from crategraph.core import layout_engines as le

    captured = {}

    class Spy(le.LayoutEngine):
        name = "spy"

        def available(self):
            return (True, "spy")

        def compute(self, n_nodes, edges, *, iterations, settings, progress_cb):
            captured.update(n=n_nodes, edges=edges, iterations=iterations, settings=settings)
            return {i: (float(i), 0.0) for i in range(n_nodes)}

    monkeypatch.setattr(le, "ENGINES", [Spy()])
    return captured


def _build_graph(n_nodes, relationships=()):
    """An in-memory graph of *n_nodes* trivial nodes plus the given (src, tgt) edges."""
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity, Relationship

    g = Graph()
    for i in range(n_nodes):
        g._add_node(Entity(id=f"#n{i}", types=["Thing"], properties={"name": f"n{i}"}))
    for source, target in relationships:
        g._add_edge(Relationship(source=source, target=target, type="links"))
    return g


def test_profile_defaults_reach_engine(monkeypatch, people_graph):
    captured = _spy_engine(monkeypatch)
    people_graph.layout()
    s = captured["settings"]
    assert s["gravity"] == 0.3 and s["scalingRatio"] == 10
    assert s["strongGravityMode"] is True and s["slowDown"] == 1
    assert s["outboundAttractionDistribution"] is False
    assert s["barnesHutOptimize"] is False  # flips only above 2000 nodes
    assert s["barnesHutTheta"] == 0.5


def test_precedence_named_beats_dict_beats_profile(monkeypatch, people_graph):
    captured = _spy_engine(monkeypatch)
    people_graph.layout(gravity=0.5, layout_settings={"gravity": 0.9, "barnesHutTheta": 0.7})
    assert captured["settings"]["gravity"] == 0.5  # named wins
    assert captured["settings"]["barnesHutTheta"] == 0.7  # dict beats profile
    people_graph.layout(layout_settings={"gravity": 0.9})
    assert captured["settings"]["gravity"] == 0.9  # dict beats profile when named is None


def test_iterations_named_beats_dict_and_never_reaches_settings(monkeypatch, people_graph):
    captured = _spy_engine(monkeypatch)
    people_graph.layout(iterations=7, layout_settings={"iterations": 99})
    assert captured["iterations"] == 7
    assert "iterations" not in captured["settings"]


def test_iterations_from_dict_beats_formula(monkeypatch, people_graph):
    captured = _spy_engine(monkeypatch)
    people_graph.layout(layout_settings={"iterations": 33})
    assert captured["iterations"] == 33
    assert "iterations" not in captured["settings"]


def test_iterations_formula_default(monkeypatch, people_graph):
    captured = _spy_engine(monkeypatch)
    people_graph.layout()
    n = len(people_graph.entities)
    assert captured["iterations"] == min(200, 50 + n // 100)


def test_layout_returns_entity_ids_and_drops_self_loops(monkeypatch, people_graph):
    captured = _spy_engine(monkeypatch)
    pos = people_graph.layout()
    assert set(pos) == {e.id for e in people_graph.entities}
    assert all(u != v for u, v in captured["edges"])


def test_isolated_node_present_in_output(monkeypatch):
    captured = _spy_engine(monkeypatch)
    g = _build_graph(3, [("#n0", "#n1")])  # #n2 has no relationships
    pos = g.layout()
    assert "#n2" in pos
    assert captured["n"] == 3


def test_parallel_relationships_deduped_at_engine_boundary(monkeypatch):
    captured = _spy_engine(monkeypatch)
    g = _build_graph(2, [("#n0", "#n1"), ("#n0", "#n1"), ("#n1", "#n0")])
    g.layout()
    edges = captured["edges"]
    assert len(edges) == len({tuple(sorted(e)) for e in edges}) == 1


def test_self_loops_never_reach_engine(monkeypatch):
    captured = _spy_engine(monkeypatch)
    g = _build_graph(2, [("#n0", "#n0"), ("#n0", "#n1")])
    pos = g.layout()
    assert all(u != v for u, v in captured["edges"])
    assert set(pos) == {"#n0", "#n1"}  # the self-looping node still gets a position


@pytest.mark.skipif(not ENGINES[0].available()[0], reason="rust forceatlas2 engine not available")
def test_topology_safety_net_through_rust_engine():
    """The self-loop/isolated-node/parallel-edge handling in presentation.layout
    also has to survive the real rust engine, not just the spy — this exercises
    the whole pipeline end-to-end instead of stopping at the compute() boundary.
    """
    g = _build_graph(
        3,
        [
            ("#n0", "#n0"),  # self-loop
            ("#n0", "#n1"),
            ("#n0", "#n1"),  # parallel edge
            # #n2 is left isolated
        ],
    )
    pos = g.layout(engine="forceatlas2")
    assert set(pos) == {"#n0", "#n1", "#n2"}


# --- visualise()/graph_to_json() layout kwarg threading ---


def test_visualise_threads_gravity_and_layout_settings_to_engine(monkeypatch, tmp_path):
    captured = _spy_engine(monkeypatch)
    g = _build_graph(3, [("#n0", "#n1")])
    filepath = str(tmp_path / "out.svg")
    g.visualise(
        renderer="svg",
        gravity=0.1,
        layout_settings={"barnesHutTheta": 0.9},
        filepath=filepath,
    )
    settings = captured["settings"]
    assert settings["gravity"] == 0.1
    assert settings["barnesHutTheta"] == 0.9


def test_graph_to_json_threads_gravity_to_engine(monkeypatch):
    from crategraph.renderers.sigma import SigmaRenderer

    captured = _spy_engine(monkeypatch)
    g = _build_graph(3, [("#n0", "#n1")])
    SigmaRenderer().graph_to_json(g, gravity=0.2)
    assert captured["settings"]["gravity"] == 0.2


def test_visualise_3d_with_layout_kwargs_warns_ignored(monkeypatch, tmp_path):
    g = _build_graph(3, [("#n0", "#n1")])
    filepath = str(tmp_path / "out.html")
    with pytest.warns(UserWarning, match="ignored.*client-side"):
        g.visualise(renderer="3d", gravity=0.2, filepath=filepath)


def test_visualise_3d_without_layout_kwargs_does_not_warn(recwarn, tmp_path):
    g = _build_graph(3, [("#n0", "#n1")])
    filepath = str(tmp_path / "out.html")
    g.visualise(renderer="3d", filepath=filepath)
    assert not any(
        "ignored" in str(w.message) and "client-side" in str(w.message) for w in recwarn.list
    )
