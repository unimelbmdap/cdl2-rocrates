"""Unit tests for crategraph.writers._flatten."""

from __future__ import annotations

import json

from hypothesis import given, settings
from hypothesis import strategies as st

from crategraph.core.models import Entity, Relationship
from crategraph.writers._flatten import (
    EDGE_PROMOTED_COLUMNS,
    NODE_PROMOTED_COLUMNS,
    decode_pipe_list,
    flatten_edge,
    flatten_node,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(**kwargs) -> Entity:
    """Convenience factory — fills in required *id* if not supplied."""
    kwargs.setdefault("id", "test-id")
    return Entity(**kwargs)


def _make_rel(**kwargs) -> Relationship:
    kwargs.setdefault("source", "a")
    kwargs.setdefault("target", "b")
    kwargs.setdefault("type", "relatesTo")
    return Relationship(**kwargs)


# ---------------------------------------------------------------------------
# 1. Promoted columns appear first in fixed order
# ---------------------------------------------------------------------------


class TestPromotedColumnOrder:
    def test_node_promoted_columns_are_first(self):
        entity = _make_entity(
            id="e1",
            types=["Person"],
            properties={"zzz": "last", "aaa": "first_alpha", "name": "Alice"},
        )
        result = flatten_node(entity)
        keys = list(result.keys())
        promoted = list(NODE_PROMOTED_COLUMNS)
        assert keys[: len(promoted)] == promoted

    def test_node_remaining_keys_sorted(self):
        entity = _make_entity(
            id="e1",
            properties={"zzz": "z", "aaa": "a", "mmm": "m"},
        )
        result = flatten_node(entity)
        promoted_count = len(NODE_PROMOTED_COLUMNS)
        remaining = list(result.keys())[promoted_count:]
        assert remaining == sorted(remaining)

    def test_edge_promoted_columns_are_first(self):
        rel = _make_rel(
            source="s",
            target="t",
            type="connects",
            properties={"zzz": "last", "aaa": "first"},
        )
        result = flatten_edge(rel)
        keys = list(result.keys())
        promoted = list(EDGE_PROMOTED_COLUMNS)
        assert keys[: len(promoted)] == promoted

    def test_edge_remaining_keys_sorted(self):
        rel = _make_rel(properties={"zzz": "z", "aaa": "a", "mmm": "m"})
        result = flatten_edge(rel)
        promoted_count = len(EDGE_PROMOTED_COLUMNS)
        remaining = list(result.keys())[promoted_count:]
        assert remaining == sorted(remaining)


# ---------------------------------------------------------------------------
# 2. Label fallback chain
# ---------------------------------------------------------------------------


class TestLabelFallback:
    def test_name_wins_over_title(self):
        entity = _make_entity(properties={"name": "MyName", "title": "MyTitle"})
        assert flatten_node(entity)["label"] == "MyName"

    def test_title_wins_over_id(self):
        entity = _make_entity(id="e1", properties={"title": "MyTitle"})
        assert flatten_node(entity)["label"] == "MyTitle"

    def test_id_fallback_when_all_missing(self):
        entity = _make_entity(id="e1", properties={})
        assert flatten_node(entity)["label"] == "e1"

    def test_empty_string_name_falls_through_to_title(self):
        entity = _make_entity(id="e1", properties={"name": "", "title": "Fallback"})
        assert flatten_node(entity)["label"] == "Fallback"

    def test_empty_string_name_and_title_falls_to_id(self):
        entity = _make_entity(id="e1", properties={"name": "", "title": ""})
        assert flatten_node(entity)["label"] == "e1"

    def test_none_name_falls_through_to_title(self):
        # None is not in properties so get returns None — same as absent.
        entity = _make_entity(id="e1", properties={"title": "TitleVal"})
        assert flatten_node(entity)["label"] == "TitleVal"

    def test_label_coerced_to_str(self):
        entity = _make_entity(properties={"name": 42})
        assert flatten_node(entity)["label"] == "42"


# ---------------------------------------------------------------------------
# 3-5. Types encoding
# ---------------------------------------------------------------------------


class TestTypesEncoding:
    def test_empty_types_gives_empty_strings(self):
        entity = _make_entity(types=[])
        result = flatten_node(entity)
        assert result["type"] == ""
        assert result["types"] == ""

    def test_single_type(self):
        entity = _make_entity(types=["Person"])
        result = flatten_node(entity)
        assert result["type"] == "Person"
        assert result["types"] == "Person"

    def test_multi_type_first_in_type_column(self):
        entity = _make_entity(types=["Person", "Agent", "Thing"])
        result = flatten_node(entity)
        assert result["type"] == "Person"
        assert result["types"] == "Person|Agent|Thing"


# ---------------------------------------------------------------------------
# 6. Scalar property encoding
# ---------------------------------------------------------------------------


class TestScalarEncoding:
    def test_str_passthrough(self):
        entity = _make_entity(properties={"note": "hello"})
        assert flatten_node(entity)["note"] == "hello"

    def test_int_passthrough(self):
        entity = _make_entity(properties={"count": 42})
        assert flatten_node(entity)["count"] == 42

    def test_float_passthrough(self):
        entity = _make_entity(properties={"score": 3.14})
        assert flatten_node(entity)["score"] == 3.14

    def test_bool_true_passthrough(self):
        entity = _make_entity(properties={"flag": True})
        result = flatten_node(entity)["flag"]
        assert result is True
        assert isinstance(result, bool)

    def test_bool_false_passthrough(self):
        entity = _make_entity(properties={"flag": False})
        result = flatten_node(entity)["flag"]
        assert result is False
        assert isinstance(result, bool)

    def test_none_becomes_empty_string(self):
        entity = _make_entity(properties={"optional": None})
        assert flatten_node(entity)["optional"] == ""


# ---------------------------------------------------------------------------
# 7. List-of-scalars round-trip (including | and \ in values)
# ---------------------------------------------------------------------------


class TestPipeListRoundTrip:
    def test_simple_list(self):
        entity = _make_entity(properties={"tags": ["a", "b", "c"]})
        encoded = flatten_node(entity)["tags"]
        assert isinstance(encoded, str)
        assert decode_pipe_list(encoded) == ["a", "b", "c"]

    def test_literal_pipe_in_value(self):
        entity = _make_entity(properties={"tags": ["a|b", "c"]})
        encoded = flatten_node(entity)["tags"]
        assert decode_pipe_list(encoded) == ["a|b", "c"]

    def test_literal_backslash_in_value(self):
        entity = _make_entity(properties={"tags": ["a\\b", "c"]})
        encoded = flatten_node(entity)["tags"]
        assert decode_pipe_list(encoded) == ["a\\b", "c"]

    def test_backslash_and_pipe_combined(self):
        items = ["a\\|b", "c|d", "e\\f"]
        entity = _make_entity(properties={"tags": items})
        encoded = flatten_node(entity)["tags"]
        assert decode_pipe_list(encoded) == items

    def test_none_element_in_list(self):
        entity = _make_entity(properties={"items": ["x", None, "y"]})
        encoded = flatten_node(entity)["items"]
        assert decode_pipe_list(encoded) == ["x", "", "y"]

    def test_bool_elements_use_str_representation(self):
        entity = _make_entity(properties={"flags": [True, False]})
        encoded = flatten_node(entity)["flags"]
        assert decode_pipe_list(encoded) == ["True", "False"]

    def test_empty_list_gives_empty_string(self):
        entity = _make_entity(properties={"empty": []})
        assert flatten_node(entity)["empty"] == ""

    def test_decode_empty_string_returns_empty_list(self):
        assert decode_pipe_list("") == []

    def test_decode_single_element(self):
        assert decode_pipe_list("hello") == ["hello"]

    def test_decode_single_empty_element(self):
        # A list with one empty-string element encodes as "".
        # Convention: empty string → [] (not [""]). Single empty element
        # would only arise mid-list. Verify direct encode of [""] gives "".
        from crategraph.writers._flatten import _encode_pipe_list

        encoded = _encode_pipe_list([""])
        # "" encodes to "" — indistinguishable from empty list by convention.
        assert encoded == ""
        # Decoded back is [] per the empty-string convention.
        assert decode_pipe_list(encoded) == []


# ---------------------------------------------------------------------------
# 8. Nested dict → JSON with sort_keys
# ---------------------------------------------------------------------------


class TestNestedDictEncoding:
    def test_dict_becomes_json(self):
        d = {"z": 1, "a": 2}
        entity = _make_entity(properties={"nested": d})
        encoded = flatten_node(entity)["nested"]
        assert isinstance(encoded, str)
        parsed = json.loads(encoded)
        assert parsed == d

    def test_dict_json_has_sorted_keys(self):
        d = {"z": 1, "m": 2, "a": 3}
        entity = _make_entity(properties={"nested": d})
        encoded = flatten_node(entity)["nested"]
        # Verify key ordering in the raw JSON string.
        assert encoded == json.dumps(d, sort_keys=True, ensure_ascii=False)

    def test_dict_encoding_is_stable_across_runs(self):
        d = {"z": 1, "m": 2, "a": 3}
        entity = _make_entity(properties={"nested": d})
        results = {flatten_node(entity)["nested"] for _ in range(10)}
        assert len(results) == 1


# ---------------------------------------------------------------------------
# 9. List of dicts → JSON
# ---------------------------------------------------------------------------


class TestListOfDictsEncoding:
    def test_list_of_dicts_becomes_json(self):
        lst = [{"key": "val"}, {"other": 2}]
        entity = _make_entity(properties={"items": lst})
        encoded = flatten_node(entity)["items"]
        assert isinstance(encoded, str)
        assert json.loads(encoded) == lst

    def test_mixed_list_with_dict_falls_to_json(self):
        lst = ["scalar", {"nested": True}]
        entity = _make_entity(properties={"mixed": lst})
        encoded = flatten_node(entity)["mixed"]
        assert isinstance(encoded, str)
        assert json.loads(encoded) == lst


# ---------------------------------------------------------------------------
# 10. Collision prefixing for nodes
# ---------------------------------------------------------------------------


class TestNodeCollisionPrefixing:
    def test_all_promoted_keys_in_properties_get_prefixed(self):
        entity = _make_entity(
            id="actual-id",
            types=["Thing"],
            properties={
                "id": "prop-id",
                "type": "prop-type",
                "label": "prop-label",
                "types": "prop-types",
            },
        )
        result = flatten_node(entity)
        # Promoted columns still come from the dataclass.
        assert result["id"] == "actual-id"
        assert result["type"] == "Thing"
        assert result["types"] == "Thing"
        assert result["label"] == "actual-id"  # no name/title; falls to id
        # Prefixed versions come from properties.
        assert result["prop_id"] == "prop-id"
        assert result["prop_type"] == "prop-type"
        assert result["prop_label"] == "prop-label"
        assert result["prop_types"] == "prop-types"

    def test_non_colliding_keys_not_prefixed(self):
        entity = _make_entity(properties={"note": "hello"})
        result = flatten_node(entity)
        assert "note" in result
        assert "prop_note" not in result

    def test_promoted_and_prefixed_both_present(self):
        """Both ``id`` and ``prop_id`` as property keys must both be preserved.

        User-defined ``prop_id`` keeps its name; the promoted-column collision
        (the ``id`` property) gets pushed further out to ``prop_prop_id``.
        """
        entity = _make_entity(
            id="actual-id",
            properties={"id": "promoted-collision", "prop_id": "user-column"},
        )
        result = flatten_node(entity)
        assert result["id"] == "actual-id"
        assert result["prop_id"] == "user-column"
        assert result["prop_prop_id"] == "promoted-collision"

    def test_chained_prefix_collisions(self):
        """Three-deep collision chain resolves via repeated prefixing."""
        entity = _make_entity(
            id="actual-id",
            properties={
                "id": "a",
                "prop_id": "b",
                "prop_prop_id": "c",
            },
        )
        result = flatten_node(entity)
        assert result["id"] == "actual-id"
        # User-defined names preserved.
        assert result["prop_id"] == "b"
        assert result["prop_prop_id"] == "c"
        # Promoted-collision ``id`` gets pushed to the first unused prefix.
        assert result["prop_prop_prop_id"] == "a"


# ---------------------------------------------------------------------------
# 11. Edge flattening
# ---------------------------------------------------------------------------


class TestEdgeFlattening:
    def test_promoted_columns_correct(self):
        rel = Relationship(source="s", target="t", type="connects", id="r1")
        result = flatten_edge(rel)
        assert result["source"] == "s"
        assert result["target"] == "t"
        assert result["type"] == "connects"
        assert result["rel_id"] == "r1"

    def test_rel_id_empty_string_when_none(self):
        rel = Relationship(source="s", target="t", type="knows", id=None)
        assert flatten_edge(rel)["rel_id"] == ""

    def test_edge_collision_prefixing(self):
        rel = Relationship(
            source="s",
            target="t",
            type="links",
            id="r1",
            properties={
                "source": "prop-source",
                "target": "prop-target",
                "type": "prop-type",
                "rel_id": "prop-rel-id",
            },
        )
        result = flatten_edge(rel)
        # Promoted columns from dataclass.
        assert result["source"] == "s"
        assert result["target"] == "t"
        assert result["type"] == "links"
        assert result["rel_id"] == "r1"
        # Prefixed from properties.
        assert result["prop_source"] == "prop-source"
        assert result["prop_target"] == "prop-target"
        assert result["prop_type"] == "prop-type"
        assert result["prop_rel_id"] == "prop-rel-id"

    def test_edge_promoted_and_prefixed_both_present(self):
        """Both ``source`` and ``prop_source`` as property keys both preserved.

        User-defined ``prop_source`` keeps its name; the promoted-column
        collision (the ``source`` property) gets pushed to ``prop_prop_source``.
        """
        rel = Relationship(
            source="s",
            target="t",
            type="links",
            id="r1",
            properties={"source": "promoted-collision", "prop_source": "user-column"},
        )
        result = flatten_edge(rel)
        assert result["source"] == "s"
        assert result["prop_source"] == "user-column"
        assert result["prop_prop_source"] == "promoted-collision"

    def test_edge_scalar_properties_encoded(self):
        rel = _make_rel(properties={"weight": 2.5, "active": True, "note": "ok"})
        result = flatten_edge(rel)
        assert result["weight"] == 2.5
        assert result["active"] is True
        assert result["note"] == "ok"

    def test_edge_none_property(self):
        rel = _make_rel(properties={"optional": None})
        assert flatten_edge(rel)["optional"] == ""


# ---------------------------------------------------------------------------
# 12. Hypothesis property test
# ---------------------------------------------------------------------------

_scalar_strategy = st.one_of(
    st.text(),
    st.integers(),
    st.floats(allow_nan=False),
    st.booleans(),
    st.none(),
    st.lists(st.text()),
    st.dictionaries(st.text(), st.text()),
)


@given(
    entity_id=st.text(min_size=1),
    types=st.lists(st.text()),
    properties=st.dictionaries(st.text(), _scalar_strategy),
)
@settings(max_examples=200)
def test_flatten_node_never_raises_and_returns_scalars(entity_id, types, properties):
    """flatten_node must not raise and must return only scalar values."""
    entity = Entity(id=entity_id, types=types, properties=properties)
    result = flatten_node(entity)
    assert isinstance(result, dict)
    for key, value in result.items():
        assert isinstance(key, str), f"Key {key!r} is not a string"
        assert isinstance(value, (str, int, float, bool)), (
            f"Value for {key!r} is {type(value).__name__!r}, not a scalar: {value!r}"
        )
