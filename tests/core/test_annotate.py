"""Tests for Graph.annotate_entities."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


def _g():
    return Crate(str(FIXTURE))


def test_annotate_adds_field_from_related_entity() -> None:
    g = _g()
    tagged = g.annotate_entities(
        org=lambda e: e.related("worksFor").join("name"),
    )
    bob = tagged._entities["#bob"]
    assert "org" in bob.properties
    assert bob.properties["org"]  # non-empty for an entity that has worksFor


def test_annotate_is_immutable() -> None:
    g = _g()
    g.annotate_entities(x=lambda e: "v")
    assert all("x" not in ent.properties for ent in g._entities.values())


def test_annotate_registers_provenance() -> None:
    g = _g()

    def org_label(e):
        return e.related("worksFor").join("name")

    tagged = g.annotate_entities(org=org_label, flag=lambda e: True)
    assert tagged.derived_fields["org"] == "org_label"
    assert tagged.derived_fields["flag"] is None  # anonymous lambda


def test_annotate_two_phase_fields_do_not_see_each_other() -> None:
    g = _g()
    tagged = g.annotate_entities(
        a=lambda e: "A",
        b=lambda e: e.properties.get("a", "no-a"),
    )
    assert all(ent.properties["b"] == "no-a" for ent in tagged._entities.values())


def test_annotate_collision_overwrites_and_marks_derived() -> None:
    g = _g()
    tagged = g.annotate_entities(name=lambda e: "OVERWRITTEN")
    assert all(ent.properties["name"] == "OVERWRITTEN" for ent in tagged._entities.values())
    assert "name" in tagged.derived_fields


def test_annotate_callable_error_is_contextualised() -> None:
    g = _g()

    def boom(e):
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match=r"field 'bad'.*entity"):
        g.annotate_entities(bad=boom)


def test_annotate_non_runtime_error_surfaces_as_chained_runtime_error() -> None:
    """A KeyError in a callable becomes a contextual RuntimeError with cause."""
    g = _g()

    def bad(e):
        raise KeyError("missing")

    with pytest.raises(RuntimeError) as excinfo:
        g.annotate_entities(bad=bad)
    assert isinstance(excinfo.value.__cause__, KeyError)
    assert "field 'bad'" in str(excinfo.value)


def test_annotate_survives_select_then_expand() -> None:
    """Regression: derived property values must NOT be lost via expand().

    expand() rebuilds from graph._root; annotate_entities resets _root
    to itself so the annotated full graph is the expansion baseline.
    """
    g = _g().annotate_entities(x=lambda e: "v")
    out = g.select(id="#alice").expand()
    assert out._entities["#alice"].properties["x"] == "v"
    assert "x" in out.derived_fields


def test_provenance_survives_select_where() -> None:
    g = _g().annotate_entities(org=lambda e: e.related("worksFor").join("name"))
    out = g.select(entity_types=["Person"]).where()
    assert "org" in out.derived_fields


def test_provenance_survives_collapse_edges() -> None:
    g = _g().annotate_entities(org=lambda e: "x")
    assert "org" in g.collapse_edges().derived_fields


def test_provenance_dropped_by_merge_nodes() -> None:
    g = _g().annotate_entities(org=lambda e: "x")
    assert "org" not in g.merge_nodes(by="type").derived_fields
