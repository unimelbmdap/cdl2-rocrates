"""Tests for crategraph.core.models — Entity, Relationship, and Pydantic models."""

from __future__ import annotations

import pytest

from crategraph.core.models import (
    Entity,
    FileTree,
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
        e = Entity(id="./", types=["Dataset"])
        assert e.has_data is False

    def test_root_dataset_excluded_via_raw_id(self):
        """Multi-crate entities store original ID as raw_id."""
        e = Entity(id="mycrate/./", types=["Dataset"], properties={"raw_id": "./"})
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


# --- FileTree ---


class TestFileTree:
    def test_empty(self):
        tree = FileTree([])
        assert len(tree) == 0
        assert list(tree) == []
        assert not tree
        assert repr(tree) == "FileTree (0 files)"

    def test_single_file(self):
        e = Entity(id="data.csv", types=["File"], properties={"encodingFormat": "text/csv"})
        tree = FileTree([e])
        assert len(tree) == 1
        assert list(tree) == [e]
        assert tree[0] is e
        assert tree
        assert "data.csv" in repr(tree)
        assert "text/csv" in repr(tree)
        assert "1 file)" in repr(tree)

    def test_flat_tree_repr(self):
        entities = [
            Entity(id="a.txt", types=["File"], properties={"encodingFormat": "text/plain"}),
            Entity(id="b.csv", types=["File"], properties={"encodingFormat": "text/csv"}),
        ]
        tree = FileTree(entities)
        text = repr(tree)
        assert "FileTree (2 files)" in text
        assert "a.txt (text/plain)" in text
        assert "b.csv (text/csv)" in text
        # Last item should use └, others ├
        assert "├── a.txt" in text
        assert "└── b.csv" in text

    def test_nested_tree_repr(self):
        entities = [
            Entity(
                id="docs/report.pdf",
                types=["File"],
                properties={"encodingFormat": "application/pdf"},
            ),
            Entity(
                id="docs/notes.txt", types=["File"], properties={"encodingFormat": "text/plain"}
            ),
            Entity(
                id="images/photo.png", types=["File"], properties={"encodingFormat": "image/png"}
            ),
        ]
        tree = FileTree(entities)
        text = repr(tree)
        assert "docs/" in text
        assert "report.pdf" in text
        assert "images/" in text
        assert "photo.png" in text

    def test_web_based_entity(self):
        e = Entity(
            id="https://example.com/data.pdf",
            types=["File"],
            properties={"encodingFormat": "application/pdf"},
        )
        tree = FileTree([e])
        text = repr(tree)
        assert "https://example.com/data.pdf" in text
        assert "[web]" in text

    def test_multi_crate_grouping(self):
        """Multi-crate entities use raw_id for tree, but prefixed id groups by crate."""
        entities = [
            Entity(
                id="crate-a/data.csv",
                types=["File"],
                properties={"raw_id": "data.csv", "encodingFormat": "text/csv"},
            ),
            Entity(
                id="crate-b/image.png",
                types=["File"],
                properties={"raw_id": "image.png", "encodingFormat": "image/png"},
            ),
        ]
        tree = FileTree(entities)
        text = repr(tree)
        # raw_id is used for tree structure, so these are flat
        assert "data.csv" in text
        assert "image.png" in text

    def test_dataset_directory(self):
        e = Entity(id="subdir/", types=["Dataset"])
        tree = FileTree([e])
        text = repr(tree)
        assert "subdir" in text

    def test_no_encoding_format(self):
        e = Entity(id="mystery.bin", types=["File"])
        tree = FileTree([e])
        text = repr(tree)
        assert "mystery.bin" in text
        # No parenthesised media type
        assert "()" not in text

    def test_iteration(self):
        entities = [
            Entity(id="a.txt", types=["File"]),
            Entity(id="b.txt", types=["File"]),
        ]
        tree = FileTree(entities)
        assert [e.id for e in tree] == ["a.txt", "b.txt"]

    def test_repr_html(self):
        e = Entity(id="data.csv", types=["File"])
        tree = FileTree([e])
        html = tree._repr_html_()
        assert "<pre" in html
        assert "data.csv" in html


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
