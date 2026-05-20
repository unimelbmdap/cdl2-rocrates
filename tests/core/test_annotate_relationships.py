"""Tests for Graph.annotate_relationships."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


def _g():
    return Crate(str(FIXTURE))


def test_annotate_relationships_derives_from_type_and_endpoint_views() -> None:
    tagged = _g().annotate_relationships(
        endpoint_label=lambda r: f"{r.type}: {r.source.label} -> {r.target.label}",
    )
    works_for = next(rel for rel in tagged.relationships if rel.type == "worksFor")
    assert works_for.properties["endpoint_label"] == "worksFor: Bob Jones -> ACME Corp"


def test_annotate_relationships_endpoint_views_compose_with_related() -> None:
    tagged = _g().annotate_relationships(
        source_org=lambda r: r.source.related("worksFor").join("name"),
    )
    works_for = next(rel for rel in tagged.relationships if rel.type == "worksFor")
    assert works_for.properties["source_org"] == "ACME Corp"


def test_annotate_relationships_is_immutable() -> None:
    g = _g()
    g.annotate_relationships(x=lambda r: "v")
    assert all("x" not in rel.properties for rel in g.relationships)


def test_annotate_relationships_registers_provenance() -> None:
    g = _g()

    def endpoint(r):
        return r.target.label

    tagged = g.annotate_relationships(target_label=endpoint, flag=lambda r: True)
    assert tagged.relationship_derived_fields["target_label"] == "endpoint"
    assert tagged.relationship_derived_fields["flag"] is None


def test_annotate_relationships_two_phase_fields_do_not_see_each_other() -> None:
    tagged = _g().annotate_relationships(
        a=lambda r: "A",
        b=lambda r: r.properties.get("a", "no-a"),
    )
    assert all(rel.properties["b"] == "no-a" for rel in tagged.relationships)


def test_annotate_relationships_collision_overwrites_and_marks_derived() -> None:
    tagged = _g().annotate_relationships(description=lambda r: "OVERWRITTEN")
    superior = next(rel for rel in tagged.relationships if rel.type == "Superior")
    assert superior.properties["description"] == "OVERWRITTEN"
    assert "description" in tagged.relationship_derived_fields


def test_annotate_relationships_callable_error_is_contextualised() -> None:
    def boom(r):
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError, match=r"field 'bad'.*relationship"):
        _g().annotate_relationships(bad=boom)


def test_annotate_relationships_non_runtime_error_surfaces_as_chained_runtime_error() -> None:
    def bad(r):
        raise KeyError("missing")

    with pytest.raises(RuntimeError) as excinfo:
        _g().annotate_relationships(bad=bad)
    assert isinstance(excinfo.value.__cause__, KeyError)
    assert "field 'bad'" in str(excinfo.value)


def test_annotate_relationships_values_appear_in_relationship_records() -> None:
    tagged = _g().annotate_relationships(source_label=lambda r: r.source.label)
    records = tagged.relationship_records()
    works_for = next(record for record in records if record["type"] == "worksFor")
    assert works_for["source_label"] == "Bob Jones"


def test_annotate_relationships_survives_select_then_expand() -> None:
    tagged = _g().annotate_relationships(source_label=lambda r: r.source.label)
    out = tagged.select(id="#bob").expand()
    works_for = next(rel for rel in out.relationships if rel.type == "worksFor")
    assert works_for.properties["source_label"] == "Bob Jones"
    assert "source_label" in out.relationship_derived_fields
