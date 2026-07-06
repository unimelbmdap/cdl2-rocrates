"""Contract tests for ``ReadOnlyMapping``.

It replaces ``types.MappingProxyType`` behind the public ``.properties`` /
``derived_fields`` accessors, so it must keep the same guarantees while
displaying as a plain dict.
"""

import pytest

from crategraph.core._mapping import ReadOnlyMapping


def test_reprs_as_plain_dict() -> None:
    assert repr(ReadOnlyMapping({"a": 1})) == "{'a': 1}"


def test_top_level_mutation_raises() -> None:
    m = ReadOnlyMapping({"a": 1})
    with pytest.raises(TypeError):
        m["b"] = 2  # type: ignore[index]


def test_is_a_live_view_of_the_source() -> None:
    src = {"a": 1}
    m = ReadOnlyMapping(src)
    src["a"] = 99
    assert m["a"] == 99


def test_equals_plain_dict_and_other_mappings() -> None:
    assert ReadOnlyMapping({"a": 1}) == {"a": 1}
    assert ReadOnlyMapping({"a": 1}) == ReadOnlyMapping({"a": 1})
    assert ReadOnlyMapping({"a": 1}) != {"a": 2}


def test_unhashable_like_dict() -> None:
    with pytest.raises(TypeError):
        hash(ReadOnlyMapping({"a": 1}))


def test_copy_returns_independent_mutable_dict() -> None:
    src = {"a": 1}
    c = ReadOnlyMapping(src).copy()
    assert c == {"a": 1}
    assert isinstance(c, dict)
    c["b"] = 2  # mutable, and does not touch the source
    assert "b" not in src


def test_or_merges_into_plain_dict() -> None:
    merged = ReadOnlyMapping({"a": 1}) | {"b": 2}
    assert merged == {"a": 1, "b": 2}
    assert isinstance(merged, dict)
    # reverse operand order, right-hand wins on key clash (dict semantics)
    assert ({"a": 0} | ReadOnlyMapping({"a": 1})) == {"a": 1}
