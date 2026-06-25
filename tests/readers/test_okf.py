"""Tests for crategraph.readers.okf — OKFReader."""

from __future__ import annotations

import os
import warnings as _warnings
from pathlib import Path

import pytest

pytest.importorskip("yaml")
pytest.importorskip("markdown_it")

from crategraph.core.graph import Graph
from crategraph.readers import OKFReader

FIXTURES = Path(__file__).parent.parent / "fixtures"
OKF_BUNDLE = FIXTURES / "okf-bundle"
MINIMAL_CRATE = FIXTURES / "minimal-crate"


class TestCanRead:
    def test_conforming_bundle(self):
        assert OKFReader().can_read(str(OKF_BUNDLE))

    def test_nonexistent_path(self, tmp_path: Path):
        assert not OKFReader().can_read(str(tmp_path / "missing"))

    def test_file_path(self, tmp_path: Path):
        document = tmp_path / "concept.md"
        document.write_text("---\ntype: Concept\n---\n")
        assert not OKFReader().can_read(str(document))

    def test_empty_directory(self, tmp_path: Path):
        assert not OKFReader().can_read(str(tmp_path))

    def test_missing_type_is_not_conforming(self, tmp_path: Path):
        (tmp_path / "concept.md").write_text("---\ntitle: Untyped\n---\n")
        assert not OKFReader().can_read(str(tmp_path))

    def test_malformed_document_is_not_conforming(self, tmp_path: Path):
        (tmp_path / "concept.md").write_text("No frontmatter")
        assert not OKFReader().can_read(str(tmp_path))

    def test_defers_to_rocrate_reader(self):
        assert not OKFReader().can_read(str(MINIMAL_CRATE))


class TestReadBundle:
    def _load(self) -> Graph:
        return OKFReader().read(str(OKF_BUNDLE))

    def test_returns_graph(self):
        assert isinstance(self._load(), Graph)

    def test_concept_ids_are_paths_without_markdown_suffix(self):
        graph = self._load()
        assert set(graph._entities) == {
            "guides/query.sql",
            "metrics/weekly-active-users",
            "tables/customers",
            "tables/orders",
        }

    def test_reserved_documents_are_not_entities(self):
        graph = self._load()
        assert "index" not in graph._entities
        assert "log" not in graph._entities

    def test_type_maps_to_entity_types(self):
        entity = self._load().get("tables/orders")
        assert entity.types == ("BigQuery Table",)

    def test_frontmatter_is_preserved(self):
        entity = self._load().get("tables/orders")
        assert entity.properties["description"] == "One row per order."
        assert entity.properties["custom_field"] == {"steward": "Data Platform"}
        assert "type" not in entity.properties

    def test_body_is_stored_as_text(self):
        entity = self._load().get("metrics/weekly-active-users")
        assert "Weekly active users are calculated" in entity.properties["text"]

    def test_title_sets_name(self):
        entity = self._load().get("tables/orders")
        assert entity.properties["name"] == "Orders"

    def test_missing_title_falls_back_to_id_basename(self):
        entity = self._load().get("tables/customers")
        assert entity.properties["name"] == "customers"

    def test_document_path_and_source_are_recorded(self):
        entity = self._load().get("tables/orders")
        assert entity.properties["document_path"] == "tables/orders.md"
        assert entity.source == str(OKF_BUNDLE.resolve())

    def test_bundle_metadata_comes_from_root_index(self):
        graph = self._load()
        assert graph.metadata["format"] == "okf"
        assert graph.metadata["okf_version"] == "0.1"
        assert graph.metadata["title"] == "Example knowledge bundle"
        assert "example bundle" in graph.metadata["text"]

    def test_external_links_are_preserved_as_properties(self):
        entity = self._load().get("metrics/weekly-active-users")
        assert entity.properties["external_links"] == ["https://example.com/metrics"]

    def test_entity_order_is_deterministic(self):
        first = list(self._load()._entities)
        second = list(self._load()._entities)
        assert first == second == sorted(first)


