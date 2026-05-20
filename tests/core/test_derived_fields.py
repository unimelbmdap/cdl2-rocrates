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
