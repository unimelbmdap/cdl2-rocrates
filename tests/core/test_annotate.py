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


def test_annotate_attribute_error_on_entity_view_hints_at_get() -> None:
    """A common mistake — `e.gender` instead of `e.get('gender')` — gets a hint."""
    g = _g()
    with pytest.raises(RuntimeError) as excinfo:
        g.annotate_entities(is_f=lambda e: e.gender == "F")
    msg = str(excinfo.value)
    assert "gender" in msg
    assert "e.get(" in msg or "e.properties[" in msg


def test_annotate_relationships_attribute_error_hints_at_get() -> None:
    g = _g()
    with pytest.raises(RuntimeError) as excinfo:
        g.annotate_relationships(has_role=lambda r: r.role == "Analyst")
    msg = str(excinfo.value)
    assert "role" in msg
    assert "r.get(" in msg or "r.properties[" in msg


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


# --- joining a mapping of entity id -> fields --------------------------------


def test_annotate_mapping_adds_fields_only_to_listed_entities_in_the_graph() -> None:
    tagged = _g().annotate_entities(
        {"#alice": {"community": 3, "rank": 0.5}, "#bob": {"community": 1}, "#nobody": {"x": 2}}
    )
    assert tagged._entities["#alice"].properties["community"] == 3
    assert tagged._entities["#alice"].properties["rank"] == 0.5
    assert tagged._entities["#bob"].properties["community"] == 1
    assert "community" not in tagged._entities["#acme"].properties
    assert "#nobody" not in tagged._entities
    assert tagged.derived_fields["community"] is None
    assert tagged.derived_fields["rank"] is None


def test_annotate_mapping_with_no_matching_ids_raises() -> None:
    with pytest.raises(ValueError, match="none of the 2 ids"):
        _g().annotate_entities({"#nobody": {"x": 1}, "#ghost": {"x": 2}})


def test_annotate_empty_mapping_is_a_no_op() -> None:
    g = _g()
    assert (
        g.annotate_entities({})._entities["#alice"].properties == g._entities["#alice"].properties
    )


@pytest.mark.parametrize(
    ("values", "match"),
    [
        ([("#alice", {"x": 1})], "mapping of entity id"),
        ({"#alice": 3}, "'#alice'"),
        ({"#alice": {0: 42}}, "field names"),
    ],
)
def test_annotate_mapping_of_the_wrong_shape_raises(values, match) -> None:
    with pytest.raises(TypeError, match=match):
        _g().annotate_entities(values)


def test_annotate_mapping_combines_with_keyword_fields_and_wins_a_clash() -> None:
    tagged = _g().annotate_entities(
        {"#alice": {"community": 3, "flag": False}}, flag=lambda e: True
    )
    assert tagged._entities["#alice"].properties["community"] == 3
    assert tagged._entities["#alice"].properties["flag"] is False
    assert tagged._entities["#bob"].properties["flag"] is True


def test_annotate_mapping_overwrites_existing_properties() -> None:
    tagged = _g().annotate_entities({"#alice": {"name": "Renamed"}})
    assert tagged._entities["#alice"].properties["name"] == "Renamed"


def test_annotate_mapping_leaves_the_source_graph_unchanged() -> None:
    g = _g()
    g.annotate_entities({"#alice": {"community": 3}})
    assert "community" not in g._entities["#alice"].properties


def test_annotate_mapping_supports_where_and_survives_expand() -> None:
    tagged = _g().annotate_entities({"#alice": {"community": 3}, "#bob": {"community": 1}})
    assert [e.id for e in tagged.where(community=3).entities] == ["#alice"]
    out = tagged.select(id="#bob").expand()
    assert out._entities["#bob"].properties["community"] == 1


def test_annotate_keyword_named_values_still_works() -> None:
    tagged = _g().annotate_entities(values=lambda e: "v")
    assert tagged._entities["#alice"].properties["values"] == "v"


def test_annotate_mapping_passed_by_keyword_says_to_pass_it_first() -> None:
    with pytest.raises(TypeError, match="first argument"):
        _g().annotate_entities(values={"#alice": {"x": 1}})
