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
