"""Tests for Graph._related_ids — the adjacency primitive."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


def _graph():
    return Crate(str(FIXTURE))


def test_related_ids_out_direction() -> None:
    g = _graph()
    # #bob --worksFor--> #acme  (present in minimal-crate)
    assert g._related_ids("#bob", "worksFor", "out") == ["#acme"]


def test_related_ids_in_direction() -> None:
    g = _graph()
    assert "#bob" in g._related_ids("#acme", "worksFor", "in")


def test_related_ids_any_dedups_out_then_in() -> None:
    g = _graph()
    ids = g._related_ids("#bob", "worksFor", "any")
    assert ids == list(dict.fromkeys(ids))  # no duplicates, order preserved


def test_related_ids_unknown_type_raises_value_error() -> None:
    g = _graph()
    with pytest.raises(ValueError):
        g._related_ids("#bob", "no_such_rel_type", "out")


def test_related_ids_known_type_no_edges_returns_empty() -> None:
    g = _graph()
    # worksFor exists in the graph, but #acme has no outgoing worksFor
    assert g._related_ids("#acme", "worksFor", "out") == []


def test_related_ids_invalid_direction_raises() -> None:
    g = _graph()
    with pytest.raises(ValueError, match="direction"):
        g._related_ids("#bob", "worksFor", "sideways")