class TestRelationships:
    def _load(self) -> Graph:
        return OKFReader().read(str(OKF_BUNDLE))

    def test_relative_link_becomes_relationship(self):
        graph = self._load()
        assert any(
            rel.source == "metrics/weekly-active-users"
            and rel.target == "tables/orders"
            and rel.type == "linksTo"
            for rel in graph.relationships
        )

    def test_root_absolute_link_becomes_relationship(self):
        graph = self._load()
        assert any(
            rel.source == "tables/orders" and rel.target == "metrics/weekly-active-users"
            for rel in graph.relationships
        )

    def test_reference_style_link_becomes_relationship(self):
        graph = self._load()
        rel = next(
            rel
            for rel in graph.relationships
            if rel.source == "metrics/weekly-active-users" and rel.target == "guides/query.sql"
        )
        assert rel.properties["label"] == "the SQL guide"
        assert rel.properties["href"] == "../guides/query.sql.md"

    def test_links_inside_code_are_ignored(self):
        graph = self._load()
        assert not any(
            rel.source == "metrics/weekly-active-users" and rel.target == "tables/customers"
            for rel in graph.relationships
        )

    def test_external_links_do_not_become_relationships(self):
        graph = self._load()
        assert all("example.com" not in rel.target for rel in graph.relationships)

    def test_relationship_order_is_deterministic(self):
        def triples(graph: Graph) -> list[tuple[str, str, str]]:
            return [(rel.source, rel.target, rel.type) for rel in graph.relationships]

        assert triples(self._load()) == triples(self._load())

    def test_parallel_link_occurrences_are_preserved(self, tmp_path: Path):
        (tmp_path / "a.md").write_text(
            "---\ntype: Concept\n---\n[first](b.md) and [second](b.md)\n"
        )
        (tmp_path / "b.md").write_text("---\ntype: Concept\n---\n")
        graph = OKFReader().read(str(tmp_path))
        links = [rel for rel in graph.relationships if rel.source == "a" and rel.target == "b"]
        assert [rel.properties["label"] for rel in links] == ["first", "second"]


class TestPermissiveLoading:
    def test_skips_malformed_documents_and_counts_them(self, tmp_path: Path):
        (tmp_path / "valid.md").write_text("---\ntype: Concept\n---\nValid")
        (tmp_path / "invalid.md").write_text("No frontmatter")

        with pytest.warns(UserWarning, match="Skipped OKF concept"):
            graph = OKFReader().read(str(tmp_path))

        assert set(graph._entities) == {"valid"}
        assert graph.metadata["skipped_document_count"] == 1

    def test_ignores_broken_links_and_counts_them(self, tmp_path: Path):
        (tmp_path / "valid.md").write_text("---\ntype: Concept\n---\n[Missing](missing.md)")

        with pytest.warns(UserWarning, match="broken OKF concept link"):
            graph = OKFReader().read(str(tmp_path))

        assert graph.relationships == []
        assert graph.metadata["broken_link_count"] == 1

    def test_fragment_only_links_are_ignored(self, tmp_path: Path):
        (tmp_path / "valid.md").write_text("---\ntype: Concept\n---\n[Section](#details)")
        with _warnings.catch_warnings(record=True) as recorded:
            _warnings.simplefilter("always")
            graph = OKFReader().read(str(tmp_path))
        assert graph.relationships == []
        assert "broken_link_count" not in graph.metadata
        assert recorded == []

    def test_links_to_reserved_documents_are_ignored(self, tmp_path: Path):
        (tmp_path / "valid.md").write_text("---\ntype: Concept\n---\n[Bundle index](index.md)")
        (tmp_path / "index.md").write_text("---\ntitle: Bundle\n---\n")
        with _warnings.catch_warnings(record=True) as recorded:
            _warnings.simplefilter("always")
            graph = OKFReader().read(str(tmp_path))
        assert graph.relationships == []
        assert "broken_link_count" not in graph.metadata
        assert recorded == []

    def test_traversal_links_are_ignored(self, tmp_path: Path):
        (tmp_path / "valid.md").write_text("---\ntype: Concept\n---\n[Outside](%2e%2e/outside.md)")
        with _warnings.catch_warnings(record=True) as recorded:
            _warnings.simplefilter("always")
            graph = OKFReader().read(str(tmp_path))
        assert graph.relationships == []
        assert "broken_link_count" not in graph.metadata
        assert recorded == []

    def test_missing_path_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            OKFReader().read(str(tmp_path / "missing"))

    def test_file_path_raises(self, tmp_path: Path):
        document = tmp_path / "concept.md"
        document.write_text("---\ntype: Concept\n---\n")
        with pytest.raises(NotADirectoryError):
            OKFReader().read(str(document))


def _make_symlink_or_skip(src: Path, dst: Path) -> None:
    try:
        os.symlink(src, dst)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not supported in this environment: {exc}")


def test_symlinked_concept_is_skipped(tmp_path: Path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("---\ntype: Concept\n---\nOutside")
    _make_symlink_or_skip(outside, bundle / "linked.md")
    (bundle / "valid.md").write_text("---\ntype: Concept\n---\nValid")

    graph = OKFReader().read(str(bundle))

    assert set(graph._entities) == {"valid"}


def test_text_property_participates_in_property_records():
    graph = OKFReader().read(str(OKF_BUNDLE))
    records = list(graph.text_records(source_kind="properties"))
    metric = next(
        record for record in records if record["entity_id"] == "metrics/weekly-active-users"
    )
    assert "Weekly active users are calculated" in metric["text"]


def test_text_property_participates_in_fuzzy_search():
    graph = OKFReader().read(str(OKF_BUNDLE))
    results = graph.search(
        "weekly active users are calculated",
        properties=["text"],
        threshold=80,
        top_n=0,
    )
    assert "metrics/weekly-active-users" in {entity.id for entity in results.entities}
