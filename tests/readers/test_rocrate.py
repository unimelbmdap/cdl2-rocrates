"""Tests for crategraph.readers.rocrate — ROCrateReader."""

from __future__ import annotations

from pathlib import Path

import pytest

from crategraph import Crate
from crategraph.readers.rocrate import ROCrateReader

FIXTURES = Path(__file__).parent.parent / "fixtures"
MINIMAL = FIXTURES / "minimal-crate"
QUIRKY = FIXTURES / "quirky-crate"
ARCP_ROOT = FIXTURES / "arcp-root-crate"


class TestCanRead:
    def test_directory_with_metadata(self):
        reader = ROCrateReader()
        assert reader.can_read(str(MINIMAL))

    def test_direct_file(self):
        reader = ROCrateReader()
        assert reader.can_read(str(MINIMAL / "ro-crate-metadata.json"))

    def test_nonexistent_path(self):
        reader = ROCrateReader()
        assert not reader.can_read("/nonexistent/path")

    def test_directory_without_metadata(self, tmp_path: Path):
        reader = ROCrateReader()
        assert not reader.can_read(str(tmp_path))


class TestReadMinimalCrate:
    def _load(self) -> Crate:
        return Crate(str(MINIMAL))

    def test_loads_entities(self):
        g = self._load()
        # alice + bob + acme + 4 Files = 7 entities.
        # Root dataset excluded by default; reified relationship is an edge.
        assert len(g) == 7

    def test_entity_types(self):
        g = self._load()
        assert "Person" in g.types
        assert "Organisation" in g.types
        assert "File" in g.types

    def test_entity_properties(self):
        g = self._load()
        alice = g._entities["#alice"]
        assert alice.properties["name"] == "Alice Smith"

    def test_source_set(self):
        g = self._load()
        assert g.source is not None
        assert "minimal-crate" in g.source

    def test_metadata_has_context(self):
        g = self._load()
        assert "@context" in g.metadata

    def test_metadata_has_root_properties(self):
        g = self._load()
        assert g.metadata["name"] == "Minimal test crate"
        assert "description" in g.metadata

    def test_root_excluded_by_default(self):
        g = self._load()
        assert "./" not in g._entities

    def test_include_root_restores_root_entity(self):
        g = Crate(str(MINIMAL), include_root=True)
        assert "./" in g._entities
        assert len(g) == 8
        assert "Dataset" in g.types

    def test_reified_relationship(self):
        g = self._load()
        rels = [r for r in g.relationships if r.id == "#rel-alice-acme"]
        assert len(rels) == 1
        rel = rels[0]
        assert rel.source == "#alice"
        assert rel.target == "#acme"
        assert rel.type == "Superior"
        assert rel.properties["description"] == "Alice is a director of ACME"

    def test_inline_id_ref(self):
        g = self._load()
        # Bob has worksFor: {"@id": "#acme"} → inline relationship.
        rels = [r for r in g.relationships if r.source == "#bob" and r.type == "worksFor"]
        assert len(rels) == 1
        assert rels[0].target == "#acme"
        assert rels[0].id is None  # Not reified.

    def test_entity_source_field(self):
        g = self._load()
        alice = g._entities["#alice"]
        assert alice.source is not None
        assert "minimal-crate" in alice.source


class TestReadQuirkyCrate:
    def _load(self) -> Crate:
        return Crate(str(QUIRKY))

    def test_leading_space_type_normalised(self):
        g = self._load()
        entity = g._entities["#entity1"]
        assert entity.type == "Source"  # Leading space stripped.

    def test_empty_type_becomes_unknown(self):
        g = self._load()
        entity = g._entities["#entity2"]
        assert entity.type == "Unknown"

    def test_url_encoded_id_decoded(self):
        g = self._load()
        assert "#Gavan McCarthy" in g._entities

    def test_full_uri_encoding_preserved(self):
        """Full URIs keep percent-encoding to avoid changing URI semantics."""
        from crategraph.readers.rocrate import ROCrateReader

        assert ROCrateReader._decode_id("arcp://name,doi10.25949%2F24629712.v1") == (
            "arcp://name,doi10.25949%2F24629712.v1"
        )
        assert ROCrateReader._decode_id("#Port%20of%20Spain") == "#Port of Spain"

    def test_null_description_preserved(self):
        g = self._load()
        func = g._entities["#func1"]
        assert func.properties["description"] is None

    def test_fparent_plain_string_preserved(self):
        g = self._load()
        func = g._entities["#func1"]
        assert func.properties["fparent"] == "F00002"

    def test_reified_relationship_in_quirky(self):
        g = self._load()
        rels = [r for r in g.relationships if r.id == "#rel-plain-string"]
        assert len(rels) == 1
        assert rels[0].type == "Related"


