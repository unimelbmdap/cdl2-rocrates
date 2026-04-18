"""Tests for crategraph.readers.rdf — RdfReader."""

from __future__ import annotations

import warnings
from pathlib import Path

import pytest

pytest.importorskip("rdflib")

from rdflib import XSD, Literal

from crategraph.readers.rdf import RdfReader

FIXTURES = Path(__file__).parent.parent / "fixtures"
RDF_FIXTURE = FIXTURES / "rdf" / "sample.ttl"


class TestToCurie:
    """RdfReader._to_curie — shorten a full URI using a namespace map."""

    def test_known_prefix(self):
        ns = {"crm": "http://www.cidoc-crm.org/cidoc-crm/"}
        result = RdfReader._to_curie("http://www.cidoc-crm.org/cidoc-crm/E21_Person", ns)
        assert result == "crm:E21_Person"

    def test_unknown_prefix_falls_back_to_full_uri(self):
        result = RdfReader._to_curie("http://unknown.org/something", {})
        assert result == "http://unknown.org/something"

    def test_fragment_uri(self):
        ns = {"ex": "http://example.org/ns#"}
        result = RdfReader._to_curie("http://example.org/ns#Foo", ns)
        assert result == "ex:Foo"

    def test_no_match_returns_full_uri(self):
        result = RdfReader._to_curie("urn:uuid:1234", {})
        assert result == "urn:uuid:1234"

    def test_most_specific_prefix_wins(self):
        ns = {
            "ex": "http://example.org/",
            "vocab": "http://example.org/vocab/",
        }
        result = RdfReader._to_curie("http://example.org/vocab/Thing", ns)
        assert result == "vocab:Thing"


class TestConvertLiteral:
    """RdfReader._convert_literal — RDF Literal → Python value."""

    def test_plain_string(self):
        assert RdfReader._convert_literal(Literal("hello")) == "hello"

    def test_xsd_string(self):
        assert RdfReader._convert_literal(Literal("hello", datatype=XSD.string)) == "hello"

    def test_xsd_integer(self):
        assert RdfReader._convert_literal(Literal(42, datatype=XSD.integer)) == 42

    def test_xsd_boolean(self):
        assert RdfReader._convert_literal(Literal(True, datatype=XSD.boolean)) is True

    def test_xsd_float(self):
        result = RdfReader._convert_literal(Literal(3.14, datatype=XSD.float))
        assert isinstance(result, float)
        assert abs(result - 3.14) < 0.001

    def test_xsd_date_preserves_datatype(self):
        lit = Literal("2023-01-15", datatype=XSD.date)
        result = RdfReader._convert_literal(lit)
        assert result == {"value": "2023-01-15", "datatype": "xsd:date"}

    def test_language_tagged(self):
        lit = Literal("hello", lang="en")
        result = RdfReader._convert_literal(lit)
        assert result == {"value": "hello", "lang": "en"}


class TestCanRead:
    def test_turtle_file(self):
        assert RdfReader().can_read(str(RDF_FIXTURE))

    def test_rdf_extension(self, tmp_path: Path):
        (tmp_path / "data.rdf").write_text("<rdf/>")
        assert RdfReader().can_read(str(tmp_path / "data.rdf"))

    def test_jsonld_extension(self, tmp_path: Path):
        (tmp_path / "data.jsonld").write_text("{}")
        assert RdfReader().can_read(str(tmp_path / "data.jsonld"))

    def test_nt_extension(self, tmp_path: Path):
        (tmp_path / "data.nt").write_text("")
        assert RdfReader().can_read(str(tmp_path / "data.nt"))

    def test_non_rdf_extension(self, tmp_path: Path):
        (tmp_path / "data.csv").write_text("a,b")
        assert not RdfReader().can_read(str(tmp_path / "data.csv"))

    def test_nonexistent_path(self):
        assert not RdfReader().can_read("/nonexistent/file.ttl")

    def test_directory_with_ttl(self, tmp_path: Path):
        (tmp_path / "data.ttl").write_text("")
        assert RdfReader().can_read(str(tmp_path))

    def test_directory_without_rdf(self, tmp_path: Path):
        (tmp_path / "data.csv").write_text("")
        assert not RdfReader().can_read(str(tmp_path))


