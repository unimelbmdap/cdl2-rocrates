"""Introspective parity: EntityView is a strict superset of Entity's read surface.

Programmatically collects Entity's public read surface (dataclass field names
plus public ``property`` descriptors) and asserts a wrapped EntityView exposes
every one of them with an agreeing value. This pins the "view is a strict
superset of Entity's read surface" contract — a new Entity property fails
here until the view learns it too.

RelationshipView is deliberately NOT covered by an equivalent test: its
``source``/``target`` return ``EntityView`` (graph-traversal endpoints), a
documented divergence from any bare-model surface, not an omission to pin.
"""

from __future__ import annotations

import dataclasses

from crategraph.core.models import Entity
from crategraph.core.views import EntityView


def _entity_public_read_surface() -> list[str]:
    """Entity's dataclass field names plus its public property names."""
    field_names = [f.name for f in dataclasses.fields(Entity)]
    property_names = [
        name
        for name, value in vars(Entity).items()
        if isinstance(value, property) and not name.startswith("_")
    ]
    return field_names + property_names


def _fixture_entity() -> Entity:
    """Multi-typed, with name, title, and source; a File type so has_data is True."""
    return Entity(
        id="#doc1",
        types=("File", "CreativeWork"),
        properties={"name": "Field Notes", "title": "Field Notes (scan)"},
        source="crate.zip",
    )


def test_entity_view_exposes_every_public_entity_attribute_with_agreeing_value() -> None:
    entity = _fixture_entity()
    view = EntityView(entity)
    attrs = _entity_public_read_surface()

    assert attrs  # sanity: reflection actually found Entity's read surface

    for attr in attrs:
        assert hasattr(view, attr), f"EntityView is missing Entity's {attr!r}"
        assert getattr(view, attr) == getattr(entity, attr), (
            f"EntityView.{attr} disagrees with Entity.{attr}"
        )


def test_entity_view_entity_returns_wrapped_record() -> None:
    entity = _fixture_entity()
    view = EntityView(entity)
    assert view.entity is entity
    assert isinstance(view.entity, Entity)


def test_entity_view_repr_shape_matches_entity() -> None:
    entity = _fixture_entity()
    view = EntityView(entity)
    # Same field shape as Entity's repr; only the class name differs.
    assert repr(view) == f"EntityView({entity.type!r}, {entity.name!r}, id={entity.id!r})"
    assert repr(view).replace("EntityView", "Entity", 1) == repr(entity)


def test_entity_view_repr_html_matches_entity_wrapper() -> None:
    from html import escape

    entity = _fixture_entity()
    view = EntityView(entity)
    assert view._repr_html_() == f"<pre>{escape(repr(view))}</pre>"
    assert view._repr_html_() == entity._repr_html_().replace("Entity(", "EntityView(", 1)


def test_entity_view_repr_survives_inside_a_tuple_list() -> None:
    # most_connected() will return list[tuple[EntityView, int]] after the flip;
    # pin the tuple/list repr shape the cheatsheet relies on.
    view = EntityView(_fixture_entity())
    assert repr([(view, 3)]) == f"[({view!r}, 3)]"