class TestReadErrors:
    def test_nonexistent_path_raises(self):
        reader = ROCrateReader()
        with pytest.raises(FileNotFoundError):
            reader.read("/nonexistent/path")

    def test_empty_directory_raises(self, tmp_path: Path):
        reader = ROCrateReader()
        with pytest.raises(FileNotFoundError, match=r"ro-crate-metadata\.json"):
            reader.read(str(tmp_path))


class TestTypeNormalisation:
    def test_none_type_becomes_unknown_list(self):
        reader = ROCrateReader()
        entity = reader._parse_entity({"@id": "#x", "@type": None}, source="fixture")
        assert entity is not None
        assert entity.types == ("Unknown",)


class TestInlineRelationsDefault:
    """inline_relations=True (default) — all inline refs become edges."""

    def _load(self) -> Crate:
        return Crate(str(MINIMAL))

    def test_default_includes_inline_edges(self):
        g = self._load()
        inline_rels = [r for r in g.relationships if r.id is None]
        assert len(inline_rels) > 0, "Expected at least one inline relationship"

    def test_default_includes_reified_edges(self):
        g = self._load()
        reified_rels = [r for r in g.relationships if r.id is not None]
        assert len(reified_rels) > 0, "Expected at least one reified relationship"

    def test_explicit_true_same_as_default(self):
        default = Crate(str(MINIMAL))
        explicit = Crate(str(MINIMAL), inline_relations=True)
        assert len(default.relationships) == len(explicit.relationships)


class TestInlineRelationsFalse:
    """inline_relations=False — only reified Relationship entities become edges."""

    def _load(self) -> Crate:
        return Crate(str(MINIMAL), inline_relations=False)

    def test_no_inline_edges(self):
        g = self._load()
        inline_rels = [r for r in g.relationships if r.id is None]
        assert len(inline_rels) == 0, "Expected no inline relationships"

    def test_reified_edges_still_present(self):
        g = self._load()
        reified_rels = [r for r in g.relationships if r.id is not None]
        assert len(reified_rels) > 0, "Reified relationships should still be present"

    def test_reified_edge_data_intact(self):
        g = self._load()
        rels = [r for r in g.relationships if r.id == "#rel-alice-acme"]
        assert len(rels) == 1
        assert rels[0].source == "#alice"
        assert rels[0].target == "#acme"
        assert rels[0].type == "Superior"

    def test_entity_count_unchanged(self):
        """Entities are always loaded — only edges are filtered."""
        g = self._load()
        default = Crate(str(MINIMAL))
        assert len(g) == len(default)


class TestInlineRelationsList:
    """inline_relations=[...] — only matching property names become edges."""

    def test_matching_property_creates_edge(self):
        g = Crate(str(MINIMAL), inline_relations=["worksFor"])
        inline_rels = [r for r in g.relationships if r.id is None]
        assert len(inline_rels) == 1
        assert inline_rels[0].type == "worksFor"
        assert inline_rels[0].source == "#bob"
        assert inline_rels[0].target == "#acme"

    def test_non_matching_property_skipped(self):
        g = Crate(str(MINIMAL), inline_relations=["preparedBy"])
        inline_rels = [r for r in g.relationships if r.id is None]
        assert len(inline_rels) == 0, "worksFor should be excluded"

    def test_reified_edges_still_present_with_list(self):
        g = Crate(str(MINIMAL), inline_relations=["preparedBy"])
        reified_rels = [r for r in g.relationships if r.id is not None]
        assert len(reified_rels) > 0

    def test_empty_list_same_as_false(self):
        empty_list = Crate(str(MINIMAL), inline_relations=[])
        false_flag = Crate(str(MINIMAL), inline_relations=False)
        assert len(empty_list.relationships) == len(false_flag.relationships)

    def test_multiple_properties_in_list(self):
        g = Crate(str(MINIMAL), inline_relations=["worksFor", "preparedBy"])
        inline_rels = [r for r in g.relationships if r.id is None]
        # Only worksFor exists in the fixture, preparedBy doesn't — so 1 edge.
        assert len(inline_rels) == 1
        assert inline_rels[0].type == "worksFor"


class TestInlineRelationsTypeError:
    """Invalid inline_relations values raise TypeError."""

    def test_string_raises_type_error(self):
        with pytest.raises(TypeError, match="inline_relations must be bool or list"):
            Crate(str(MINIMAL), inline_relations="worksFor")

    def test_int_raises_type_error(self):
        with pytest.raises(TypeError, match="inline_relations must be bool or list"):
            Crate(str(MINIMAL), inline_relations=42)

    def test_none_raises_type_error(self):
        with pytest.raises(TypeError, match="inline_relations must be bool or list"):
            Crate(str(MINIMAL), inline_relations=None)

    def test_list_with_non_strings_raises_type_error(self):
        with pytest.raises(TypeError, match="list must contain only strings"):
            Crate(str(MINIMAL), inline_relations=["worksFor", 42])

    def test_reader_directly_validates(self):
        """TypeError is raised by ROCrateReader, not just Crate."""
        with pytest.raises(TypeError, match="inline_relations must be bool or list"):
            ROCrateReader(inline_relations="bad")


