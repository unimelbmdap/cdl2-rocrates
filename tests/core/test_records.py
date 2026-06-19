"""Tests for crategraph.core.records — native list[dict] export of entities and relationships."""

from __future__ import annotations

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.core.records import Records


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


class TestRelationshipRecords:
    def test_returns_list_of_dicts(self):
        a = _entity("A", types=["Person"])
        b = _entity("B", types=["Person"])
        g = _make_graph(a, b, relationships=[_rel("A", "B", "knows")])
        result = g.relationship_records()
        assert isinstance(result, list)
        assert all(isinstance(r, dict) for r in result)

    def test_one_record_per_relationship(self):
        a = _entity("A", types=["Person"])
        b = _entity("B", types=["Person"])
        c = _entity("C", types=["Person"])
        g = _make_graph(
            a,
            b,
            c,
            relationships=[
                _rel("A", "B", "knows"),
                _rel("A", "C", "knows"),
                _rel("B", "C", "manages"),
            ],
        )
        assert len(g.relationship_records()) == 3

    def test_promoted_keys_first_in_order(self):
        a = _entity("A", types=["Person"])
        b = _entity("B", types=["Person"])
        rel = _rel("A", "B", "knows", id="r1", properties={"since": 2020})
        g = _make_graph(a, b, relationships=[rel])
        record = g.relationship_records()[0]
        assert list(record.keys())[:4] == ["source", "target", "type", "rel_id"]

    def test_inline_relationship_rel_id_is_none(self):
        a = _entity("A", types=["Person"])
        b = _entity("B", types=["Person"])
        rel = _rel("A", "B", "knows")  # no id → inline
        g = _make_graph(a, b, relationships=[rel])
        record = g.relationship_records()[0]
        assert record["rel_id"] is None

    def test_reified_relationship_rel_id_preserved(self):
        a = _entity("A", types=["Person"])
        b = _entity("B", types=["Person"])
        rel = _rel("A", "B", "knows", id="r-42")
        g = _make_graph(a, b, relationships=[rel])
        record = g.relationship_records()[0]
        assert record["rel_id"] == "r-42"

    def test_relationship_property_keys_sorted_after_promoted(self):
        a = _entity("A", types=["Person"])
        b = _entity("B", types=["Person"])
        rel = _rel("A", "B", "knows", id="r1", properties={"weight": 0.8, "since": 2020})
        g = _make_graph(a, b, relationships=[rel])
        record = g.relationship_records()[0]
        property_keys = list(record.keys())[4:]
        assert property_keys == ["since", "weight"]


class TestNativeTypes:
    """Records preserve native Python types — no pipe-delimiting, no JSON encoding.

    The CSV writer flattens lists/dicts to strings because CSV cells must be
    scalar; records have no such constraint. Pandas, polars, and pyarrow all
    handle list-typed cells natively, so preserving structure here is more
    useful than mirroring CSV's lossy encoding.
    """

    def test_list_property_stays_a_list(self):
        a = _entity("A", types=["Person"], properties={"tags": ["x", "y", "z"]})
        g = _make_graph(a)
        record = g.entity_records()[0]
        assert record["tags"] == ["x", "y", "z"]

    def test_dict_property_stays_a_dict(self):
        a = _entity(
            "A",
            types=["Person"],
            properties={"address": {"city": "Sydney", "postcode": "2000"}},
        )
        g = _make_graph(a)
        record = g.entity_records()[0]
        assert record["address"] == {"city": "Sydney", "postcode": "2000"}

    def test_none_property_stays_none(self):
        a = _entity("A", types=["Person"], properties={"middle_name": None})
        g = _make_graph(a)
        record = g.entity_records()[0]
        assert record["middle_name"] is None

    def test_int_and_float_preserved(self):
        a = _entity("A", types=["Person"], properties={"age": 30, "height": 1.75})
        g = _make_graph(a)
        record = g.entity_records()[0]
        assert record["age"] == 30
        assert isinstance(record["age"], int)
        assert record["height"] == 1.75
        assert isinstance(record["height"], float)

    def test_types_is_a_list_not_a_tuple(self):
        a = _entity("A", types=["Person", "Researcher"])
        g = _make_graph(a)
        record = g.entity_records()[0]
        assert record["types"] == ["Person", "Researcher"]
        assert isinstance(record["types"], list)

    def test_mutating_returned_list_does_not_corrupt_graph(self):
        """Property values are deep-copied so callers can mutate freely."""
        a = _entity("A", types=["Person"], properties={"tags": ["x", "y"]})
        g = _make_graph(a)
        record = g.entity_records()[0]
        record["tags"].append("z")
        # Re-read from the graph; the original property must be unchanged.
        assert g.entity_records()[0]["tags"] == ["x", "y"]
        assert a.properties["tags"] == ["x", "y"]

    def test_mutating_returned_dict_does_not_corrupt_graph(self):
        a = _entity(
            "A",
            types=["Person"],
            properties={"address": {"city": "Sydney"}},
        )
        g = _make_graph(a)
        record = g.entity_records()[0]
        record["address"]["city"] = "Melbourne"
        assert g.entity_records()[0]["address"] == {"city": "Sydney"}
        assert a.properties["address"] == {"city": "Sydney"}


