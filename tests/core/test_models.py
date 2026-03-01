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

    def test_equality(self):
        a = Entity(id="x", types=["Thing"])
        b = Entity(id="x", types=["Thing"])
        assert a == b

    def test_different_entities_not_equal(self):
        a = Entity(id="x", types=["Thing"])
        b = Entity(id="y", types=["Thing"])
        assert a != b


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
