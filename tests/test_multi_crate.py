"""Tests for multi-crate loading via Crate(*paths)."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate

FIXTURES = Path(__file__).parent / "fixtures"
MINIMAL = str(FIXTURES / "minimal-crate")
SECOND = str(FIXTURES / "second-crate")
ARCP_ROOT = str(FIXTURES / "arcp-root-crate")


class TestSinglePathBackwardsCompatible:
    """Single-path loading must remain unchanged."""

    def test_single_path_no_prefix(self):
        crate = Crate(MINIMAL)
        assert "#alice" in crate._entities

    def test_single_path_no_raw_id(self):
        crate = Crate(MINIMAL)
        alice = crate._entities["#alice"]
        assert "raw_id" not in alice.properties

    def test_single_path_source_set(self):
        crate = Crate(MINIMAL)
        assert crate.source is not None


class TestMultiCrateLoading:
    """Loading multiple crates into one graph."""

    def test_entities_from_both_crates(self):
        crate = Crate(MINIMAL, SECOND)
        # minimal: 7 entities, second: 2 entities = 9 total (roots excluded)
        assert len(crate) == 9

    def test_ids_prefixed_by_directory(self):
        crate = Crate(MINIMAL, SECOND)
        assert "minimal-crate/#alice" in crate._entities
        assert "second-crate/#alice" in crate._entities

    def test_raw_id_property_set(self):
        crate = Crate(MINIMAL, SECOND)
        alice_min = crate._entities["minimal-crate/#alice"]
        alice_sec = crate._entities["second-crate/#alice"]
        assert alice_min.properties["raw_id"] == "#alice"
        assert alice_sec.properties["raw_id"] == "#alice"

    def test_relationships_use_prefixed_ids(self):
        crate = Crate(MINIMAL, SECOND)
        # Bob's worksFor should use prefixed IDs.
        bob_rels = [r for r in crate.relationships if r.source == "minimal-crate/#bob"]
        assert len(bob_rels) > 0
        for rel in bob_rels:
            assert rel.target.startswith("minimal-crate/")

    def test_reified_relationship_prefixed(self):
        crate = Crate(MINIMAL, SECOND)
        rels = [r for r in crate.relationships if r.id == "minimal-crate/#rel-alice-acme"]
        assert len(rels) == 1
        assert rels[0].source == "minimal-crate/#alice"
        assert rels[0].target == "minimal-crate/#acme"

    def test_select_by_source_recovers_subgraph(self):
        crate = Crate(MINIMAL, SECOND)
        minimal_only = crate.select(source="minimal-crate")
        assert len(minimal_only) == 7
        second_only = crate.select(source="second-crate")
        assert len(second_only) == 2

    def test_select_by_source_updates_sources(self):
        crate = Crate(MINIMAL, SECOND)
        minimal_only = crate.select(source="minimal-crate")
        assert minimal_only.sources == ["minimal-crate"]

    def test_entity_source_field_set(self):
        crate = Crate(MINIMAL, SECOND)
        alice = crate._entities["minimal-crate/#alice"]
        assert "minimal-crate" in alice.source

    def test_roots_excluded_by_default(self):
        crate = Crate(MINIMAL, SECOND)
        assert "minimal-crate/./" not in crate._entities
        assert "second-crate/./" not in crate._entities

    def test_include_root_restores_prefixed_roots(self):
        crate = Crate(MINIMAL, SECOND, include_root=True)
        assert "minimal-crate/./" in crate._entities
        assert "second-crate/./" in crate._entities
        assert len(crate) == 11

    def test_graph_source_is_none_for_multi(self):
        """graph.source should be None when multiple crates are loaded."""
        crate = Crate(MINIMAL, SECOND)
        assert crate.source is None

    def test_multi_crate_metadata_per_prefix(self):
        crate = Crate(MINIMAL, SECOND)
        assert "minimal-crate" in crate.metadata
        assert "second-crate" in crate.metadata
        assert crate.metadata["minimal-crate"]["name"] == "Minimal test crate"
        assert crate.metadata["second-crate"]["name"] == "Second test crate"


class TestMultiCrateMergeByRawId:
    """merge_nodes(by='raw_id') joins entities across crates."""

    def test_merge_collapses_shared_ids(self):
        crate = Crate(MINIMAL, SECOND)
        merged = crate.merge_nodes(by="raw_id")
        # Both crates have #alice — should merge into one node.
        alice_nodes = [e for e in merged.entities if e.id == "#alice"]
        assert len(alice_nodes) == 1
        assert alice_nodes[0].properties["count"] == 2

    def test_merge_preserves_unique_entities(self):
        crate = Crate(MINIMAL, SECOND)
        merged = crate.merge_nodes(by="raw_id")
        # #project-x only in second crate — should be its own node.
        px_nodes = [e for e in merged.entities if e.id == "#project-x"]
        assert len(px_nodes) == 1
        assert px_nodes[0].properties["count"] == 1


class TestDirectoryNameCollision:
    """Error when two paths share the same directory name."""

    def test_same_directory_name_raises(self):
        with pytest.raises(ValueError, match="same directory name"):
            Crate(MINIMAL, MINIMAL)

    def test_error_message_includes_name(self):
        with pytest.raises(ValueError, match="minimal-crate"):
            Crate(MINIMAL, MINIMAL)


class TestMultiCrateSourcesDisplay:
    """Sources display in repr, _repr_html_, and summary()."""

    def test_sources_property_multi_crate(self):
        crate = Crate(MINIMAL, SECOND)
        srcs = crate.sources
        assert "minimal-crate" in srcs
        assert "second-crate" in srcs
        assert len(srcs) == 2

    def test_sources_property_single_crate(self):
        crate = Crate(MINIMAL)
        srcs = crate.sources
        assert len(srcs) == 1
        assert "minimal-crate" in srcs

    def test_repr_shows_sources_multi_crate(self):
        crate = Crate(MINIMAL, SECOND)
        r = repr(crate)
        assert "sources=" in r
        assert "minimal-crate" in r
        assert "second-crate" in r

    def test_repr_no_sources_single_crate(self):
        crate = Crate(MINIMAL)
        r = repr(crate)
        assert "sources=" not in r

    def test_repr_html_shows_sources_multi_crate(self):
        crate = Crate(MINIMAL, SECOND)
        html = crate._repr_html_()
        assert "Sources:" in html
        assert "minimal-crate" in html
        assert "second-crate" in html

    def test_repr_html_no_sources_single_crate(self):
        crate = Crate(MINIMAL)
        html = crate._repr_html_()
        assert "Sources:" not in html

    def test_summary_shows_sources_multi_crate(self):
        crate = Crate(MINIMAL, SECOND)
        s = crate.summary()
        assert len(s.sources) == 2
        assert "minimal-crate" in s.sources
        assert "second-crate" in s.sources

    def test_summary_repr_shows_sources_multi_crate(self):
        crate = Crate(MINIMAL, SECOND)
        s = crate.summary()
        r = repr(s)
        assert "Sources:" in r
        assert "minimal-crate" in r
        assert "second-crate" in r

    def test_summary_repr_shows_source_single_crate(self):
        crate = Crate(MINIMAL)
        s = crate.summary()
        r = repr(s)
        assert "Source:" in r
        assert "Sources:" not in r


class TestRestoreRootSingleCrate:
    """_restore_root() reconstructs the root Dataset from metadata."""

    def test_restores_root_entity(self):
        crate = Crate(MINIMAL)
        assert "./" not in crate._entities
        crate._restore_root()
        assert "./" in crate._entities

    def test_restored_root_has_dataset_type(self):
        crate = Crate(MINIMAL)
        crate._restore_root()
        root = crate._entities["./"]
        assert root.types == ("Dataset",)

    def test_restored_root_has_metadata_properties(self):
        crate = Crate(MINIMAL)
        crate._restore_root()
        root = crate._entities["./"]
        assert root.properties["name"] == "Minimal test crate"
        assert (
            root.properties["description"]
            == "A crate with a few entities and relationships for testing."
        )

    def test_restored_root_has_source(self):
        crate = Crate(MINIMAL)
        crate._restore_root()
        root = crate._entities["./"]
        assert root.source is not None
        assert "minimal-crate" in root.source

    def test_noop_when_root_present(self):
        crate = Crate(MINIMAL, include_root=True)
        original_count = len(crate)
        crate._restore_root()
        assert len(crate) == original_count

    def test_context_excluded_from_properties(self):
        crate = Crate(MINIMAL)
        crate._restore_root()
        root = crate._entities["./"]
        assert "@context" not in root.properties


class TestRestoreRootMultiCrate:
    """_restore_root() reconstructs per-prefix root entities."""

    def test_restores_both_roots(self):
        crate = Crate(MINIMAL, SECOND)
        assert "minimal-crate/./" not in crate._entities
        assert "second-crate/./" not in crate._entities
        crate._restore_root()
        assert "minimal-crate/./" in crate._entities
        assert "second-crate/./" in crate._entities

    def test_restored_roots_have_correct_names(self):
        crate = Crate(MINIMAL, SECOND)
        crate._restore_root()
        min_root = crate._entities["minimal-crate/./"]
        sec_root = crate._entities["second-crate/./"]
        assert min_root.properties["name"] == "Minimal test crate"
        assert sec_root.properties["name"] == "Second test crate"

    def test_restored_roots_have_raw_id(self):
        crate = Crate(MINIMAL, SECOND)
        crate._restore_root()
        for prefix in ["minimal-crate", "second-crate"]:
            root = crate._entities[f"{prefix}/./"]
            assert root.properties["raw_id"] == "./"

    def test_noop_when_roots_present(self):
        crate = Crate(MINIMAL, SECOND, include_root=True)
        original_count = len(crate)
        crate._restore_root()
        assert len(crate) == original_count


class TestRestoreRootArcpCrate:
    """_restore_root() works with arcp:// root IDs."""

    def test_restores_arcp_root(self):
        crate = Crate(ARCP_ROOT)
        root_id = "arcp://name,test-collection"
        assert root_id not in crate._entities
        crate._restore_root()
        assert root_id in crate._entities

    def test_restored_arcp_root_has_metadata(self):
        crate = Crate(ARCP_ROOT)
        crate._restore_root()
        root = crate._entities["arcp://name,test-collection"]
        assert root.properties["name"] == "Test collection with arcp root"

    def test_restored_arcp_root_has_is_root_flag(self):
        crate = Crate(ARCP_ROOT)
        crate._restore_root()
        root = crate._entities["arcp://name,test-collection"]
        assert root.properties["_is_root"] is True

    def test_restored_arcp_root_has_data_false(self):
        crate = Crate(ARCP_ROOT)
        crate._restore_root()
        root = crate._entities["arcp://name,test-collection"]
        assert root.has_data is False

    def test_noop_when_arcp_root_present(self):
        crate = Crate(ARCP_ROOT, include_root=True)
        original_count = len(crate)
        crate._restore_root()
        assert len(crate) == original_count

    def test_root_id_excluded_from_restored_properties(self):
        crate = Crate(ARCP_ROOT)
        crate._restore_root()
        root = crate._entities["arcp://name,test-collection"]
        assert "_root_id" not in root.properties


class TestMultiCrateWithInlineRelations:
    """inline_relations parameter works with multiple crates."""

    def test_inline_false_multi_crate(self):
        crate = Crate(MINIMAL, SECOND, inline_relations=False)
        # Only reified relationships should be present.
        for rel in crate.relationships:
            assert rel.id is not None

    def test_inline_list_multi_crate(self):
        crate = Crate(MINIMAL, SECOND, inline_relations=["worksFor"])
        inline_rels = [r for r in crate.relationships if r.id is None]
        assert len(inline_rels) == 1
        assert inline_rels[0].type == "worksFor"
