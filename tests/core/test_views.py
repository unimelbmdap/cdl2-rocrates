"""Tests for crategraph.core.views — CardinalityError, EntityView, Related."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from crategraph import Crate
from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.core.views import CardinalityError, EntityView, Related, RelationshipView

_FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


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


def test_entity_view_get_returns_property_value() -> None:
    e = EntityView(Entity(id="x", properties={"gender": "F"}))
    assert e.get("gender") == "F"


def test_entity_view_get_returns_default_when_missing() -> None:
    e = EntityView(Entity(id="x", properties={}))
    assert e.get("gender") is None
    assert e.get("gender", "unknown") == "unknown"
    assert e.get("preparedBy", "") == ""


def test_relationship_view_record_style_fields() -> None:
    rel = Relationship(
        source="#bob",
        target="#acme",
        type="worksFor",
        properties={"role": "Analyst"},
        id="#r1",
    )
    view = RelationshipView(rel)
    assert view.id == "#r1"
    assert view.type == "worksFor"
    assert view.source_id == "#bob"
    assert view.target_id == "#acme"
    assert view.properties["role"] == "Analyst"


def test_relationship_view_properties_top_level_read_only() -> None:
    rel = Relationship(source="#bob", target="#acme", type="worksFor", properties={"a": 1})
    view = RelationshipView(rel)
    with pytest.raises(TypeError):
        view.properties["a"] = 2
    assert rel.properties == {"a": 1}


def test_relationship_view_get_returns_property_value_or_default() -> None:
    rel = Relationship(
        source="#bob", target="#acme", type="worksFor", properties={"role": "Analyst"}
    )
    view = RelationshipView(rel)
    assert view.get("role") == "Analyst"
    assert view.get("missing") is None
    assert view.get("missing", "?") == "?"


def test_relationship_view_properties_is_shallow_documented_limit() -> None:
    rel = Relationship(
        source="#bob",
        target="#acme",
        type="worksFor",
        properties={"tags": ["a"]},
    )
    view = RelationshipView(rel)
    view.properties["tags"].append("b")
    assert rel.properties["tags"] == ["a", "b"]


def test_relationship_view_source_and_target_are_entity_views() -> None:
    g = Graph()
    g._add_node(Entity(id="#bob", types=["Person"], properties={"name": "Bob"}))
    g._add_node(Entity(id="#acme", types=["Organisation"], properties={"name": "ACME"}))
    rel = Relationship(source="#bob", target="#acme", type="worksFor")
    g._add_edge(rel)

    view = RelationshipView(rel, g)
    assert isinstance(view.source, EntityView)
    assert isinstance(view.target, EntityView)
    assert view.source.id == "#bob"
    assert view.target.id == "#acme"
    assert view.source.graph is g
    assert view.target.graph is g


def test_relationship_view_graphless_endpoint_access_raises() -> None:
    view = RelationshipView(Relationship(source="#bob", target="#acme", type="worksFor"))
    with pytest.raises(ValueError, match="source"):
        _ = view.source
    with pytest.raises(ValueError, match="target"):
        _ = view.target


def test_relationship_view_slots_prevent_arbitrary_assignment() -> None:
    view = RelationshipView(Relationship(source="#bob", target="#acme", type="worksFor"))
    with pytest.raises(AttributeError):
        view.extra = "nope"


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


def test_related_list_key_none_returns_views() -> None:
    r = Related(_views(("a", {}), ("b", {})))
    assert [v.id for v in r.list()] == ["a", "b"]


def test_related_list_default_preserves_order_no_dedup() -> None:
    r = Related(_views(("a", {"g": "X"}), ("b", {"g": "Y"}), ("c", {"g": "X"})))
    assert r.list("g") == ["X", "Y", "X"]  # source order, no dedup


def test_related_list_unique_order_preserving_handles_unhashable() -> None:
    r = Related(_views(("a", {"g": ["X"]}), ("b", {"g": ["X"]}), ("c", {"g": ["Y"]})))
    assert r.list("g", unique=True) == [["X"], ["Y"]]  # equality dedup, unhashable ok


def test_related_list_sort_never_raises_on_mixed() -> None:
    r = Related(_views(("a", {"g": 2}), ("b", {"g": "x"}), ("c", {"g": 1})))
    # mixed int/str: str() fallback, deterministic, no TypeError
    assert r.list("g", sort=True) == [1, 2, "x"]


def test_related_traversal_against_real_graph() -> None:
    g = Crate(str(_FIXTURE))
    bob = (
        g.entity_view("#bob") if hasattr(g, "entity_view") else EntityView(g._entities["#bob"], g)
    )
    rel = bob.related("worksFor")
    assert isinstance(rel, Related)
    assert "#acme" in [v.id for v in rel]
    assert bob.has("worksFor") is True


def test_related_unknown_type_raises_value_error() -> None:
    g = Crate(str(_FIXTURE))
    bob = EntityView(g._entities["#bob"], g)
    with pytest.raises(ValueError):
        bob.related("definitely_not_a_rel")


def test_related_graphless_view_skips_validation_returns_empty() -> None:
    e = EntityView(Entity(id="x", properties={}))  # no graph
    assert list(e.related("anything")) == []
    assert e.has("anything") is False


class TestEntityViewTemporal:
    """Date accessors delegate to the temporal engine; work on graphless views."""

    def test_year_from_isostring(self) -> None:
        e = EntityView(Entity(id="x", properties={"startDateISOString": "2017-03-12 00:00:00"}))
        assert e.year == 2017
        assert e.start_date == date(2017, 3, 12)
        assert e.date_precision == "day"

    def test_prefers_isostring_over_human_startdate(self) -> None:
        e = EntityView(
            Entity(
                id="x",
                properties={
                    "startDateISOString": "2017-03-12 00:00:00",
                    "startDate": "12 March 2017",
                },
            )
        )
        assert e.start_date == date(2017, 3, 12)

    def test_falls_back_to_human_pair_when_iso_blank(self) -> None:
        e = EntityView(
            Entity(
                id="x",
                properties={"startDateISOString": "", "startDate": "1 Sept 1990"},
            )
        )
        assert e.year == 1990
        assert e.start_date == date(1990, 9, 1)

    def test_circa_and_uncertain_from_modifier_fields(self) -> None:
        e = EntityView(
            Entity(
                id="x",
                properties={
                    "startDate": "1966",
                    "startDateModifier": "c",
                    "endDate": "1970",
                    "endDateModifier": "?",
                },
            )
        )
        assert e.date_circa is True
        assert e.date_uncertain is True

    def test_misspelt_end_modifier_is_read(self) -> None:
        e = EntityView(Entity(id="x", properties={"endDate": "1966", "endDateModifer": "c"}))
        assert e.date_circa is True

    def test_no_temporal_fields_returns_none(self) -> None:
        e = EntityView(Entity(id="x", properties={"name": "Alice"}))
        assert e.year is None
        assert e.start_date is None
        assert e.date_circa is False


class TestEntityViewParse:
    """e.parse_year / e.parse_date — explicit field parsing, graphless-safe."""

    def test_parse_year_named_field(self) -> None:
        e = EntityView(Entity(id="x", properties={"birthDate": "1888"}))
        assert e.parse_year("birthDate") == 1888

    def test_parse_year_ordered_fallback(self) -> None:
        e = EntityView(Entity(id="x", properties={"startDate": "12 March 2017"}))
        # First field missing -> falls through to the second.
        assert e.parse_year("startDateISOString", "startDate") == 2017

    def test_parse_year_ignores_unnamed_fields(self) -> None:
        # Only the named field is read — no cascade, no provenance.
        e = EntityView(Entity(id="x", properties={"recordAppendDate": "2018-01-01"}))
        assert e.parse_year("startDateISOString") is None
        assert e.year is None  # default policy also ignores provenance

    def test_parse_date_returns_temporal_value(self) -> None:
        e = EntityView(Entity(id="x", properties={"startDate": "Dec 1914"}))
        tv = e.parse_date("startDate")
        assert tv is not None
        assert (tv.year, tv.precision) == (1914, "month")

    def test_parse_all_missing_is_none(self) -> None:
        e = EntityView(Entity(id="x", properties={"name": "Alice"}))
        assert e.parse_year("birthDate") is None
        assert e.parse_date("birthDate") is None

    def test_no_fields_returns_none(self) -> None:
        e = EntityView(Entity(id="x", properties={"birthDate": "1888"}))
        assert e.parse_year() is None
        assert e.parse_date() is None
