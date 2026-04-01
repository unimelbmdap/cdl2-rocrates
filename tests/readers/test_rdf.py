"""Tests for crategraph.readers.rdf — RdfReader."""

from __future__ import annotations

from pathlib import Path

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
