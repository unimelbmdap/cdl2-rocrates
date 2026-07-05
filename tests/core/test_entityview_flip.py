"""Flip-focused suite: the four public entity accessors return EntityView.

Covers return types, traversal from each accessor (including the spec's
literal select(...).entities[0].related(...) success-criterion path),
equality/dedup across accessor calls, read-only properties, .entity
identity with the stored record, the entity_view alias, and
most_connected tuple-repr shape.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate
from crategraph.core.views import EntityView, Related

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


def _crate() -> Crate:
    return Crate(str(FIXTURE))


def test_entities_returns_views() -> None:
    crate = _crate()
    views = crate.entities
    assert views
    assert all(isinstance(v, EntityView) for v in views)


def test_files_returns_views() -> None:
    crate = _crate()
    assert all(isinstance(f, EntityView) for f in crate.files)


def test_get_returns_view() -> None:
    crate = _crate()
    view = crate.get("#bob")
    assert isinstance(view, EntityView)
    assert view.id == "#bob"
    assert view.graph is crate


def test_most_connected_returns_view_tuples() -> None:
    crate = _crate()
    top = crate.most_connected(n=1)
    assert top
    entity_view, degree = top[0]
    assert isinstance(entity_view, EntityView)
    assert isinstance(degree, int)


def test_traversal_from_entities_accessor() -> None:
    crate = _crate()
    bob = next(v for v in crate.entities if v.id == "#bob")
    assert "#acme" in [v.id for v in bob.related("worksFor")]


def test_traversal_from_get() -> None:
    crate = _crate()
    assert crate.get("#bob").has("worksFor") is True


def test_select_entities_related_success_criterion() -> None:
    """The spec's literal path: crate.select(...).entities[0].related(...)."""
    crate = _crate()
    sub = crate.select(entity_types=["Person", "Organisation"])
    # The subgraph keeps #bob --worksFor--> #acme, so the type validates and
    # the literal indexed form works regardless of which entity is first.
    assert isinstance(sub.entities[0].related("worksFor"), Related)
    bob = next(v for v in sub.entities if v.id == "#bob")
    assert "#acme" in [t.id for t in bob.related("worksFor")]


def test_equality_and_dedup_across_accessor_calls() -> None:
    crate = _crate()
    first_a = crate.entities[0]
    first_b = crate.entities[0]
    assert first_a == first_b  # value equality is the contract
    assert first_a is not first_b  # fresh views, no handle cache
    assert len(set(crate.entities)) == len(crate.entities)  # hashable, unique ids


def test_accessor_properties_are_read_only() -> None:
    crate = _crate()
    with pytest.raises(TypeError):
        crate.entities[0].properties["injected"] = 1


def test_entity_property_identity_with_stored_record() -> None:
    crate = _crate()
    first_id = next(iter(crate._entities))
    assert crate.entities[0].entity is crate._entities[first_id]


def test_entity_view_is_alias_of_get() -> None:
    crate = _crate()
    assert crate.entity_view("#bob") == crate.get("#bob")


def test_entity_view_missing_id_raises_keyerror() -> None:
    crate = _crate()
    with pytest.raises(KeyError, match="No entity with id"):
        crate.entity_view("#definitely-missing")


def test_most_connected_tuple_repr_shape() -> None:
    crate = _crate()
    top = crate.most_connected(n=1)
    entity_view, degree = top[0]
    assert repr(top) == f"[({entity_view!r}, {degree})]"
    assert repr(entity_view).startswith("EntityView(")
