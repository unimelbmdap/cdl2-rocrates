import re

import pytest

pytest.importorskip("rdflib")
pytest.importorskip("validators")

from crategraph.validators.masp.document import Node
from crategraph.validators.masp.profile import ItemListRule, PropertyValueRule
from crategraph.validators.masp.values import (
    check_literal,
    matches_item_list,
    matches_property_value,
    matches_template,
    parse_regex_literal,
    values_equivalent,
)


def node(node_id: str, **properties) -> Node:
    return Node(id=node_id, types=(), properties={k: list(v) for k, v in properties.items()})


def pv(*values, min_count=0, max_count=None) -> PropertyValueRule:
    return PropertyValueRule(
        id="#pv", values=tuple(values), min_count=min_count, max_count=max_count
    )


@pytest.mark.parametrize(
    "value,ok",
    [
        (5, True),
        (5.0, True),
        ("42", True),
        (' "7" ', True),
        ("4.2", False),
        (True, False),
        ("", False),
    ],
)
def test_integer(value, ok):
    assert check_literal(value, "http://schema.org/Integer") is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        (1.5, True),
        ("3.1", True),
        ("1e5", True),
        ("", False),
        ("  ", False),
        (True, False),
        ("abc", False),
        ("nan", False),
        ("inf", False),
        ("1_000", False),
    ],
)
def test_number_rejects_blank_bool_and_python_only_forms(value, ok):
    assert check_literal(value, "Number") is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("2024", True),
        ("2024-02-29", True),
        ("2024-13-01", False),
        ("2023-02-29", False),
        (2024, True),
        ("soon", False),
        ("2024-W01", False),
        ("20240101", False),
        ("2024-01-01T12:30", False),
        ("2024-01-01T12:30:00+10:00", True),
        ("2024-01-01T25:30:00Z", False),
        ("2024-01-01T12:61:00Z", False),
        (True, False),
    ],
)
def test_date(value, ok):
    assert check_literal(value, "https://schema.org/Date") is ok
    assert check_literal(value, "DateTime") is ok


def test_url_accepts_http_and_rejects_plain_text():
    assert check_literal("https://example.org/a", "http://schema.org/URL") is True
    assert check_literal("not a url", "URL") is False
    assert check_literal(5, "URL") is False


def test_text_rejects_number():
    assert check_literal("x", "https://schema.org/Text") is True
    assert check_literal(5, "Text") is False


def test_boolean():
    assert check_literal(True, "Boolean") is True
    assert check_literal("true", "Boolean") is False


def test_rdfs_literal():
    iri = "http://www.w3.org/2000/01/rdf-schema#Literal"
    for value in ("a", 1, 1.5, True):
        assert check_literal(value, iri) is True
        assert check_literal(value, "rdfs:Literal") is True
    assert check_literal(None, iri) is False
    assert check_literal(["a"], iri) is False


def test_unknown_range_is_false():
    assert check_literal("x", "http://schema.org/Thing") is False


def test_value_object_checked_as_literal():
    assert check_literal({"@value": "5"}, "Integer") is True
    assert check_literal({"@value": 5}, "Text") is False


def test_regex_flags_and_search_semantics():
    pattern, unsupported = parse_regex_literal("/^ab/i")
    assert unsupported == ""
    assert pattern.flags & re.I
    assert pattern.search("ABc")
    pattern, _ = parse_regex_literal("/b/")
    assert pattern.search("abc")
    pattern, unsupported = parse_regex_literal("/a.b/gsmyu")
    assert unsupported == ""
    assert pattern.flags & re.S and pattern.flags & re.M
    assert parse_regex_literal("abc") is None
    assert parse_regex_literal("/abc") is None
    assert parse_regex_literal("/") is None
    assert parse_regex_literal(5) is None
    assert parse_regex_literal("/(/") is None


def test_unsupported_regex_flag_reported():
    pattern, unsupported = parse_regex_literal("/a/dx")
    assert unsupported == "dx"
    assert pattern.search("a")


def test_property_value_literal_id_and_regex_matching():
    # No expected values.
    assert matches_property_value("a", pv()) is False
    # Literal match.
    assert matches_property_value("a", pv("a", "b")) is True
    assert matches_property_value("c", pv("a", "b")) is False
    # Reference compared by id, and as a bare id string.
    assert matches_property_value({"@id": "#x"}, pv("#x")) is True
    assert matches_property_value({"@id": "#x"}, pv({"@id": "#x"})) is True
    assert matches_property_value({"@id": "#y"}, pv("#x")) is False
    # Regex only.
    assert matches_property_value("hello", pv("/^h/")) is True
    assert matches_property_value("hello", pv("/^x/")) is False
    assert matches_property_value(5, pv("/5/")) is False
    # All regexes must match.
    assert matches_property_value("hello", pv("/^h/", "/o$/")) is True
    assert matches_property_value("hello", pv("/^h/", "/x$/")) is False
    # Regex plus literals: regexes must match and a literal must match too.
    assert matches_property_value("hello", pv("/^h/", "hello")) is True
    assert matches_property_value("hello", pv("/^h/", "other")) is False
    # Regex applies to the id of a reference.
    assert matches_property_value({"@id": "http://a/b"}, pv("/^http/")) is True
    # Booleans are not numbers.
    assert matches_property_value(True, pv(1)) is False
    assert matches_property_value(1, pv(1)) is True


