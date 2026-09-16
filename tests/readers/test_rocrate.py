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
LIST_WRAPPED = FIXTURES / "list-wrapped-crate"


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


class TestUnwrapLiteralSingleton:
    """Covers every row of the rule table in the 2026-09-16 spec."""

    def test_string_singleton_unwrapped(self):
        from crategraph.readers.rocrate import _unwrap_literal_singleton

        assert _unwrap_literal_singleton(["Foo"]) == "Foo"

    def test_numeric_and_bool_singletons_unwrapped(self):
        from crategraph.readers.rocrate import _unwrap_literal_singleton

        assert _unwrap_literal_singleton([42]) == 42
        assert _unwrap_literal_singleton([1.5]) == 1.5
        assert _unwrap_literal_singleton([True]) is True

    def test_falsy_literals_preserved_not_dropped(self):
        from crategraph.readers.rocrate import _unwrap_literal_singleton

        assert _unwrap_literal_singleton([""]) == ""
        assert _unwrap_literal_singleton([0]) == 0
        assert _unwrap_literal_singleton([False]) is False

    def test_multi_item_list_untouched(self):
        from crategraph.readers.rocrate import _unwrap_literal_singleton

        assert _unwrap_literal_singleton(["A", "B"]) == ["A", "B"]

    def test_reference_singleton_untouched(self):
        from crategraph.readers.rocrate import _unwrap_literal_singleton

        ref = [{"@id": "#x"}]
        assert _unwrap_literal_singleton(ref) is ref

    def test_nested_object_singleton_untouched(self):
        from crategraph.readers.rocrate import _unwrap_literal_singleton

        obj = [{"@type": "GeoCoordinates", "latitude": -37.8}]
        assert _unwrap_literal_singleton(obj) is obj

    def test_null_empty_and_nested_lists_untouched(self):
        from crategraph.readers.rocrate import _unwrap_literal_singleton

        assert _unwrap_literal_singleton([None]) == [None]
        assert _unwrap_literal_singleton([]) == []
        assert _unwrap_literal_singleton([["a"]]) == [["a"]]

    def test_scalars_and_dicts_pass_through(self):
        from crategraph.readers.rocrate import _unwrap_literal_singleton

        assert _unwrap_literal_singleton("Foo") == "Foo"
        assert _unwrap_literal_singleton(7) == 7
        assert _unwrap_literal_singleton(None) is None
        d = {"@id": "#x"}
        assert _unwrap_literal_singleton(d) is d


class TestListWrappedCrate:
    """Singleton literal arrays are unwrapped at the reader boundary."""

    def _load(self, **kwargs) -> Crate:
        return Crate(str(LIST_WRAPPED), **kwargs)

    def test_entity_literal_singletons_become_scalars(self):
        g = self._load()
        f = g._entities["data/file.txt"]
        assert f.properties["name"] == "A file"
        assert f.properties["encodingFormat"] == "text/plain"
        assert f.properties["contentSize"] == 42
        assert f.properties["isPublic"] is True

    def test_falsy_literal_singletons_preserved(self):
        f = self._load()._entities["data/file.txt"]
        assert f.properties["emptyName"] == ""
        assert f.properties["zero"] == 0
        assert f.properties["flag"] is False

    def test_non_literal_lists_keep_shape(self):
        f = self._load()._entities["data/file.txt"]
        assert f.properties["tags"] == ["a", "b"]
        assert f.properties["nested"] == [["a"]]
        assert f.properties["nothing"] == []
        assert f.properties["nulls"] == [None]
        assert f.properties["mixed"] == ["a", "#alice"]
        assert f.properties["geo"] == [{"@type": "GeoCoordinates", "latitude": -37.8}]
        assert f.properties["structured"] == [{"@value": "A", "@language": "en"}]

    def test_reference_singletons_stay_lists_of_ids(self):
        f = self._load()._entities["data/file.txt"]
        assert f.properties["author"] == ["#alice"]
        assert f.properties["contributor"] == ["#Bob Smith"]

    def test_bare_reference_still_collapses_to_id(self):
        alice = self._load()._entities["#alice"]
        assert alice.properties["affiliation"] == "#acme"

    def test_root_metadata_literal_singletons_become_scalars(self):
        g = self._load()
        assert g.metadata["name"] == "Wrapped Crate"
        assert g.metadata["description"] == "A producer that kept singleton arrays"
        assert g.metadata["datePublished"] == "2024-01-01"

    def test_root_metadata_reference_lists_stay_lists(self):
        g = self._load()
        assert g.metadata["license"] == ["https://creativecommons.org/licenses/by/4.0/"]
        assert g.metadata["hasPart"] == ["data/file.txt"]

    def test_root_excluded_by_default(self):
        assert "./" not in self._load()._entities

    def test_include_root_true_gives_root_entity_scalar_name(self):
        g = self._load(include_root=True)
        root = g._entities["./"]
        assert root.properties["name"] == "Wrapped Crate"
        assert root.properties["license"] == ["https://creativecommons.org/licenses/by/4.0/"]
        assert g.metadata["name"] == "Wrapped Crate"

    def test_reified_relationship_properties_unwrapped(self):
        g = self._load()
        rel = next(r for r in g.relationships if r.id == "#rel1")
        assert rel.properties["role"] == "Director"