class TestLabelDerivation:
    def test_label_uses_name_when_present(self):
        a = _entity("A", types=["Person"], properties={"name": "Alice"})
        g = _make_graph(a)
        assert g.entity_records()[0]["label"] == "Alice"

    def test_label_falls_back_to_title(self):
        a = _entity("A", types=["Document"], properties={"title": "My Paper"})
        g = _make_graph(a)
        assert g.entity_records()[0]["label"] == "My Paper"

    def test_label_falls_back_to_id_when_no_name_or_title(self):
        a = _entity("A", types=["Person"], properties={"description": "Anonymous"})
        g = _make_graph(a)
        assert g.entity_records()[0]["label"] == "A"

    def test_empty_string_name_falls_through(self):
        a = _entity("A", types=["Person"], properties={"name": ""})
        g = _make_graph(a)
        # Empty string is not truthy → fall through to id.
        assert g.entity_records()[0]["label"] == "A"

    def test_non_string_name_is_coerced(self):
        a = _entity("A", types=["Person"], properties={"name": 42})
        g = _make_graph(a)
        assert g.entity_records()[0]["label"] == "42"


class TestKeyCollisions:
    def test_property_named_id_is_prefixed(self):
        a = _entity("A", types=["Person"], properties={"id": "external-id-001"})
        g = _make_graph(a)
        record = g.entity_records()[0]
        # Promoted "id" wins; property collides → prop_id.
        assert record["id"] == "A"
        assert record["prop_id"] == "external-id-001"

    def test_property_named_types_is_prefixed(self):
        a = _entity("A", types=["Person"], properties={"types": ["custom"]})
        g = _make_graph(a)
        record = g.entity_records()[0]
        assert record["types"] == ["Person"]
        assert record["prop_types"] == ["custom"]

    def test_existing_prop_prefix_is_pushed_further(self):
        a = _entity(
            "A",
            types=["Person"],
            properties={"id": "x", "prop_id": "y"},
        )
        g = _make_graph(a)
        record = g.entity_records()[0]
        # "prop_id" is non-colliding (not in promoted keys) so the
        # non-colliding-first sort emits it before "id". With "prop_id"
        # already taken, "id" then collides on the promoted "id" *and*
        # the just-emitted "prop_id" → prop_prop_id.
        assert record["id"] == "A"
        assert record["prop_id"] == "y"
        assert record["prop_prop_id"] == "x"

    def test_relationship_property_named_source_is_prefixed(self):
        a = _entity("A", types=["Person"])
        b = _entity("B", types=["Person"])
        rel = _rel("A", "B", "knows", properties={"source": "interview-2020"})
        g = _make_graph(a, b, relationships=[rel])
        record = g.relationship_records()[0]
        assert record["source"] == "A"
        assert record["prop_source"] == "interview-2020"


