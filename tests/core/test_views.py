"""Tests for crategraph.core.views — CardinalityError, EntityView, Related."""

from __future__ import annotations

import pytest

from crategraph.core.models import Entity
from crategraph.core.views import CardinalityError, EntityView, Related


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


def _views(*specs):
    return [EntityView(Entity(id=i, properties=p)) for i, p in specs]


def test_related_protocols() -> None:
    r = Related(_views(("a", {"name": "A"}), ("b", {"name": "B"})))
    assert len(r) == 2
    assert bool(r) is True
    assert [v.id for v in r] == ["a", "b"]
    assert bool(Related([])) is False
    assert len(Related([])) == 0


def test_related_first_key_none_returns_view_or_default() -> None:
    r = Related(_views(("a", {}), ("b", {})))
    assert r.first().id == "a"
    assert Related([]).first(default="x") == "x"


def test_related_first_projects_and_skips_missing() -> None:
    r = Related(_views(("a", {}), ("b", {"name": "B"})))
    assert r.first("name") == "B"  # 'a' has no name -> skipped
    assert r.first("name", default="?") == "B"
    assert Related(_views(("a", {}))).first("name", default="?") == "?"


def test_related_first_callable_key() -> None:
    r = Related(_views(("a", {"n": 1}), ("b", {"n": 2})))
    assert r.first(lambda v: v.properties.get("n")) == 1


def test_related_first_strict_raises_on_multiple() -> None:
    r = Related(_views(("a", {"name": "A"}), ("b", {"name": "B"})))
    with pytest.raises(CardinalityError):
        r.first("name", strict=True)
    # strict counts related entities, not projected values:
    one = Related(_views(("a", {"name": "A"})))
    assert one.first("name", strict=True) == "A"


def test_related_join_label_default_dedup_sort() -> None:
    r = Related(_views(("a", {"name": "B"}), ("b", {"name": "A"}), ("c", {"name": "A"})))
    # key="name": deduped + sorted by default, ", " join
    assert r.join("name") == "A, B"
    assert Related([]).join("name") is None
    assert Related([]).join("name", default="None") == "None"


def test_related_join_key_none_uses_label() -> None:
    r = Related(_views(("a", {"name": "Zed"}), ("b", {"name": "Amy"})))
    assert r.join() == "Amy, Zed"  # labels, sorted+deduped


def test_related_join_str_coerces_and_respects_flags() -> None:
    r = Related(_views(("a", {"n": 2}), ("b", {"n": 1}), ("c", {"n": 1})))
    assert r.join("n") == "1, 2"  # str-coerced, unique, sorted
    assert r.join("n", unique=False, sort=False) == "2, 1, 1"
    assert r.join("n", sep="|", sort=True, unique=True) == "1|2"
