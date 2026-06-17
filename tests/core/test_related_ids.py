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


def _bruteforce_related_ids(g, entity_id, rel, direction):
    """Reference implementation: a full scan of _relationships (pre-index logic)."""
    out_ids = [r.target for r in g._relationships if r.source == entity_id and r.type == rel]
    in_ids = [r.source for r in g._relationships if r.target == entity_id and r.type == rel]
    ordered = {"out": out_ids, "in": in_ids, "any": out_ids + in_ids}[direction]
    seen: set[str] = set()
    result: list[str] = []
    for rid in ordered:
        if rid not in seen and rid in g._entities:
            seen.add(rid)
            result.append(rid)
    return result


def test_indexed_related_ids_matches_bruteforce_everywhere() -> None:
    # The adjacency index must produce results identical to a full scan
    # for every entity, relationship type, and direction — same ids, same order.
    g = _graph()
    for entity in g.entities:
        for rel in g.relationship_types:
            for direction in ("out", "in", "any"):
                assert g._related_ids(entity.id, rel, direction) == _bruteforce_related_ids(
                    g, entity.id, rel, direction
                )


def test_derived_graph_rebuilds_adjacency_from_its_own_edges() -> None:
    # A filtered graph must reflect only its own edges, not the parent's
    # cached index (guards against stale-index leakage through _build_derived_graph).
    g = _graph()
    g._related_ids("#bob", "worksFor", "out")  # populate parent's cache
    people_only = g.select(entity_types=["Person"])
    # worksFor links a Person to an Organisation, so it is filtered out of a
    # people-only subgraph; the relationship type should no longer be present.
    assert "worksFor" not in set(people_only.relationship_types)