class TestReadEntities:
    """RdfReader.read() — entity construction from the sample fixture."""

    def _load(self):
        return RdfReader().read(str(RDF_FIXTURE))

    def test_loads_defined_subjects_only(self):
        g = self._load()
        # 4 defined subjects; dangling target (external_tool) dropped by default.
        assert len(g.entities) == 4

    def test_entity_id_is_full_uri(self):
        g = self._load()
        ids = {e.id for e in g.entities}
        assert "http://example.org/person1" in ids

    def test_entity_types_are_curies(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person1")
        assert person.types == ["crm:E21_Person"]

    def test_type_uris_preserved_in_properties(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person1")
        assert person.properties["_type_uris"] == ["http://www.cidoc-crm.org/cidoc-crm/E21_Person"]

    def test_plain_literal_stored_as_string(self):
        g = self._load()
        org = next(e for e in g.entities if e.id == "http://example.org/org1")
        assert org.properties["rdfs:label"] == "Research Lab"

    def test_integer_literal(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person1")
        assert person.properties["ex:birthYear"] == 1990

    def test_boolean_literal(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person1")
        assert person.properties["ex:active"] is True

    def test_typed_literal_preserves_datatype(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person2")
        assert person.properties["ex:birthDate"] == {
            "value": "1985-03-15",
            "datatype": "xsd:date",
        }

    def test_language_tagged_literal(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person2")
        assert person.properties["rdfs:label"] == {
            "value": "Bob Jones",
            "lang": "en",
        }

    def test_source_set_on_entities(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person1")
        assert person.source is not None
        assert person.source.endswith("sample.ttl")


class TestReadRelationships:
    """RdfReader.read() — relationship construction."""

    def _load(self):
        return RdfReader().read(str(RDF_FIXTURE))

    def test_relationship_count_excludes_dangling(self):
        g = self._load()
        # memberOf x2, knows x1, P14_carried_out_by x2 = 5
        # usedTool → external_tool is dropped (dangling).
        assert len(g.relationships) == 5

    def test_relationship_type_is_curie(self):
        g = self._load()
        rel = next(r for r in g.relationships if "knows" in r.type)
        assert rel.type == "ex:knows"

    def test_relationship_source_and_target_are_full_uris(self):
        g = self._load()
        rel = next(r for r in g.relationships if "knows" in r.type)
        assert rel.source == "http://example.org/person2"
        assert rel.target == "http://example.org/person1"

    def test_rdf_type_not_a_relationship(self):
        g = self._load()
        types = {r.type for r in g.relationships}
        assert not any("type" in t.lower() and "rdf" in t.lower() for t in types)

    def test_multiple_objects_create_multiple_relationships(self):
        g = self._load()
        carried = [r for r in g.relationships if "P14_carried_out_by" in r.type]
        assert len(carried) == 2
        targets = {r.target for r in carried}
        assert targets == {
            "http://example.org/person1",
            "http://example.org/person2",
        }

    def test_relationship_id_is_none(self):
        g = self._load()
        for r in g.relationships:
            assert r.id is None


class TestDanglingTargets:
    """RdfReader — include_dangling_targets behaviour."""

    def test_default_drops_dangling_with_warning(self):
        with pytest.warns(UserWarning, match=r"Dropped \d+ relationship"):
            g = RdfReader().read(str(RDF_FIXTURE))
        assert not any(e.id == "http://example.org/external_tool" for e in g.entities)
        assert not any("usedTool" in r.type for r in g.relationships)

    def test_default_records_dropped_count_in_metadata(self):
        with pytest.warns(UserWarning):
            g = RdfReader().read(str(RDF_FIXTURE))
        assert g.metadata["dropped_dangling_count"] == 1

    def test_include_creates_stub_with_external_flag(self):
        g = RdfReader(include_dangling_targets=True).read(str(RDF_FIXTURE))
        stub = next(e for e in g.entities if e.id == "http://example.org/external_tool")
        assert stub.types == []
        assert stub.properties["_external"] is True

    def test_include_preserves_relationship(self):
        g = RdfReader(include_dangling_targets=True).read(str(RDF_FIXTURE))
        rel = next(r for r in g.relationships if "usedTool" in r.type)
        assert rel.target == "http://example.org/external_tool"

    def test_include_gives_six_total_relationships(self):
        g = RdfReader(include_dangling_targets=True).read(str(RDF_FIXTURE))
        assert len(g.relationships) == 6


class TestNameResolution:
    """RdfReader.read() — rdfs:label → properties['name']."""

    def _load(self):
        with pytest.warns(UserWarning):
            return RdfReader().read(str(RDF_FIXTURE))

    def test_plain_label_becomes_name(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person1")
        assert person.name == "Alice Smith"
        assert person.properties["name"] == "Alice Smith"

    def test_language_tagged_label_becomes_name(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person2")
        assert person.name == "Bob Jones"

    def test_label_also_kept_under_original_key(self):
        g = self._load()
        person = next(e for e in g.entities if e.id == "http://example.org/person1")
        assert person.properties["rdfs:label"] == "Alice Smith"

    def test_deterministic_tiebreak_plain_over_tagged(self):
        """Plain string wins over language-tagged at the same priority."""
        result = RdfReader._pick_best_label([{"value": "Tagged", "lang": "en"}, "Plain"])
        assert result == "Plain"

    def test_deterministic_tiebreak_en_over_other_lang(self):
        """English wins over other languages."""
        result = RdfReader._pick_best_label(
            [{"value": "French", "lang": "fr"}, {"value": "English", "lang": "en"}]
        )
        assert result == "English"

    def test_deterministic_tiebreak_lexicographic(self):
        """Lexicographic sort breaks ties within the same category."""
        result = RdfReader._pick_best_label(["Zebra", "Apple"])
        assert result == "Apple"

    def test_empty_label_predicates_disables_name_resolution(self):
        """label_predicates=[] should produce no 'name' property."""
        with pytest.warns(UserWarning):
            g = RdfReader(label_predicates=[]).read(str(RDF_FIXTURE))
        person = next(e for e in g.entities if e.id == "http://example.org/person1")
        assert "name" not in person.properties


class TestGraphMetadata:
    """RdfReader.read() — Graph.metadata population."""

    def _load(self):
        with pytest.warns(UserWarning):
            return RdfReader().read(str(RDF_FIXTURE))

    def test_namespaces_populated(self):
        g = self._load()
        ns = g.metadata["namespaces"]
        assert "crm" in ns
        assert ns["crm"] == "http://www.cidoc-crm.org/cidoc-crm/"
        assert "ex" in ns

    def test_format_detected(self):
        g = self._load()
        assert g.metadata["format"] == "turtle"

    def test_source_set(self):
        g = self._load()
        assert g.source is not None
        assert g.source.endswith("sample.ttl")


class TestExcludePredicates:
    def test_excluded_predicate_not_in_relationships(self):
        with pytest.warns(UserWarning):
            reader = RdfReader(exclude_predicates=["http://example.org/memberOf"])
            g = reader.read(str(RDF_FIXTURE))
        member_rels = [r for r in g.relationships if "memberOf" in r.type]
        assert len(member_rels) == 0
        # knows, P14 x2 remain (usedTool dropped as dangling).
        assert len(g.relationships) == 3


CHAD_KG = Path(__file__).parent.parent.parent / "data" / "rdf" / "chad_kg.ttl"


@pytest.mark.skipif(not CHAD_KG.exists(), reason="CHAD-KG fixture not present")
class TestChadKgIntegration:
    """Integration tests against the full CHAD-KG dataset (52K triples)."""

    @pytest.fixture(scope="class")
    def graph(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            return RdfReader().read(str(CHAD_KG))

    def test_loads_many_entities(self, graph):
        assert len(graph.entities) > 1_000

    def test_loads_many_relationships(self, graph):
        assert len(graph.relationships) > 1_000

    def test_has_cidoc_types_as_curies(self, graph):
        all_types = set()
        for e in graph.entities:
            all_types.update(e.types)
        assert any(t.startswith("crm:") or t.startswith("crmdig:") for t in all_types)

    def test_namespaces_include_cidoc(self, graph):
        ns = graph.metadata["namespaces"]
        assert "crm" in ns
        assert "cidoc-crm" in ns.get("crm", "")

    def test_entities_have_data_properties(self, graph):
        with_props = [e for e in graph.entities if len(e.properties) > 1]
        assert len(with_props) > 100

    def test_dropped_dangling_count_recorded(self, graph):
        assert graph.metadata.get("dropped_dangling_count", 0) > 0

    def test_graph_is_queryable(self, graph):
        """The loaded graph works with crategraph's standard select() API."""
        all_types = set()
        for e in graph.entities:
            all_types.update(e.types)
        some_type = next(t for t in all_types if t.startswith("crm:"))
        result = graph.select(entity_types=[some_type])
        assert len(result) >= 1


class TestDirectoryRead:
    """RdfReader.read() — directory with multiple RDF files."""

    def test_merges_files_in_directory(self, tmp_path: Path):
        (tmp_path / "a.ttl").write_text(
            "@prefix ex: <http://example.org/> .\nex:alice a ex:Person ; ex:knows ex:bob .\n"
        )
        (tmp_path / "b.ttl").write_text(
            "@prefix ex: <http://example.org/> .\nex:bob a ex:Person .\n"
        )
        g = RdfReader().read(str(tmp_path))
        ids = {e.id for e in g.entities}
        assert "http://example.org/alice" in ids
        assert "http://example.org/bob" in ids
        assert len(g.relationships) == 1
        assert g.source.endswith(str(tmp_path.name))

    def test_mixed_directory_formats_report_mixed_metadata(self, tmp_path: Path):
        (tmp_path / "a.ttl").write_text(
            "@prefix ex: <http://example.org/> .\nex:alice a ex:Person .\n"
        )
        (tmp_path / "b.nt").write_text(
            "<http://example.org/bob> "
            "<http://www.w3.org/1999/02/22-rdf-syntax-ns#type> "
            "<http://example.org/Person> .\n"
        )
        g = RdfReader().read(str(tmp_path))
        assert g.metadata["format"] == "mixed"
