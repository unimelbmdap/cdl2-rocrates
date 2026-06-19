"""Tests for Graph.entity_counts / relationship_counts."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.core.records import Records


def _graph(*entities: Entity, relationships: list[Relationship] | None = None) -> Graph:
    g = Graph()
    for entity in entities:
        g._add_node(entity)
    for rel in relationships or []:
        g._add_edge(rel)
    return g


def _as_pairs(records: Records, field: str, count_col: str = "count") -> list[tuple]:
    return [(r[field], r[count_col]) for r in records]


class TestEntityCounts:
    def test_counts_promoted_first_type(self):
        g = _graph(
            Entity(id="#1", types=["Person"]),
            Entity(id="#2", types=["Person"]),
            Entity(id="#3", types=["Organisation"]),
        )
        result = g.entity_counts("type")
        assert isinstance(result, Records)
        assert _as_pairs(result, "type") == [("Person", 2), ("Organisation", 1)]

    def test_counts_label_via_derive_label(self):
        g = _graph(
            Entity(id="#1", properties={"name": "Alice"}),
            Entity(id="#2", properties={"title": "Alice"}),  # title falls back to same label
            Entity(id="#3", properties={}),  # label -> id "#3"
        )
        result = g.entity_counts("label")
        assert _as_pairs(result, "label") == [("Alice", 2), ("#3", 1)]

    def test_types_explodes_so_total_exceeds_entity_count(self):
        g = _graph(
            Entity(id="#1", types=["Person", "Author"]),
            Entity(id="#2", types=["Person"]),
        )
        result = g.entity_counts("types")
        counts = dict(_as_pairs(result, "types"))
        assert counts == {"Person": 2, "Author": 1}
        assert sum(counts.values()) == 3  # > 2 entities

    def test_counts_a_plain_property(self):
        g = _graph(
            Entity(id="#1", properties={"gender": "F"}),
            Entity(id="#2", properties={"gender": "F"}),
            Entity(id="#3", properties={"gender": "M"}),
            Entity(id="#4", properties={}),  # missing -> skipped
        )
        assert _as_pairs(g.entity_counts("gender"), "gender") == [("F", 2), ("M", 1)]

    def test_property_named_type_collides_to_prop_type(self):
        # The promoted "type" is the first entity type; a property literally
        # named "type" surfaces (and counts) as "prop_type".
        g = _graph(
            Entity(id="#1", types=["Person"], properties={"type": "primary"}),
            Entity(id="#2", types=["Person"], properties={"type": "secondary"}),
        )
        assert _as_pairs(g.entity_counts("type"), "type") == [("Person", 2)]
        prop = dict(_as_pairs(g.entity_counts("prop_type"), "prop_type"))
        assert prop == {"primary": 1, "secondary": 1}

    def test_counts_a_derived_column_from_annotate(self):
        # No bespoke method needed — annotate adds the column, counts see it.
        g = _graph(
            Entity(id="#1", types=["Person"]),
            Entity(id="#2", types=["File"]),
            Entity(id="#3", types=["File"]),
        )
        annotated = g.annotate_entities(is_file=lambda e: e.type == "File")
        assert _as_pairs(annotated.entity_counts("is_file"), "is_file") == [
            (True, 2),
            (False, 1),
        ]

    def test_native_scalar_type_preserved(self):
        g = _graph(
            Entity(id="#1", properties={"year": 1900}),
            Entity(id="#2", properties={"year": 1900}),
            Entity(id="#3", properties={"year": 2000}),
        )
        rows = g.entity_counts("year")
        top_value = rows[0]["year"]
        assert top_value == 1900
        assert isinstance(top_value, int)  # not "1900"

    def test_equal_dicts_count_together_and_stringify(self):
        g = _graph(
            Entity(id="#1", properties={"meta": {"a": 1}}),
            Entity(id="#2", properties={"meta": {"a": 1}}),
        )
        # Equal unhashable values tally together; output is the stringified value.
        assert _as_pairs(g.entity_counts("meta"), "meta") == [("{'a': 1}", 2)]

    def test_unhashable_value_does_not_collide_with_real_string(self):
        # A dict and a genuine string of the same text are distinct buckets,
        # so they produce two rows (each count 1) rather than merging to one.
        text = "{'a': 1}"
        g = _graph(
            Entity(id="#1", properties={"meta": {"a": 1}}),
            Entity(id="#2", properties={"meta": text}),
        )
        rows = _as_pairs(g.entity_counts("meta"), "meta")
        assert len(rows) == 2
        assert all(value == text for value, _ in rows)
        assert sum(count for _, count in rows) == 2

    def test_sorted_count_desc_then_value(self):
        g = _graph(
            Entity(id="#1", properties={"g": "b"}),
            Entity(id="#2", properties={"g": "a"}),
            Entity(id="#3", properties={"g": "c"}),
        )
        # All count 1 -> tie broken by value ascending.
        assert [r["g"] for r in g.entity_counts("g")] == ["a", "b", "c"]

    def test_field_named_count_uses_n_column(self):
        g = _graph(
            Entity(id="#1", properties={"count": "x"}),
            Entity(id="#2", properties={"count": "x"}),
        )
        # "count" is a property name here; tally column falls back to "n".
        result = g.entity_counts("count")
        assert "n" in result[0]
        assert result[0]["count"] == "x"
        assert result[0]["n"] == 2

    def test_counts_respect_current_view(self):
        g = _graph(
            Entity(id="#1", types=["Person"]),
            Entity(id="#2", types=["Person"]),
            Entity(id="#3", types=["Organisation"]),
        )
        view = g.select(entity_types=["Person"])
        assert _as_pairs(view.entity_counts("type"), "type") == [("Person", 2)]


class TestRelationshipCounts:
    def test_counts_relationship_type(self):
        g = _graph(
            Entity(id="#a"),
            Entity(id="#b"),
            Entity(id="#c"),
            relationships=[
                Relationship(source="#a", target="#b", type="knows"),
                Relationship(source="#b", target="#c", type="knows"),
                Relationship(source="#a", target="#c", type="memberOf"),
            ],
        )
        assert _as_pairs(g.relationship_counts("type"), "type") == [("knows", 2), ("memberOf", 1)]

    def test_counts_relationship_property(self):
        g = _graph(
            Entity(id="#a"),
            Entity(id="#b"),
            relationships=[
                Relationship(source="#a", target="#b", type="r", properties={"role": "lead"}),
                Relationship(source="#a", target="#b", type="r", properties={"role": "lead"}),
                Relationship(source="#a", target="#b", type="r", properties={"role": "member"}),
            ],
        )
        assert _as_pairs(g.relationship_counts("role"), "role") == [("lead", 2), ("member", 1)]
