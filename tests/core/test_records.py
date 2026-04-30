"""Tests for crategraph.core.records — native list[dict] export of entities and relationships."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship


def _entity(eid: str, **kwargs) -> Entity:
    return Entity(id=eid, **kwargs)


def _rel(source: str, target: str, rel_type: str = "relatesTo", **kwargs) -> Relationship:
    return Relationship(source=source, target=target, type=rel_type, **kwargs)


def _make_graph(*entities: Entity, relationships: list[Relationship] | None = None) -> Graph:
    g = Graph()
    for entity in entities:
        g._add_node(entity)
    for rel in relationships or []:
        g._add_edge(rel)
    return g


class TestEntityRecords:
    def test_returns_list_of_dicts(self):
        a = _entity("A", types=["Person"], properties={"name": "Alice"})
        g = _make_graph(a)
        result = g.entity_records()
        assert isinstance(result, list)
        assert all(isinstance(r, dict) for r in result)

    def test_one_record_per_entity(self):
        a = _entity("A", types=["Person"], properties={"name": "Alice"})
        b = _entity("B", types=["Person"], properties={"name": "Bob"})
        g = _make_graph(a, b)
        assert len(g.entity_records()) == 2

    def test_promoted_keys_first_in_order(self):
        a = _entity("A", types=["Person"], properties={"name": "Alice", "age": 30})
        g = _make_graph(a)
        record = g.entity_records()[0]
        assert list(record.keys())[:4] == ["id", "label", "type", "types"]

    def test_property_keys_sorted_after_promoted(self):
        a = _entity(
            "A",
            types=["Person"],
            properties={"name": "Alice", "zebra": 1, "apple": 2},
        )
        g = _make_graph(a)
        record = g.entity_records()[0]
        property_keys = list(record.keys())[4:]
        assert property_keys == ["apple", "name", "zebra"]
