"""Tests for layout progress feedback (`progress` flag + upfront message).

The layout step (`presentation.layout`) is a single blocking engine call.
These tests cover the user-facing progress affordances added around it:

* an upfront message naming the node count, gated by a ``progress`` flag and
  a node-count threshold in terminals;
* percentage lines (``layout N%``) at ~5% steps in terminals, driven by the
  engine's progress callback; and
* an inline display progress reporter in notebooks.

The engine is a spy (registered via the engine registry) that drives the
progress callback like a real iteration loop, so the tests run fast and
deterministically whether or not ``crategraph_forceatlas2`` is installed.
"""

from __future__ import annotations

import re
import sys

import pytest

from crategraph.core import layout_engines as le
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


class _SpyEngine(le.LayoutEngine):
    """Instant engine that drives ``progress_cb`` like a real iteration loop."""

    name = "spy"

    def available(self) -> tuple[bool, str]:
        return (True, "spy")

    def compute(self, n_nodes, edges, *, iterations, settings, progress_cb):
        if progress_cb is not None:
            for i in range(1, iterations + 1):
                progress_cb(i, iterations)
        return {i: (float(i), 0.0) for i in range(n_nodes)}


@pytest.fixture
def spy_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the spy the only registered engine."""
    monkeypatch.setattr(le, "ENGINES", [_SpyEngine()])


# Threshold-sized graphs reused across tests.
_LARGE = 2000  # == _LAYOUT_PROGRESS_MIN_NODES
_SMALL = 5

_PERCENT_LINE = re.compile(r"layout \d+%")


class TestLayoutMessage:
    def test_quiet_by_default_even_for_large_graph(self, spy_engine, capsys):
        _build_graph(_LARGE).layout()
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    def test_progress_true_below_threshold_is_quiet(self, spy_engine, capsys):
        _build_graph(_SMALL).layout(progress=True)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""

    def test_progress_true_above_threshold_emits_message(self, spy_engine, capsys):
        _build_graph(_LARGE).layout(progress=True)
        err = capsys.readouterr().err
        assert "2,000" in err
        assert "nodes" in err

    def test_percentage_lines_step_to_completion(self, spy_engine, capsys):
        _build_graph(_LARGE).layout(progress=True)
        lines = _PERCENT_LINE.findall(capsys.readouterr().err)
        assert lines, "expected percentage progress lines"
        assert lines[-1] == "layout 100%"
        assert len(lines) == len(set(lines))  # ~5% steps, no repeats


class TestNxFallback:
    def test_absent_rust_falls_back_with_slow_warning(self, monkeypatch, capsys):
        # Without the rust package, resolution falls through to the nx engine,
        # which warns-and-proceeds on large graphs (the old path raised
        # ImportError). Its layout call is stubbed out so the test is instant;
        # the warning is emitted by the engine before the call.
        import networkx as nx

        monkeypatch.setitem(sys.modules, "crategraph_forceatlas2", None)
        monkeypatch.setattr(
            nx,
            "forceatlas2_layout",
            lambda graph, **kwargs: {node: (0.0, 0.0) for node in graph.nodes()},
            raising=False,
        )
        with pytest.warns(UserWarning) as record:
            pos = _build_graph(_LARGE).layout(progress=True)
        messages = [str(warning.message) for warning in record]
        assert any("slow NetworkX fallback" in m for m in messages)
        assert len(pos) == _LARGE
        assert "2,000" in capsys.readouterr().err  # the size line still appears


class TestProgressStream:
    def test_progress_on_stderr_outside_notebook(self, spy_engine, capsys):
        _build_graph(_LARGE).layout(progress=True)
        captured = capsys.readouterr()
        assert "Laying out" in captured.err
        assert _PERCENT_LINE.search(captured.err)
        assert captured.out == ""

    def test_progress_uses_inline_reporter_in_notebook(self, spy_engine, capsys, monkeypatch):
        # In Jupyter, use an inline display progress bar rather than stdout or
        # stderr text.
        calls = []

        def fake_notebook_reporter(n_nodes, n_relationships):
            calls.append(("start", n_nodes, n_relationships))

            def report(i, total):
                calls.append((i, total))

            return report

        monkeypatch.setattr(presentation, "_in_notebook", lambda: True)
        monkeypatch.setattr(presentation, "_notebook_progress_reporter", fake_notebook_reporter)
        _build_graph(_LARGE).layout(progress=True)
        captured = capsys.readouterr()
        assert calls[0] == ("start", _LARGE, 1)
        assert calls[-1] == (70, 70)  # default iterations for 2,000 nodes
        assert captured.out == ""
        assert captured.err == ""


class TestVisualiseForwardsProgress:
    def test_visualise_defaults_to_progress_on(self, spy_engine, capsys):
        _build_graph(_LARGE).visualise(renderer="svg")
        assert "2,000" in capsys.readouterr().err

    def test_visualise_progress_false_is_silent(self, spy_engine, capsys):
        _build_graph(_LARGE).visualise(renderer="svg", progress=False)
        assert capsys.readouterr().err == ""