def test_values_equivalent_id_vs_string():
    assert values_equivalent({"@id": "#a"}, "#a") is True
    assert values_equivalent("#a", {"@id": "#a"}) is True
    assert values_equivalent({"@id": "#a"}, {"@id": "#a"}) is True
    assert values_equivalent({"@id": "#a"}, {"@id": "#b"}) is False
    assert values_equivalent("a", "a") is True
    assert values_equivalent("a", "b") is False
    assert values_equivalent(1, True) is False


def test_template_match_requires_all_template_values():
    template = node("#t", name=["A", "B"])
    assert matches_template(node("#t", name=["A", "B", "C"]), template) is True
    assert matches_template(node("#t", name=["A"]), template) is False
    assert matches_template(node("#t"), template) is False
    assert matches_template(node("#other", name=["A", "B"]), template) is False
    assert matches_template(node("#t"), node("#t")) is True


def test_item_list_requires_matching_id_and_values():
    rule = ItemListRule(id="#l", elements=(node("#e", name=["A"]),))
    assert matches_item_list(node("#e", name=["A", "B"]), rule) is True
    assert matches_item_list(node("#e", name=["B"]), rule) is False
    assert matches_item_list(node("#e"), rule) is False
    assert matches_item_list(node("#z", name=["A"]), rule) is False


def test_item_list_accepts_unresolved_reference_element():
    rule = ItemListRule(id="#l", elements=({"@id": "#e"},))
    assert matches_item_list(node("#e", anything=["x"]), rule) is True
    assert matches_item_list(node("#f"), rule) is False


def test_item_list_reference_does_not_equal_string():
    rule = ItemListRule(id="#l", elements=(node("#e", about=[{"@id": "#x"}]),))
    assert matches_item_list(node("#e", about=[{"@id": "#x"}]), rule) is True
    assert matches_item_list(node("#e", about=["#x"]), rule) is False
    template = node("#e", about=[{"@id": "#x"}])
    assert matches_template(node("#e", about=["#x"]), template) is True


def test_item_list_dict_element_without_id_is_no_match():
    rule = ItemListRule(id="#l", elements=({"@value": "x"},))
    assert matches_item_list(node("#e"), rule) is False


def test_item_list_and_template_compare_types_as_written():
    actual = Node("#e", ("Thing",), {})
    assert matches_template(actual, Node("#e", ("Language",), {})) is False
    assert matches_template(actual, Node("#e", ("Thing",), {})) is True
    assert matches_template(Node("#e", ("Thing", "X"), {}), Node("#e", ("X",), {})) is True
    resolved = ItemListRule(id="#l", elements=(Node("#e", ("Language",), {}),))
    assert matches_item_list(actual, resolved) is False
    bare = ItemListRule(id="#l", elements=({"@id": "#e", "@type": "Language"},))
    assert matches_item_list(actual, bare) is False
    assert matches_item_list(Node("#e", ("Language",), {}), bare) is True


@pytest.mark.parametrize("range_iri", ["Integer", "Number", "Date"])
def test_non_ascii_digits_rejected(range_iri):
    value = "2024" if range_iri == "Date" else "42"
    assert check_literal(value, range_iri) is True
    arabic = value.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    assert check_literal(arabic, range_iri) is False


def test_date_accepts_integral_float_not_bool():
    assert check_literal(2024.0, "Date") is True
    assert check_literal(2024.5, "Date") is False
    assert check_literal(True, "Date") is False


def test_dicts_without_id_never_equivalent():
    assert values_equivalent({"@value": "x"}, {"@value": "x"}) is False
    rule = ItemListRule(id="#l", elements=(node("#e", p=[{"@value": "x"}]),))
    assert matches_item_list(node("#e", p=[{"@value": "x"}]), rule) is False


def test_https_rdfs_literal_range():
    assert check_literal("a", "https://www.w3.org/2000/01/rdf-schema#Literal") is True


@pytest.mark.parametrize(
    "value,ok",
    [
        ("0000-02-29", True),
        ("1900-02-29", False),
        ("2000-02-29", True),
        ("2024-01-01T12:00:00+24:00", False),
        ("2024-01-01T12:00:00+10:60", False),
        ("2024-01-01T12:00:00+10:00", True),
    ],
)
def test_calendar_decisions(value, ok):
    assert check_literal(value, "Date") is ok
