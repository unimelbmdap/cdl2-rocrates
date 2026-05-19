"""Tests for crategraph.core.views — CardinalityError, EntityView, Related."""

from __future__ import annotations

from crategraph.core.views import CardinalityError


def test_cardinality_error_is_a_value_error() -> None:
    err = CardinalityError("too many")
    assert isinstance(err, ValueError)
    assert str(err) == "too many"
