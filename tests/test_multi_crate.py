"""Tests for multi-crate loading via Crate(*paths)."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate

FIXTURES = Path(__file__).parent / "fixtures"
MINIMAL = str(FIXTURES / "minimal-crate")
SECOND = str(FIXTURES / "second-crate")


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
        # minimal: 8 entities, second: 3 entities = 11 total
        assert len(crate) == 11

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
        rels = [
            r for r in crate.relationships if r.id == "minimal-crate/#rel-alice-acme"
        ]
        assert len(rels) == 1
        assert rels[0].source == "minimal-crate/#alice"
        assert rels[0].target == "minimal-crate/#acme"

    def test_select_by_source_recovers_subgraph(self):
        crate = Crate(MINIMAL, SECOND)
        minimal_only = crate.select(source="minimal-crate")
        assert len(minimal_only) == 8
        second_only = crate.select(source="second-crate")
        assert len(second_only) == 3

    def test_entity_source_field_set(self):
        crate = Crate(MINIMAL, SECOND)
        alice = crate._entities["minimal-crate/#alice"]
        assert "minimal-crate" in alice.source

    def test_boilerplate_ids_prefixed(self):
        crate = Crate(MINIMAL, SECOND)
        assert "minimal-crate/./" in crate._entities
        assert "second-crate/./" in crate._entities

    def test_graph_source_is_none_for_multi(self):
        """graph.source should be None when multiple crates are loaded."""
        crate = Crate(MINIMAL, SECOND)
        assert crate.source is None


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
