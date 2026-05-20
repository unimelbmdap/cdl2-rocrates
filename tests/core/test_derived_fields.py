"""Tests for Graph.derived_fields registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


def test_derived_fields_empty_by_default() -> None:
    g = Crate(str(FIXTURE))
    assert dict(g.derived_fields) == {}


def test_derived_fields_is_read_only() -> None:
    g = Crate(str(FIXTURE))
    with pytest.raises(TypeError):
        g.derived_fields["x"] = "y"


def test_derived_fields_attr_exists_on_build_derived_graph_path() -> None:
    """`_build_derived_graph` uses Graph.__new__ — the attr must still exist."""
    g = Crate(str(FIXTURE))
    derived = g.select(entity_types=["Person"])
    # select() routes through _build_derived_graph; reading the registry
    # must not AttributeError, and must be empty (no annotation yet).
    assert dict(derived.derived_fields) == {}


def test_relationship_derived_fields_empty_by_default() -> None:
    g = Crate(str(FIXTURE))
    assert dict(g.relationship_derived_fields) == {}


def test_relationship_derived_fields_is_read_only() -> None:
    g = Crate(str(FIXTURE))
    with pytest.raises(TypeError):
        g.relationship_derived_fields["x"] = "y"


def test_relationship_derived_fields_attr_exists_on_build_derived_graph_path() -> None:
    g = Crate(str(FIXTURE))
    derived = g.select(entity_types=["Person"])
    assert dict(derived.relationship_derived_fields) == {}


def test_relationship_provenance_survives_select_where() -> None:
    g = Crate(str(FIXTURE)).annotate_relationships(source_label=lambda r: r.source.label)
    out = g.select(entity_types=["Person"]).where()
    assert "source_label" in out.relationship_derived_fields


def test_relationship_provenance_dropped_by_collapse_edges() -> None:
    g = Crate(str(FIXTURE)).annotate_relationships(source_label=lambda r: r.source.label)
    assert "source_label" not in g.collapse_edges().relationship_derived_fields


def test_relationship_provenance_dropped_by_merge_nodes() -> None:
    g = Crate(str(FIXTURE)).annotate_relationships(source_label=lambda r: r.source.label)
    assert "source_label" not in g.merge_nodes(by="type").relationship_derived_fields
