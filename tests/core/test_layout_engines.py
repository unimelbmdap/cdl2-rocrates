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


def test_nx_engine_maps_and_drops_settings():
    engine = resolve_engine("nx")
    n, edges = TRIANGLE
    with pytest.warns(UserWarning, match="adjustSizes"):
        pos = engine.compute(
            n,
            edges,
            iterations=10,
            settings={
                "gravity": 0.3,
                "strongGravityMode": True,
                "scalingRatio": 10,
                "adjustSizes": True,
                "barnesHutTheta": 0.9,
                "barnesHutOptimize": True,
                "slowDown": 1,
            },
            progress_cb=None,
        )
    assert set(pos) == {0, 1, 2}


def test_nx_engine_unavailable_without_forceatlas2_layout():
    import networkx as nx

    engine = resolve_engine("nx")
    with mock.patch.object(nx, "forceatlas2_layout", None, create=True):
        ok, _hint = engine.available()
        assert ok is False
        with pytest.raises(ValueError, match="install"):
            resolve_engine("nx")
