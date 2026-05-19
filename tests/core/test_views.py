"""Tests for crategraph.core.views — CardinalityError, EntityView, Related."""

from __future__ import annotations

import pytest

from crategraph.core.models import Entity
from crategraph.core.views import CardinalityError, EntityView


def test_cardinality_error_is_a_value_error() -> None:
    err = CardinalityError("too many")
    assert isinstance(err, ValueError)
    assert str(err) == "too many"


def test_entity_view_record_style_fields() -> None:
    e = EntityView(Entity(id="x", types=("File", "Thing"), properties={"name": "Doc"}))
    assert e.id == "x"
    assert e.types == ("File", "Thing")
    assert e.type == "File"  # first type, NOT Entity.type's joined string
    assert e.name == "Doc"
    assert e.label == "Doc"


def test_entity_view_name_is_none_when_absent() -> None:
    e = EntityView(Entity(id="x", types=("File",), properties={}))
    assert e.name is None  # raw .get("name"), NOT Entity.name's id fallback
    assert e.type == "File"


def test_entity_view_type_empty_when_untyped() -> None:
    assert EntityView(Entity(id="x")).type == ""


def test_entity_view_properties_top_level_read_only() -> None:
    src = Entity(id="x", properties={"a": 1})
    e = EntityView(src)
    assert e.properties["a"] == 1
    with pytest.raises(TypeError):
        e.properties["a"] = 2
    assert src.properties == {"a": 1}  # source unmutated


def test_entity_view_properties_is_shallow_documented_limit() -> None:
    """Characterisation test: nested mutation DOES reach the source.

    This is the documented shallow boundary, asserted so it cannot
    drift silently.
    """
    src = Entity(id="x", properties={"keywords": ["a"]})
    e = EntityView(src)
    e.properties["keywords"].append("b")
    assert src.properties["keywords"] == ["a", "b"]