class TestListWrappedCrateEdges:
    """Relationship extraction reads raw items; the unwrap must not change edges."""

    def _edges(self, **kwargs) -> set[tuple[str, str, str]]:
        g = Crate(str(LIST_WRAPPED), **kwargs)
        return {(r.source, r.target, r.type) for r in g.relationships}

    def test_default_inline_relations(self):
        assert self._edges() == {
            ("data/file.txt", "#alice", "author"),
            ("data/file.txt", "#alice", "mixed"),
            ("data/file.txt", "#Bob Smith", "contributor"),
            ("#alice", "#acme", "affiliation"),
            ("#alice", "#acme", "Relationship"),
        }

    def test_inline_relations_false_keeps_only_reified(self):
        assert self._edges(inline_relations=False) == {("#alice", "#acme", "Relationship")}

    def test_inline_relations_allowlist(self):
        assert self._edges(inline_relations=["author"]) == {
            ("data/file.txt", "#alice", "author"),
            ("#alice", "#acme", "Relationship"),
        }

    def test_include_root_adds_root_and_descriptor_edges(self):
        # Singleton ``hasPart`` and ``license`` reference lists on the root
        # still produce edges once the root is kept.
        assert self._edges(include_root=True) == {
            ("data/file.txt", "#alice", "author"),
            ("data/file.txt", "#alice", "mixed"),
            ("data/file.txt", "#Bob Smith", "contributor"),
            ("#alice", "#acme", "affiliation"),
            ("#alice", "#acme", "Relationship"),
            ("./", "data/file.txt", "hasPart"),
            ("./", "https://creativecommons.org/licenses/by/4.0/", "license"),
            ("ro-crate-metadata.json", "./", "about"),
        }


class TestListWrappedCrateConsumers:
    """The unwrap must be visible through every public surface, not just .properties."""

    def _load(self) -> Crate:
        return Crate(str(LIST_WRAPPED))

    def test_entity_name_and_label_are_plain_strings(self):
        alice = self._load()._entities["#alice"]
        assert alice.name == "Alice"
        assert alice.label == "Alice"

    def test_graph_title_and_metadata_are_scalar(self):
        g = self._load()
        assert g.title == "Wrapped Crate"
        # ``Graph.title`` already tolerates a singleton list via ``_first``;
        # the stored metadata value itself must be a str.
        assert isinstance(g.metadata["name"], str)

    def test_entity_records_carry_scalar_name_and_label(self):
        g = self._load()
        row = next(r for r in g.entity_records() if r["id"] == "#alice")
        assert row["name"] == "Alice"
        assert row["label"] == "Alice"

    def test_where_on_name_matches(self):
        g = self._load()
        assert {e.id for e in g.where(name="Alice").entities} == {"#alice"}

    def test_entity_counts_and_where_agree(self):
        g = self._load()
        counted = {row["name"] for row in g.entity_counts("name")}
        for value in counted:
            assert len(g.where(name=value)) >= 1, value

    def test_csv_writer_label_and_name_columns(self, tmp_path: Path):
        import csv

        g = self._load()
        out = tmp_path / "csv"
        g.write(str(out), format="csv")
        with (out / "nodes.csv").open(newline="", encoding="utf-8") as fh:
            rows = {row["id"]: row for row in csv.DictReader(fh)}
        assert rows["#alice"]["label"] == "Alice"
        assert rows["#alice"]["name"] == "Alice"
        assert rows["data/file.txt"]["label"] == "A file"

    def test_svg_renders_plain_labels(self):
        from crategraph.renderers.svg import SvgRenderer

        svg = SvgRenderer().render(self._load())
        text = svg.data if hasattr(svg, "data") else str(svg)
        assert "Alice" in text
        assert "[&#x27;" not in text

    def test_sigma_renders_to_file(self, tmp_path: Path):
        from crategraph.renderers.sigma import SigmaRenderer

        target = tmp_path / "sigma.html"
        SigmaRenderer().render(self._load(), filepath=str(target))
        assert target.exists()

    def test_gallery_caption_is_plain_label(self):
        from crategraph.renderers.gallery import GalleryRenderer

        html = GalleryRenderer().render(self._load()).data
        assert html.count("<img") == 1
        assert '<figcaption class="cg-caption">A picture</figcaption>' in html
        assert "[&#x27;" not in html
