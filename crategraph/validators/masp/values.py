"""Value checks for the MASP validator: literal ranges, PropertyValue rules,
ItemList and template matching.

These are pure functions over plain Python values. Ported from the JS
validator (``isValidInteger``, ``isValidDate``, ``valuesEquivalent``,
``parseRegexLiteral``, ``matchesPropertyValueConstraint``, ``matchesItem`` and
``matchesProfileEntity``), with the deliberate differences noted inline.
"""

from __future__ import annotations

import re
from typing import Any

from crategraph.validators.masp.context import normalise_iri
from crategraph.validators.masp.document import Node, is_reference, literal_of
from crategraph.validators.masp.profile import ItemListRule, PropertyValueRule

_RDFS_LITERAL = "http://www.w3.org/2000/01/rdf-schema#Literal"
_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")
_NUMBER_RE = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$")
_DATE_RE = re.compile(
    r"^([0-9]{4})(?:-([0-9]{2})(?:-([0-9]{2}))?)?"
    r"(?:T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:\.[0-9]+)?(?:Z|[+-]([0-9]{2}):([0-9]{2}))?)?$"
)
_DAYS_IN_MONTH = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
_FLAG_MAP = {"i": re.I, "m": re.M, "s": re.S}
_IGNORED_FLAGS = frozenset("gyu")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _strip_quotes(text: str) -> str:
    """Trim, then strip one pair of matching quotes (as the JS does)."""
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1].strip()
    return text


def _is_integer(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    if isinstance(value, str):
        return bool(_INTEGER_RE.match(_strip_quotes(value)))
    return False


def _is_number_value(value: Any) -> bool:
    if _is_number(value):
        return True
    if isinstance(value, str):
        return bool(_NUMBER_RE.match(value.strip()))
    return False


def _is_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    import validators

    return bool(validators.url(value))


def _is_date(value: Any) -> bool:
    """The JS date language plus a real calendar check (difference 13)."""
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, float):
        if not value.is_integer():
            return False
        text = str(int(value))
    elif isinstance(value, str):
        text = _strip_quotes(value)
    else:
        return False
    match = _DATE_RE.match(text)
    if match is None:
        return False
    year, month, day, hour, minute, second, tz_hour, tz_minute = match.groups()
    if month is not None:
        if not 1 <= int(month) <= 12:
            return False
        if day is not None:
            limit = _DAYS_IN_MONTH[int(month) - 1]
            y = int(year)
            if int(month) == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
                limit = 29
            if not 1 <= int(day) <= limit:
                return False
    if hour is not None and (int(hour) > 23 or int(minute) > 59 or int(second) > 59):
        return False
    return not (tz_hour is not None and (int(tz_hour) > 23 or int(tz_minute) > 59))


def check_literal(value: Any, range_iri: str) -> bool:
    """True when the literal *value* is acceptable for the range *range_iri*."""
    value = literal_of(value)
    iri = normalise_iri(range_iri)
    # JS l.1913-1914: any leading https: is compared as http:.
    if iri.startswith("https:"):
        iri = "http:" + iri[len("https:") :]

    def is_type(name: str) -> bool:
        return iri == f"http://schema.org/{name}" or iri == name

    if is_type("Text"):
        return isinstance(value, str)
    if iri == _RDFS_LITERAL or iri == "rdfs:Literal":
        return isinstance(value, (str, int, float, bool))
    if is_type("URL"):
        return _is_url(value)
    if is_type("Integer"):
        return _is_integer(value)
    if is_type("Number"):
        return _is_number_value(value)
    if is_type("Boolean"):
        return isinstance(value, bool)
    if is_type("Date") or is_type("DateTime"):
        return _is_date(value)
    return False


