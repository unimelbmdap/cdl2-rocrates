"""Tests for layout progress feedback (`progress` flag + upfront message).

The layout step (`presentation.layout`) is a single blocking ForceAtlas2 call.
These tests cover the user-facing progress affordances added around it:

* an upfront stderr message naming the node count, gated by a ``progress``
  flag and a node-count threshold; and
* the ``verbose`` flag passed to ForceAtlas2 tracking that same gate.

ForceAtlas2 is faked (injected into ``sys.modules``) so the tests run fast and
deterministically whether or not the optional ``fa2`` package is installed.
"""

from __future__ import annotations

import sys
import types

import pytest

from crategraph.core import presentation
from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _build_graph(n_nodes: int) -> Graph:
    """A graph of *n_nodes* trivial nodes plus a couple of edges."""
    g = Graph()
    for i in range(n_nodes):
        g._add_node(Entity(id=f"#n{i}", types=["Thing"], properties={"name": f"n{i}"}))
    if n_nodes >= 2:
        g._add_edge(Relationship(source="#n0", target="#n1", type="links"))
    return g


class _FakeForceAtlas2:
    """Records the ``verbose`` kwarg and returns dummy positions instantly.

    Mimics the real ``fa2``: when ``verbose=True`` it dumps a timing summary to
    *stdout* (the live progress bar itself goes to stderr).
    """

    last_verbose: bool | None = None
    last_selfloops: int | None = None

    def __init__(self, **kwargs: object) -> None:
        self._verbose = bool(kwargs.get("verbose"))
        _FakeForceAtlas2.last_verbose = kwargs.get("verbose")  # type: ignore[assignment]

    def forceatlas2_networkx_layout(self, graph: object, iterations: int = 100) -> dict:
        import networkx as nx

        _FakeForceAtlas2.last_selfloops = nx.number_of_selfloops(graph)  # type: ignore[arg-type]
        if self._verbose:
            print("BarnesHut Approximation took 0.12 seconds")  # fa2 stdout noise
        return {node: (0.0, 0.0) for node in graph.nodes()}  # type: ignore[attr-defined]


@pytest.fixture
def fake_fa2(monkeypatch: pytest.MonkeyPatch) -> type[_FakeForceAtlas2]:
    """Inject a fake ``fa2`` module so ``from fa2 import ForceAtlas2`` is fast."""
    _FakeForceAtlas2.last_verbose = None
    module = types.ModuleType("fa2")
    module.ForceAtlas2 = _FakeForceAtlas2  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "fa2", module)
    return _FakeForceAtlas2


# Threshold-sized graphs reused across tests.
_LARGE = 2000  # == _LAYOUT_PROGRESS_MIN_NODES
_SMALL = 5


class TestLayoutMessage:
    def test_quiet_by_default_even_for_large_graph(self, fake_fa2, capsys):
        _build_graph(_LARGE).layout()
        assert capsys.readouterr().err == ""

    def test_progress_true_below_threshold_is_quiet(self, fake_fa2, capsys):
        _build_graph(_SMALL).layout(progress=True)
        assert capsys.readouterr().err == ""

    def test_progress_true_above_threshold_emits_message(self, fake_fa2, capsys):
        _build_graph(_LARGE).layout(progress=True)
        err = capsys.readouterr().err
        assert "2,000" in err
        assert "nodes" in err

    def test_fa2_stdout_timing_noise_is_suppressed(self, fake_fa2, capsys):
        # fa2's verbose timing summary goes to stdout, which Jupyter captures
        # into committed cell outputs; the progress bar (stderr) is what we want.
        _build_graph(_LARGE).layout(progress=True)
        out = capsys.readouterr().out
        assert out == ""

    def test_no_message_when_fa2_absent(self, monkeypatch, capsys):
        # ``import fa2`` raises -> no server-side layout actually runs (here it
        # raises; in pyvis the ImportError is caught and silently falls back to
        # client-side physics). The upfront message must NOT mislead by claiming
        # layout happened, so it is emitted only once fa2 is confirmed available.
        monkeypatch.setitem(sys.modules, "fa2", None)
        with pytest.raises(ImportError):
            _build_graph(_LARGE + 1).layout(progress=True)
        assert capsys.readouterr().err == ""


class TestLayoutVerboseFlag:
    def test_verbose_true_when_large_and_progress(self, fake_fa2):
        _build_graph(_LARGE).layout(progress=True)
        assert fake_fa2.last_verbose is True

    def test_verbose_false_when_progress_disabled(self, fake_fa2):
        _build_graph(_LARGE).layout(progress=False)
        assert fake_fa2.last_verbose is False

    def test_verbose_false_when_below_threshold(self, fake_fa2):
        _build_graph(_SMALL).layout(progress=True)
        assert fake_fa2.last_verbose is False


class TestSelfLoops:
    def test_selfloops_stripped_before_layout(self, fake_fa2):
        # Self-loops make fa2 warn ("non-zero diagonal") and inflate node mass;
        # they must be removed from the graph handed to fa2.
        g = _build_graph(_LARGE)
        g._add_edge(Relationship(source="#n0", target="#n0", type="mentions"))
        g.layout(progress=True)
        assert fake_fa2.last_selfloops == 0


class TestProgressStream:
    def test_message_on_stderr_outside_notebook(self, fake_fa2, capsys):
        _build_graph(_LARGE).layout(progress=True)
        captured = capsys.readouterr()
        assert "Laying out" in captured.err
        assert "Laying out" not in captured.out

    def test_message_on_stdout_in_notebook(self, fake_fa2, capsys, monkeypatch):
        # In Jupyter, stderr is shown on an alarming red background, so progress
        # is routed to stdout instead.
        monkeypatch.setattr(presentation, "_in_notebook", lambda: True)
        _build_graph(_LARGE).layout(progress=True)
        captured = capsys.readouterr()
        assert "Laying out" in captured.out
        assert "Laying out" not in captured.err


class TestVisualiseForwardsProgress:
    def test_visualise_defaults_to_progress_on(self, fake_fa2, capsys):
        _build_graph(_LARGE).visualise(renderer="svg")
        assert "2,000" in capsys.readouterr().err

    def test_visualise_progress_false_is_silent(self, fake_fa2, capsys):
        _build_graph(_LARGE).visualise(renderer="svg", progress=False)
        assert capsys.readouterr().err == ""
