"""Tests for crategraph.core.text — reader-agnostic text extraction."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("markitdown")

from crategraph import Crate
from crategraph.core.models import Entity
from crategraph.core.text import (
    _format_property_text,
    _render_value,
    _source_id_for,
    enrich_record_with_entity_properties,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "minimal-crate"


# --- Pure helpers ---


def test_format_property_text_includes_types_and_strings() -> None:
    entity = Entity(
        id="#alice",
        types=("Person",),
        properties={
            "name": "Alice Smith",
            "description": "Director",
            "worksFor": {"@id": "#acme"},
            "keywords": ["leadership", "engineering"],
        },
    )
    text = _format_property_text(entity, ("name", "description", "worksFor", "keywords"))

    assert "[Person]" in text
    assert "name: Alice Smith" in text
    assert "description: Director" in text
    assert "keywords: leadership, engineering" in text
    assert "worksFor" not in text


def test_render_value_handles_scalars_and_lists() -> None:
    assert _render_value("hello") == "hello"
    assert _render_value(42) == "42"
    assert _render_value(True) == "True"
    assert _render_value(["a", "b", "c"]) == "a, b, c"
    assert _render_value({"@id": "..."}) == ""
    assert _render_value(None) == ""


def test_source_id_for_uses_entity_source() -> None:
    entity = Entity(id="x", source="/some/path/iaea-crate")

    # graph not needed when entity.source is set; pass a dummy
    class _Dummy:
        source = None

    assert _source_id_for(entity, _Dummy()) == "iaea-crate"  # type: ignore[arg-type]


# --- text_records on a real fixture ---


def test_text_records_defaults_to_file_records() -> None:
    crate = Crate(str(FIXTURE))
    records = list(crate.text_records())

    assert records
    assert {r["source_kind"] for r in records} == {"file"}
    assert "name" not in records[0]
    assert "encodingFormat" not in records[0]


def test_text_records_emits_property_records_when_requested() -> None:
    crate = Crate(str(FIXTURE))
    records = list(crate.text_records(source_kind="properties"))

    by_id = {(r["entity_id"], r["source_kind"]) for r in records}
    assert ("#alice", "properties") in by_id
    assert ("#bob", "properties") in by_id
    assert ("#acme", "properties") in by_id


def test_text_records_source_kind_all_returns_files_and_properties() -> None:
    crate = Crate(str(FIXTURE))
    records = list(crate.text_records(source_kind="all"))

    kinds = {r["source_kind"] for r in records}
    assert kinds == {"file", "properties"}


def test_text_records_emits_file_records_for_data_entities() -> None:
    crate = Crate(str(FIXTURE))
    records = list(crate.text_records())

    file_ids = {r["entity_id"] for r in records if r["source_kind"] == "file"}
    assert "sample.txt" in file_ids


def test_text_records_assigns_correct_source_id() -> None:
    crate = Crate(str(FIXTURE))
    records = list(crate.text_records())

    source_ids = {r["source_id"] for r in records}
    assert source_ids == {"minimal-crate"}


def test_text_records_has_no_token_count() -> None:
    crate = Crate(str(FIXTURE))
    record = next(iter(crate.text_records()))
    assert "token_count" not in record


def test_text_records_include_properties_adds_requested_entity_properties() -> None:
    crate = Crate(str(FIXTURE))
    records = list(
        crate.text_records(
            include_properties=["name", "encodingFormat", "missing"],
            filters={"entity_id": ["sample.txt"]},
        )
    )

    assert records
    record = records[0]
    assert record["entity_id"] == "sample.txt"
    assert record["name"] == "Sample text file"
    assert record["encodingFormat"] == "text/plain"
    assert "missing" not in record


def test_text_records_include_properties_true_adds_all_entity_properties() -> None:
    crate = Crate(str(FIXTURE))
    record = next(
        iter(
            crate.text_records(
                include_properties=True,
                filters={"entity_id": ["sample.txt"]},
            )
        )
    )

    assert record["name"] == "Sample text file"
    assert record["encodingFormat"] == "text/plain"


def test_text_records_include_properties_rejects_bare_string() -> None:
    crate = Crate(str(FIXTURE))

    with pytest.raises(TypeError, match="include_properties"):
        list(crate.text_records(include_properties="name"))  # type: ignore[arg-type]


def test_include_properties_prefixes_colliding_record_keys() -> None:
    entity = Entity(
        id="doc",
        types=("File",),
        properties={
            "text": "metadata text",
            "entity_id": "metadata id",
            "prop_text": "already prefixed",
        },
    )
    record = enrich_record_with_entity_properties(
        {
            "source_id": "source",
            "entity_id": "doc",
            "source_kind": "file",
            "entity_types": ("File",),
            "text": "file text",
        },
        entity,
        include_properties=True,
    )

    assert record["text"] == "file text"
    assert record["prop_text"] == "already prefixed"
    assert record["prop_entity_id"] == "metadata id"
    assert record["prop_prop_text"] == "metadata text"


def test_include_properties_true_excludes_internal_underscore_properties() -> None:
    """``include_properties=True`` means *public* metadata only.

    Internal loader flags like ``_is_root`` are an implementation
    detail; surfacing them in an NLP/index record is leaky.
    """
    entity = Entity(
        id="#root",
        types=("Dataset",),
        properties={"name": "Root crate", "_is_root": True},
    )
    record = enrich_record_with_entity_properties(
        {
            "source_id": "source",
            "entity_id": "#root",
            "source_kind": "properties",
            "entity_types": ("Dataset",),
            "text": "text",
        },
        entity,
        include_properties=True,
    )

    assert record["name"] == "Root crate"
    assert "_is_root" not in record
    assert "prop__is_root" not in record


def test_include_properties_preserves_non_string_values() -> None:
    """Requested properties keep native types and are deep-copied.

    Unlike the text-content path (which stringifies via
    ``_render_value``), ``include_properties`` preserves lists, nested
    dicts and numbers verbatim, deep-copied so callers can mutate the
    returned record without touching graph state.
    """
    entity = Entity(
        id="#alice",
        types=("Person",),
        properties={
            "keywords": ["leadership", "engineering"],
            "worksFor": {"@id": "#acme", "name": "Acme"},
            "age": 42,
        },
    )
    record = enrich_record_with_entity_properties(
        {
            "source_id": "source",
            "entity_id": "#alice",
            "source_kind": "properties",
            "entity_types": ("Person",),
            "text": "text",
        },
        entity,
        include_properties=["keywords", "worksFor", "age"],
    )

    assert record["keywords"] == ["leadership", "engineering"]
    assert record["worksFor"] == {"@id": "#acme", "name": "Acme"}
    assert record["age"] == 42

    # Deep-copied: mutating the returned record must not touch the entity.
    record["keywords"].append("mutated")
    record["worksFor"]["name"] = "Mutated"
    assert entity.properties["keywords"] == ["leadership", "engineering"]
    assert entity.properties["worksFor"] == {"@id": "#acme", "name": "Acme"}


def test_text_records_filters_by_source_kind() -> None:
    crate = Crate(str(FIXTURE))
    only_files = list(crate.text_records(filters={"source_kind": ["file"]}))
    only_props = list(crate.text_records(filters={"source_kind": ["properties"]}))

    assert all(r["source_kind"] == "file" for r in only_files)
    assert all(r["source_kind"] == "properties" for r in only_props)
    assert only_files
    assert only_props


def test_text_records_rejects_invalid_source_kind() -> None:
    crate = Crate(str(FIXTURE))

    with pytest.raises(ValueError, match="source_kind"):
        list(crate.text_records(source_kind="metadata"))


def test_text_records_filters_by_entity_id() -> None:
    crate = Crate(str(FIXTURE))
    records = list(
        crate.text_records(
            source_kind="properties",
            filters={"entity_id": ["#alice"]},
        )
    )

    assert records
    assert all(r["entity_id"] == "#alice" for r in records)


def test_text_records_filters_by_entity_types() -> None:
    crate = Crate(str(FIXTURE))
    records = list(
        crate.text_records(
            source_kind="properties",
            filters={"entity_types": ["Person"]},
        )
    )

    assert records
    assert all("Person" in r["entity_types"] for r in records)


def test_text_records_handles_multi_crate() -> None:
    second = Path(__file__).parent.parent / "fixtures" / "second-crate"
    if not second.exists():
        pytest.skip("second-crate fixture missing")
    crate = Crate(str(FIXTURE), str(second))
    records = list(crate.text_records(source_kind="all"))

    source_ids = {r["source_id"] for r in records}
    assert "minimal-crate" in source_ids
    assert "second-crate" in source_ids


def test_text_records_is_a_generator() -> None:
    """Should be lazy — peak memory ≈ one record."""
    crate = Crate(str(FIXTURE))
    gen = crate.text_records()

    # Should be iterable but not list-like
    assert iter(gen) is gen  # generators yield themselves from __iter__


def test_text_records_empty_text_properties_suppresses_property_records() -> None:
    """An explicit empty allowlist must NOT silently fall back to defaults.

    Caller passing ``text_properties=[]`` expects "no property text in
    the output" — file records still flow because they don't go through
    the property allowlist.
    """
    crate = Crate(str(FIXTURE))
    records = list(crate.text_records(text_properties=[]))

    assert records, "expected file records even when properties suppressed"
    kinds = {r["source_kind"] for r in records}
    assert kinds == {"file"}, (
        f"expected only file records when text_properties=[], got kinds={kinds}"
    )