class TestRootIdDetection:
    """Root ID is detected from the metadata descriptor's ``about`` property."""

    def test_minimal_crate_root_id_is_dot_slash(self):
        reader = ROCrateReader(include_root=True)
        g = reader.read(str(MINIMAL))
        assert g.metadata["_root_id"] == "./"

    def test_arcp_root_id_detected(self):
        reader = ROCrateReader(include_root=True)
        g = reader.read(str(ARCP_ROOT))
        assert g.metadata["_root_id"] == "arcp://name,test-collection"

    def test_arcp_root_entity_in_graph_when_included(self):
        g = Crate(str(ARCP_ROOT), include_root=True)
        assert "arcp://name,test-collection" in g._entities

    def test_arcp_root_excluded_by_default(self):
        g = Crate(str(ARCP_ROOT))
        assert "arcp://name,test-collection" not in g._entities

    def test_arcp_root_metadata_promoted(self):
        g = Crate(str(ARCP_ROOT))
        assert g.metadata["name"] == "Test collection with arcp root"
        assert "description" in g.metadata

    def test_arcp_root_edges_excluded_by_default(self):
        g = Crate(str(ARCP_ROOT))
        root_id = "arcp://name,test-collection"
        for rel in g.relationships:
            assert rel.source != root_id
            assert rel.target != root_id

    def test_arcp_root_has_is_root_flag(self):
        g = Crate(str(ARCP_ROOT), include_root=True)
        root = g._entities["arcp://name,test-collection"]
        assert root.properties.get("_is_root") is True

    def test_minimal_root_has_is_root_flag(self):
        g = Crate(str(MINIMAL), include_root=True)
        root = g._entities["./"]
        assert root.properties.get("_is_root") is True

    def test_arcp_root_has_data_false(self):
        g = Crate(str(ARCP_ROOT), include_root=True)
        root = g._entities["arcp://name,test-collection"]
        assert root.has_data is False

    def test_arcp_non_root_dataset_has_data_true(self):
        g = Crate(str(ARCP_ROOT), include_root=True)
        sub = g._entities["arcp://name,test-collection/subcollection/"]
        assert sub.has_data is True

    def test_non_root_entities_not_flagged(self):
        g = Crate(str(ARCP_ROOT), include_root=True)
        alice = g._entities["#alice"]
        assert "_is_root" not in alice.properties

    def test_entity_count_without_root(self):
        g = Crate(str(ARCP_ROOT))
        # alice + bob + acme + report.csv + subcollection + ro-crate-metadata.json = 6
        assert len(g) == 6

    def test_entity_count_with_root(self):
        g = Crate(str(ARCP_ROOT), include_root=True)
        # Same 6 + root = 7
        assert len(g) == 7

    def test_fallback_to_dot_slash_without_descriptor(self, tmp_path: Path):
        """Crate with no ro-crate-metadata.json entity falls back to './'."""
        import json

        metadata = {
            "@context": "https://w3id.org/ro/crate/1.1/context",
            "@graph": [
                {"@id": "./", "@type": "Dataset", "name": "No descriptor"},
                {"@id": "#item", "@type": "Thing", "name": "An item"},
            ],
        }
        (tmp_path / "ro-crate-metadata.json").write_text(json.dumps(metadata))
        reader = ROCrateReader()
        g = reader.read(str(tmp_path))
        assert g.metadata["_root_id"] == "./"
        assert g.metadata["name"] == "No descriptor"


class TestReadIAEACrate:
    """Integration test against the real IAEA crate (if available)."""

    IAEA = Path(__file__).parent.parent.parent / "data" / "IAEA-ro-crate"

    @pytest.fixture()
    def iaea_crate(self) -> Crate:
        if not self.IAEA.exists():
            pytest.skip("IAEA crate not available")
        return Crate(str(self.IAEA))

    def test_loads_many_entities(self, iaea_crate: Crate):
        # The IAEA crate has 455 items, minus ~224 reified relationships.
        assert len(iaea_crate) > 100

    def test_has_relationships(self, iaea_crate: Crate):
        assert len(iaea_crate.relationships) > 100

    def test_has_diverse_types(self, iaea_crate: Crate):
        assert len(iaea_crate.types) > 5

    def test_relationship_types_present(self, iaea_crate: Crate):
        assert len(iaea_crate.relationship_types) > 0