class TestEmptyGraph:
    def test_entity_records_empty_graph_returns_empty_list(self):
        g = _make_graph()  # no entities
        result = g.entity_records()
        assert result == []
        assert isinstance(result, list)

    def test_relationship_records_no_relationships_returns_empty_list(self):
        a = _entity("A", types=["Person"])
        g = _make_graph(a)  # entity but no relationships
        result = g.relationship_records()
        assert result == []
        assert isinstance(result, list)


class TestRecordsType:
    """Records stays a drop-in list[dict]; adds only a humble notebook table."""

    def test_record_methods_return_records_instances(self):
        g = _make_graph(_entity("A", types=["Person"], properties={"name": "Alice"}))
        assert isinstance(g.entity_records(), Records)
        assert isinstance(g.relationship_records(), Records)

    def test_records_is_a_list_and_equals_plain_list(self):
        g = _make_graph(_entity("A", types=["Person"], properties={"name": "Alice"}))
        result = g.entity_records()
        assert isinstance(result, list)
        assert result == [dict(result[0])]
        assert result[0]["label"] == "Alice"

    def test_slice_returns_plain_list_not_records(self):
        # Deliberately not re-wrapped — only the full result needs _repr_html_.
        entities = [_entity(f"E{i}", types=["Person"]) for i in range(5)]
        sliced = _make_graph(*entities).entity_records()[:3]
        assert isinstance(sliced, list)
        assert not isinstance(sliced, Records)

    def test_records_is_publicly_exported(self):
        import crategraph

        assert crategraph.Records is Records

    def test_repr_html_title_and_table(self):
        g = _make_graph(_entity("A", types=["Person"], properties={"name": "Alice"}))
        markup = g.entity_records()._repr_html_()
        assert "<table" in markup and "</table>" in markup
        assert "Records: 1 rows x" in markup  # ASCII 'x' separator
        assert "Alice" in markup
        assert 'style="' in markup  # inline styles, not a CSS class

    def test_repr_html_escapes_header_and_values(self):
        g = _make_graph(_entity("A", types=["Person"], properties={"name": "<script>x</script>"}))
        markup = g.entity_records()._repr_html_()
        assert "<script>x</script>" not in markup
        assert "&lt;script&gt;x&lt;/script&gt;" in markup

    def test_repr_html_joins_list_values(self):
        g = _make_graph(_entity("A", types=["Person", "Author"], properties={"name": "Alice"}))
        assert "Person, Author" in g.entity_records()._repr_html_()

    def test_repr_html_truncates_long_cells(self):
        long = "x" * 200
        g = _make_graph(_entity("A", types=["Person"], properties={"name": long}))
        markup = g.entity_records()._repr_html_()
        assert "..." in markup
        assert long not in markup  # full untruncated value not present

    def test_repr_html_caps_rows_and_reports_total(self):
        entities = [_entity(f"E{i}", types=["Person"]) for i in range(25)]
        result = _make_graph(*entities).entity_records()
        assert len(result) == 25  # full data retained
        markup = result._repr_html_()
        assert markup.count("<tr>") == 1 + Records.max_display_rows  # header + capped body
        assert "Showing 20 of 25 rows" in markup

    def test_repr_html_caps_columns_with_marker(self):
        # 4 promoted + 11 properties = 15 columns > max_display_cols (12).
        props = {f"p{i:02d}": i for i in range(11)}
        props["name"] = "Alice"
        g = _make_graph(_entity("A", types=["Person"], properties=props))
        markup = g.entity_records()._repr_html_()
        assert "more columns" in markup

    def test_repr_html_empty(self):
        markup = _make_graph().entity_records()._repr_html_()
        assert "Records: 0 rows" in markup