def parse_regex_literal(text: Any) -> tuple[re.Pattern[str], str] | None:
    """Parse ``/pattern/flags`` into a compiled pattern and unsupported flags.

    Returns ``None`` when *text* is not of that form or the pattern does not
    compile. ``g``, ``y`` and ``u`` are ignored; flags other than ``i``, ``m``,
    ``s`` and those are returned as a string of unsupported flags.
    """
    if not isinstance(text, str) or len(text) < 2 or text[0] != "/":
        return None
    last = text.rfind("/")
    if last <= 0:
        return None
    pattern, flags = text[1:last], text[last + 1 :]
    compiled_flags = 0
    unsupported = ""
    for flag in flags:
        if flag in _FLAG_MAP:
            compiled_flags |= _FLAG_MAP[flag]
        elif flag not in _IGNORED_FLAGS:
            unsupported += flag
    try:
        return re.compile(pattern, compiled_flags), unsupported
    except re.error:
        return None


def _same(a: Any, b: Any) -> bool:
    """Strict equality like JS ``===`` (a bool never equals a number)."""
    if isinstance(a, bool) != isinstance(b, bool):
        return False
    if isinstance(a, (dict, list)) or isinstance(b, (dict, list)):
        return False  # distinct JS objects are never ===
    return a == b


def _ref_id(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("@id") or None
    return None


def values_equivalent(actual: Any, expected: Any) -> bool:
    """Equality where a reference also equals a string holding its id."""
    actual_id = _ref_id(actual)
    expected_id = _ref_id(expected)
    if actual_id and expected_id:
        return actual_id == expected_id
    if actual_id and isinstance(expected, str):
        return actual_id == expected
    if expected_id and isinstance(actual, str):
        return expected_id == actual
    return _same(actual, expected)


def matches_property_value(value: Any, rule: PropertyValueRule) -> bool:
    """Check *value* against a PropertyValue rule (regexes, then literals)."""
    if not rule.values:
        return False
    scalar = _ref_id(value) or value

    regexes: list[re.Pattern[str]] = []
    literals: list[Any] = []
    for expected in rule.values:
        parsed = parse_regex_literal(expected)
        if parsed is not None:
            regexes.append(parsed[0])
        else:
            literals.append(expected)

    if regexes:
        if not isinstance(scalar, str):
            return False
        # Difference 7: search semantics, as JS ``RegExp.test``.
        if not all(regex.search(scalar) for regex in regexes):
            return False

    if not literals:
        return bool(regexes)
    return any(
        values_equivalent(value, expected) or values_equivalent(scalar, expected)
        for expected in literals
    )


def _expected_properties(
    element: Node | dict,
) -> tuple[Any, tuple[Any, ...], dict[str, list[Any]]]:
    if isinstance(element, Node):
        return element.id, element.types, element.properties
    props = {
        key: list(val) if isinstance(val, list) else [val]
        for key, val in element.items()
        if key not in ("@id", "@type")
    }
    raw_type = element.get("@type", [])
    types = tuple(raw_type) if isinstance(raw_type, list) else (raw_type,)
    return element.get("@id"), types, props


def _item_values_equal(expected: Any, actual: Any) -> bool:
    if is_reference(expected) and expected["@id"] and is_reference(actual) and actual["@id"]:
        return expected["@id"] == actual["@id"]
    return _same(expected, actual)


def _matches_item(actual: Node, element: Node | dict) -> bool:
    element_id, expected_types, expected_props = _expected_properties(element)
    if element_id is None or element_id != actual.id:
        return False
    if any(t not in actual.types for t in expected_types):
        return False
    for prop, expected_values in expected_props.items():
        actual_values = actual.properties.get(prop)
        if not actual_values:
            return False
        for expected in expected_values:
            if not any(_item_values_equal(expected, a) for a in actual_values):
                return False
    return True


def matches_item_list(actual: Node, rule: ItemListRule) -> bool:
    """True when *actual* matches any element of the item list.

    A reference never equals a string here (contrast ``matches_template``).
    """
    return any(_matches_item(actual, element) for element in rule.elements)


def matches_template(actual: Node, template: Node) -> bool:
    """True when *actual* has the template's id and every template value."""
    if actual.id != template.id:
        return False
    if any(t not in actual.types for t in template.types):
        return False
    for prop, expected_values in template.properties.items():
        actual_values = actual.properties.get(prop)
        if not actual_values:
            return False
        for expected in expected_values:
            if not any(values_equivalent(a, expected) for a in actual_values):
                return False
    return True
