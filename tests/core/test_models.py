"""Tests for crategraph.core.models — Entity, Relationship, and Pydantic models."""

from __future__ import annotations

import pytest

from crategraph.core.models import (
    Entity,
    Relationship,
    SelectOptions,
    ValidationIssue,
    ValidationReport,
)

# --- Entity ---


class TestEntity:
    def test_create_minimal(self):
        e = Entity(id="./data.csv", types=["File"])
        assert e.id == "./data.csv"
        assert e.type == "File"
        assert e.properties == {}
        assert e.source is None

    def test_create_with_properties_and_source(self):
        e = Entity(
            id="#author1",
            types=["Person"],
            properties={"name": "Alice"},
            source="crate.zip",
        )
        assert e.properties["name"] == "Alice"
        assert e.source == "crate.zip"

    def test_frozen(self):
        e = Entity(id="x", types=["Thing"])
        with pytest.raises(AttributeError):
            e.id = "y"  # type: ignore[misc]

    def test_types_coerced_to_tuple(self):
        e = Entity(id="x", types=["Thing", "Other"])
        assert e.types == ("Thing", "Other")
        assert isinstance(e.types, tuple)

    def test_types_are_immutable(self):
        e = Entity(id="x", types=["Thing"])
        with pytest.raises(AttributeError):
            e.types.append("Other")  # type: ignore[attr-defined]

    def test_equality(self):
        a = Entity(id="x", types=["Thing"])
        b = Entity(id="x", types=["Thing"])
        assert a == b

    def test_different_entities_not_equal(self):
        a = Entity(id="x", types=["Thing"])
        b = Entity(id="y", types=["Thing"])
        assert a != b


# --- Entity.label ---


class TestEntityLabel:
    def test_label_prefers_name(self):
        e = Entity(id="x", properties={"name": "Doc", "title": "T"})
        assert e.label == "Doc"

    def test_label_falls_back_to_title_when_no_name(self):
        e = Entity(id="x", properties={"title": "My Paper"})
        assert e.label == "My Paper"

    def test_label_falls_back_to_id_when_no_name_or_title(self):
        e = Entity(id="x", properties={})
        assert e.label == "x"

    def test_label_coerces_non_string_name(self):
        e = Entity(id="x", properties={"name": 42})
        assert e.label == "42"

    def test_label_is_always_a_string(self):
        assert isinstance(Entity(id="x").label, str)


# --- Entity.has_data ---


class TestEntityHasData:
    def test_file_entity(self):
        e = Entity(id="data.csv", types=["File"])
        assert e.has_data is True

    def test_dataset_directory(self):
        e = Entity(id="subdir/", types=["Dataset"])
        assert e.has_data is True

    def test_multi_type_array(self):
        e = Entity(id="workflow.cwl", types=["File", "ComputationalWorkflow"])
        assert e.has_data is True

    def test_root_dataset_excluded(self):
        e = Entity(id="./", types=["Dataset"], properties={"_is_root": True})
        assert e.has_data is False

    def test_arcp_root_dataset_excluded(self):
        """Root datasets with non-./ IDs are excluded via _is_root flag."""
        e = Entity(
            id="arcp://name,test",
            types=["Dataset", "RepositoryCollection"],
            properties={"_is_root": True},
        )
        assert e.has_data is False

    def test_root_dataset_excluded_via_raw_id(self):
        """Multi-crate entities store original ID as raw_id."""
        e = Entity(
            id="mycrate/./",
            types=["Dataset"],
            properties={"raw_id": "./", "_is_root": True},
        )
        assert e.has_data is False

    def test_person_contextual_entity(self):
        e = Entity(id="#alice", types=["Person"])
        assert e.has_data is False

    def test_organisation_contextual_entity(self):
        e = Entity(id="#org1", types=["Organisation"])
        assert e.has_data is False

    def test_web_based_file_entity(self):
        e = Entity(id="https://example.com/file.pdf", types=["File"])
        assert e.has_data is True

    def test_creative_work_not_treated_as_data(self):
        e = Entity(id="ro-crate-metadata.json", types=["CreativeWork"])
        assert e.has_data is False

    def test_no_types(self):
        e = Entity(id="mystery")
        assert e.has_data is False


# --- Relationship ---


class TestRelationship:
    def test_create_minimal(self):
        r = Relationship(source="#a", target="#b", type="author")
        assert r.source == "#a"
        assert r.target == "#b"
        assert r.type == "author"
        assert r.properties == {}
        assert r.id is None

    def test_create_with_properties(self):
        r = Relationship(
            source="#a",
            target="#b",
            type="hasPart",
            properties={"weight": 1.0},
        )
        assert r.properties["weight"] == 1.0

    def test_reified_relationship_has_id(self):
        r = Relationship(
            source="#E000009",
            target="#E000020",
            type="Controlling",
            id="#E000020-E000009",
            properties={"startDate": "2 July 1998"},
        )
        assert r.id == "#E000020-E000009"
        assert r.type == "Controlling"
        assert r.properties["startDate"] == "2 July 1998"

    def test_frozen(self):
        r = Relationship(source="#a", target="#b", type="x")
        with pytest.raises(AttributeError):
            r.type = "y"  # type: ignore[misc]


# --- SelectOptions ---


class TestSelectOptions:
    def test_defaults_all_none(self):
        opts = SelectOptions()
        assert opts.entity_types is None
        assert opts.relationship_types is None
        assert opts.time_range is None
        assert opts.min_connections is None
        assert opts.max_connections is None
        assert opts.source is None
        assert opts.id is None

    def test_with_entity_types(self):
        opts = SelectOptions(entity_types=["Person", "File"])
        assert opts.entity_types == ["Person", "File"]

    def test_with_time_range(self):
        opts = SelectOptions(time_range=(2000, 2020))
        assert opts.time_range == (2000, 2020)


# --- ValidationIssue ---


class TestValidationIssue:
    def test_error_issue(self):
        issue = ValidationIssue(severity="error", message="Missing @id")
        assert issue.severity == "error"
        assert issue.entity_id is None
        assert issue.message == "Missing @id"

    def test_warning_with_entity(self):
        issue = ValidationIssue(severity="warning", entity_id="#x", message="No name")
        assert issue.entity_id == "#x"


# --- ValidationReport ---


class TestValidationReport:
    def test_empty_report_is_valid(self):
        report = ValidationReport(issues=[])
        assert report.is_valid is True

    def test_report_with_warning_is_valid(self):
        report = ValidationReport(issues=[ValidationIssue(severity="warning", message="minor")])
        assert report.is_valid is True

    def test_report_with_error_is_not_valid(self):
        report = ValidationReport(issues=[ValidationIssue(severity="error", message="bad")])
        assert report.is_valid is False

    def test_report_with_mixed_issues(self):
        report = ValidationReport(
            issues=[
                ValidationIssue(severity="info", message="ok"),
                ValidationIssue(severity="error", message="bad"),
                ValidationIssue(severity="warning", message="meh"),
            ]
        )
        assert report.is_valid is False
