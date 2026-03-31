# RDF Reader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general-purpose `RdfReader` that loads any RDF serialisation (Turtle, RDF/XML, JSON-LD, N-Triples, etc.) into crategraph's `Graph` model via rdflib, preserving full URIs and namespace maps for round-trip fidelity.

**Architecture:** `RdfReader` implements the `Reader` ABC. It uses `rdflib.Graph.parse()` for format-agnostic loading, then walks all distinct subjects to partition triples into Entity types/properties and Relationship edges. Property keys and Entity.types use CURIEs when a namespace prefix exists, otherwise full URIs — never bare local names. Dangling targets (external vocabulary URIs) are dropped by default with a warning. A small synthetic Turtle fixture drives unit tests; the CC0 CHAD-KG dataset (already at `data/rdf/chad_kg.ttl`) provides integration coverage.

**Tech Stack:** `rdflib>=7.0` (existing optional dep under `[project.optional-dependencies] rdf`). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-03-31-rdf-reader-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `crategraph/readers/rdf.py` | `RdfReader` — parses RDF via rdflib, builds crategraph Graph |
| `tests/readers/test_rdf.py` | Unit + integration tests for RdfReader |
| `tests/fixtures/rdf/sample.ttl` | Small synthetic Turtle fixture (~20 triples) |

### Existing files (no modifications needed)

| File | Note |
|------|------|
| `crategraph/core/interfaces.py` | `Reader` ABC — already defines `can_read()` and `read()` |
| `crategraph/core/models.py` | `Entity`, `Relationship` — used as-is |
| `crategraph/core/graph.py` | `Graph` — used as-is |
| `pyproject.toml` | `rdflib>=7.0` already in `[project.optional-dependencies] rdf` |

---

### Task 1: Create Synthetic Turtle Fixture

**Files:**
- Create: `tests/fixtures/rdf/sample.ttl`

This fixture drives all unit tests. It covers: multiple namespaces, typed entities, `rdfs:label` (plain + language-tagged), typed literals (`xsd:date`, `xsd:integer`, `xsd:boolean`), URI-valued predicates (relationships), multiple objects for one predicate, and a dangling target (referenced but never defined as a subject).

- [ ] **Step 1: Create the fixture file**

```turtle
@prefix ex: <http://example.org/> .
@prefix crm: <http://www.cidoc-crm.org/cidoc-crm/> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

ex:person1 a crm:E21_Person ;
    rdfs:label "Alice Smith" ;
    ex:birthYear 1990 ;
    ex:active true ;
    ex:memberOf ex:org1 .

ex:person2 a crm:E21_Person ;
    rdfs:label "Bob Jones"@en ;
    ex:birthDate "1985-03-15"^^xsd:date ;
    ex:memberOf ex:org1 ;
    ex:knows ex:person1 .

ex:org1 a crm:E74_Group ;
    rdfs:label "Research Lab" ;
    ex:founded 2010 .

ex:event1 a crm:E5_Event ;
    rdfs:label "Conference 2023" ;
    crm:P14_carried_out_by ex:person1, ex:person2 ;
    ex:usedTool ex:external_tool .
```

Entities: `person1`, `person2`, `org1`, `event1` (4 defined subjects).
Dangling target: `ex:external_tool` (referenced but never defined).
Relationships: `memberOf` (×2), `knows`, `P14_carried_out_by` (×2), `usedTool` — 6 total.

- [ ] **Step 2: Commit**

```bash
git add tests/fixtures/rdf/sample.ttl
git commit -m "test: add synthetic Turtle fixture for RDF reader tests"
```

---

### Task 2: URI Shortening and Literal Conversion Helpers

**Files:**
- Create: `crategraph/readers/rdf.py` (initial skeleton with helpers only)
- Create: `tests/readers/test_rdf.py` (helper tests)

These are pure functions tested in isolation before building the reader itself.

- [ ] **Step 1: Write failing tests for `_to_curie`**

```python
"""Tests for crategraph.readers.rdf — RdfReader."""

from __future__ import annotations

import pytest

from crategraph.readers.rdf import RdfReader


class TestToCurie:
    """RdfReader._to_curie — shorten a full URI using a namespace map."""

    def test_known_prefix(self):
        ns = {"crm": "http://www.cidoc-crm.org/cidoc-crm/"}
        result = RdfReader._to_curie(
            "http://www.cidoc-crm.org/cidoc-crm/E21_Person", ns
        )
        assert result == "crm:E21_Person"

    def test_unknown_prefix_falls_back_to_full_uri(self):
        result = RdfReader._to_curie(
            "http://unknown.org/something", {}
        )
        assert result == "http://unknown.org/something"

    def test_fragment_uri(self):
        ns = {"ex": "http://example.org/ns#"}
        result = RdfReader._to_curie("http://example.org/ns#Foo", ns)
        assert result == "ex:Foo"

    def test_no_match_returns_full_uri(self):
        result = RdfReader._to_curie("urn:uuid:1234", {})
        assert result == "urn:uuid:1234"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/readers/test_rdf.py::TestToCurie -v`
Expected: FAIL — `crategraph.readers.rdf` does not exist yet.

- [ ] **Step 3: Write failing tests for `_convert_literal`**

Append to `tests/readers/test_rdf.py`:

```python
from rdflib import Literal, XSD


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
```

- [ ] **Step 4: Implement helpers in `crategraph/readers/rdf.py`**

```python
"""RDF reader — loads any RDF serialisation via rdflib.

Supports Turtle, RDF/XML, JSON-LD, N-Triples, and other formats
recognised by rdflib. Preserves full URIs, namespace maps, and
literal metadata for round-trip fidelity.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

from rdflib import RDF, RDFS, DCTERMS, FOAF, XSD, BNode, Literal, Namespace, URIRef
from rdflib import Graph as RdfGraph
from rdflib.term import Node

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader
from crategraph.core.models import Entity, Relationship

# XSD types that map directly to Python primitives.
_XSD_INT_TYPES = {
    XSD.integer, XSD.int, XSD.long, XSD.short, XSD.byte,
    XSD.nonNegativeInteger, XSD.positiveInteger,
    XSD.nonPositiveInteger, XSD.negativeInteger,
    XSD.unsignedInt, XSD.unsignedLong, XSD.unsignedShort, XSD.unsignedByte,
}
_XSD_FLOAT_TYPES = {XSD.float, XSD.double, XSD.decimal}
_XSD_BOOL_TYPES = {XSD.boolean}
_XSD_STRING_TYPES = {XSD.string, XSD.normalizedString, XSD.token}

# Well-known namespace for xsd: CURIE prefix in datatype values.
_XSD_NS = str(XSD)

_RDF_EXTENSIONS = {".ttl", ".rdf", ".owl", ".xml", ".nt", ".nq", ".jsonld", ".trig"}

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
DC = Namespace("http://purl.org/dc/elements/1.1/")

_DEFAULT_LABEL_PREDICATES: list[URIRef] = [
    RDFS.label,
    SKOS.prefLabel,
    FOAF.name,
    DCTERMS.title,
    DC.title,
]


class RdfReader(Reader):
    """Read any RDF file into a crategraph Graph."""

    def __init__(
        self,
        *,
        format: str | None = None,
        label_predicates: list[URIRef] | None = None,
        exclude_predicates: list[str] | None = None,
        include_dangling_targets: bool = False,
    ) -> None:
        self._format = format
        self._label_predicates = label_predicates
        self._exclude_predicates = set(exclude_predicates or [])
        self._include_dangling_targets = include_dangling_targets

    # --- Public API (Reader ABC) ---

    def can_read(self, path: str) -> bool:
        raise NotImplementedError

    def read(self, path: str) -> Graph:
        raise NotImplementedError

    # --- URI helpers (static, tested directly) ---

    @staticmethod
    def _to_curie(uri: str, namespaces: dict[str, str]) -> str:
        """Shorten a full URI to CURIE form using a namespace map.

        Returns the CURIE if a prefix matches, otherwise the full URI.
        Never returns a bare local name — this ensures every key is
        reversible to a full URI.
        """
        for prefix, ns_uri in namespaces.items():
            if uri.startswith(ns_uri):
                local = uri[len(ns_uri):]
                if local:
                    return f"{prefix}:{local}"
        return uri

    # --- Literal conversion ---

    @staticmethod
    def _convert_literal(literal: Literal) -> Any:
        """Convert an rdflib Literal to a Python value.

        Plain strings and common XSD types (integer, float, boolean) are
        returned as native Python types.  Language-tagged literals return
        ``{"value": ..., "lang": ...}``.  Other typed literals return
        ``{"value": ..., "datatype": ...}`` with the datatype as a CURIE.
        """
        # Language-tagged literal.
        if literal.language:
            return {"value": str(literal), "lang": literal.language}

        dt = literal.datatype

        # No datatype or xsd:string — return plain string.
        if dt is None or dt in _XSD_STRING_TYPES:
            return str(literal)

        # Integer types.
        if dt in _XSD_INT_TYPES:
            return int(literal)

        # Float types.
        if dt in _XSD_FLOAT_TYPES:
            return float(literal)

        # Boolean.
        if dt in _XSD_BOOL_TYPES:
            return literal.toPython()

        # Everything else — preserve datatype as CURIE.
        dt_str = str(dt)
        if dt_str.startswith(_XSD_NS):
            dt_curie = "xsd:" + dt_str[len(_XSD_NS):]
        else:
            dt_curie = dt_str
        return {"value": str(literal), "datatype": dt_curie}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/readers/test_rdf.py -v`
Expected: All 11 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add crategraph/readers/rdf.py tests/readers/test_rdf.py
git commit -m "feat(rdf): add URI shortening and literal conversion helpers"
```

---

### Task 3: `can_read` File Detection

**Files:**
- Modify: `crategraph/readers/rdf.py`
- Modify: `tests/readers/test_rdf.py`

- [ ] **Step 1: Write failing tests for `can_read`**

Append to `tests/readers/test_rdf.py`:

```python
from pathlib import Path

FIXTURES = Path(__file__).parent.parent / "fixtures"
RDF_FIXTURE = FIXTURES / "rdf" / "sample.ttl"


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/readers/test_rdf.py::TestCanRead -v`
Expected: FAIL — `can_read` raises `NotImplementedError`.

- [ ] **Step 3: Implement `can_read`**

Replace the `can_read` stub in `crategraph/readers/rdf.py`:

```python
    def can_read(self, path: str) -> bool:
        """Return True if *path* is an RDF file or directory containing one."""
        p = Path(path)
        if p.is_file():
            return p.suffix.lower() in _RDF_EXTENSIONS
        if p.is_dir():
            return any(
                f.suffix.lower() in _RDF_EXTENSIONS
                for f in p.iterdir()
                if f.is_file()
            )
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/readers/test_rdf.py::TestCanRead -v`
Expected: All 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add crategraph/readers/rdf.py tests/readers/test_rdf.py
git commit -m "feat(rdf): implement can_read file/directory detection"
```

---

### Task 4: Core `read()` — Entity and Relationship Construction

**Files:**
- Modify: `crategraph/readers/rdf.py`
- Modify: `tests/readers/test_rdf.py`

This is the main task. It implements `read()` including entity construction, relationship construction, dangling target handling, name resolution with deterministic tie-breaking, and graph metadata.

- [ ] **Step 1: Write failing tests for entity construction**

Append to `tests/readers/test_rdf.py`:

```python
class TestReadEntities:
    """RdfReader.read() — entity construction from the sample fixture."""

    def _load(self) -> Graph:
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
        assert person.properties["_type_uris"] == [
            "http://www.cidoc-crm.org/cidoc-crm/E21_Person"
        ]

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/readers/test_rdf.py::TestReadEntities -v`
Expected: FAIL — `read` raises `NotImplementedError`.

- [ ] **Step 3: Implement `read()` with entity construction, relationships, dangling targets, and name resolution**

Replace the `read` stub and add supporting methods in `crategraph/readers/rdf.py`:

```python
    def read(self, path: str) -> Graph:
        """Read the RDF file or directory at *path* and return a populated Graph."""
        p = Path(path)
        rdf = RdfGraph()

        if p.is_dir():
            rdf_files = sorted(
                f for f in p.iterdir()
                if f.is_file() and f.suffix.lower() in _RDF_EXTENSIONS
            )
            for f in rdf_files:
                rdf.parse(str(f), format=self._format)
            source = str(p.resolve())
            detected_format = self._detect_format(str(rdf_files[0])) if rdf_files else None
        else:
            rdf.parse(str(p), format=self._format)
            source = str(p.resolve())
            detected_format = self._detect_format(str(p))

        namespaces = {
            prefix: str(uri)
            for prefix, uri in rdf.namespaces()
            if prefix  # skip the default empty prefix
        }

        graph = Graph(
            source=source,
            metadata={
                "namespaces": namespaces,
                "format": self._format or detected_format,
                "base_uri": None,
            },
        )

        # Collect all subjects that appear in the data.
        subjects = set(rdf.subjects())

        # First pass: build entities from subjects.
        for subject in subjects:
            entity = self._build_entity(subject, rdf, namespaces, source)
            graph._add_node(entity)

        # Second pass: build relationships and track dangling targets.
        existing_ids = {e.id for e in graph.entities}
        relationships: list[Relationship] = []
        dangling_uris: set[str] = set()
        dangling_rel_count = 0

        for subject in subjects:
            for pred, obj in rdf.predicate_objects(subject):
                if pred == RDF.type:
                    continue
                pred_str = str(pred)
                if pred_str in self._exclude_predicates:
                    continue
                if isinstance(obj, URIRef):
                    obj_str = str(obj)
                    rel = Relationship(
                        source=str(subject),
                        target=obj_str,
                        type=self._to_curie(pred_str, namespaces),
                    )
                    if obj_str in existing_ids:
                        relationships.append(rel)
                    elif self._include_dangling_targets:
                        dangling_uris.add(obj_str)
                        relationships.append(rel)
                    else:
                        dangling_uris.add(obj_str)
                        dangling_rel_count += 1

        # Create stub entities for dangling targets when requested.
        if self._include_dangling_targets:
            for uri in dangling_uris:
                graph._add_node(
                    Entity(id=uri, types=[], properties={"_external": True}, source=source)
                )

        # Emit warning about dropped dangling relationships.
        if not self._include_dangling_targets and dangling_rel_count > 0:
            graph.metadata["dropped_dangling_count"] = dangling_rel_count
            warnings.warn(
                f"Dropped {dangling_rel_count} relationship(s) to "
                f"{len(dangling_uris)} undefined target URI(s).",
                stacklevel=2,
            )

        # Add relationships (after stubs exist).
        for rel in relationships:
            graph._add_edge(rel)

        return graph

    def _build_entity(
        self,
        subject: Node,
        rdf: RdfGraph,
        namespaces: dict[str, str],
        source: str,
    ) -> Entity:
        """Build an Entity from all triples about *subject*."""
        subject_str = str(subject)
        if isinstance(subject, BNode):
            subject_str = f"_:{subject}"

        types: list[str] = []
        type_uris: list[str] = []
        properties: dict[str, Any] = {}

        for pred, obj in rdf.predicate_objects(subject):
            pred_str = str(pred)

            if pred_str in self._exclude_predicates:
                continue

            # rdf:type → types list (as CURIEs).
            if pred == RDF.type:
                type_uri = str(obj)
                type_uris.append(type_uri)
                types.append(self._to_curie(type_uri, namespaces))
                continue

            # Skip URI-valued predicates — handled as relationships.
            if isinstance(obj, URIRef):
                continue

            # Literal-valued predicate → property.
            if isinstance(obj, Literal):
                key = self._to_curie(pred_str, namespaces)
                value = self._convert_literal(obj)
                # Accumulate multiple values as a list.
                if key in properties:
                    existing = properties[key]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        properties[key] = [existing, value]
                else:
                    properties[key] = value

        # Store full type URIs for round-trip fidelity.
        if type_uris:
            properties["_type_uris"] = type_uris

        # Resolve display name.
        name = self._resolve_name(properties, namespaces)
        if name is not None:
            properties["name"] = name

        return Entity(id=subject_str, types=types, properties=properties, source=source)

    def _resolve_name(
        self, properties: dict[str, Any], namespaces: dict[str, str]
    ) -> str | None:
        """Pick the best display name from label-like properties.

        Tie-break: un-tagged → 'en' → lexicographic lang → lexicographic value.
        """
        label_preds = self._label_predicates or _DEFAULT_LABEL_PREDICATES
        for label_pred in label_preds:
            label_key = self._to_curie(str(label_pred), namespaces)
            if label_key not in properties:
                continue
            raw = properties[label_key]
            candidates = raw if isinstance(raw, list) else [raw]
            return self._pick_best_label(candidates)
        return None

    @staticmethod
    def _pick_best_label(candidates: list[Any]) -> str | None:
        """Select the best label from a list of literal values.

        Priority: plain string → lang 'en' → lowest lang tag → lowest value.
        """
        plain: list[str] = []
        en: list[str] = []
        tagged: list[tuple[str, str]] = []  # (lang, value)

        for c in candidates:
            if isinstance(c, str):
                plain.append(c)
            elif isinstance(c, dict) and "value" in c:
                if "lang" in c:
                    if c["lang"] == "en":
                        en.append(c["value"])
                    else:
                        tagged.append((c["lang"], c["value"]))
                else:
                    # Typed literal without lang — treat as plain.
                    plain.append(str(c["value"]))
            elif isinstance(c, (int, float, bool)):
                plain.append(str(c))

        if plain:
            return sorted(plain)[0]
        if en:
            return sorted(en)[0]
        if tagged:
            tagged.sort()
            return tagged[0][1]
        return None

    @staticmethod
    def _detect_format(path: str) -> str | None:
        """Guess RDF format from file extension."""
        suffix = Path(path).suffix.lower()
        return {
            ".ttl": "turtle",
            ".rdf": "xml",
            ".owl": "xml",
            ".xml": "xml",
            ".nt": "nt",
            ".nq": "nquads",
            ".jsonld": "json-ld",
            ".trig": "trig",
        }.get(suffix)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/readers/test_rdf.py::TestReadEntities -v`
Expected: All 10 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add crategraph/readers/rdf.py tests/readers/test_rdf.py
git commit -m "feat(rdf): implement read() with entity/relationship construction"
```

---

### Task 5: Relationship Tests

**Files:**
- Modify: `tests/readers/test_rdf.py`

The relationship logic is implemented in Task 4. This task adds focused tests.

- [ ] **Step 1: Write relationship tests**

Append to `tests/readers/test_rdf.py`:

```python
class TestReadRelationships:
    """RdfReader.read() — relationship construction."""

    def _load(self) -> Graph:
        return RdfReader().read(str(RDF_FIXTURE))

    def test_relationship_count_excludes_dangling(self):
        g = self._load()
        # memberOf ×2, knows ×1, P14_carried_out_by ×2 = 5
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/readers/test_rdf.py::TestReadRelationships -v`
Expected: All 6 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/readers/test_rdf.py
git commit -m "test(rdf): add relationship construction tests"
```

---

### Task 6: Dangling Target Handling Tests

**Files:**
- Modify: `tests/readers/test_rdf.py`

- [ ] **Step 1: Write dangling target tests**

Append to `tests/readers/test_rdf.py`:

```python
class TestDanglingTargets:
    """RdfReader — include_dangling_targets behaviour."""

    def test_default_drops_dangling_with_warning(self):
        with pytest.warns(UserWarning, match=r"Dropped \d+ relationship"):
            g = RdfReader().read(str(RDF_FIXTURE))
        # usedTool → external_tool is dropped.
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/readers/test_rdf.py::TestDanglingTargets -v`
Expected: All 5 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/readers/test_rdf.py
git commit -m "test(rdf): add dangling target handling tests"
```

---

### Task 7: Name Resolution and Graph Metadata Tests

**Files:**
- Modify: `tests/readers/test_rdf.py`

- [ ] **Step 1: Write name resolution and metadata tests**

Append to `tests/readers/test_rdf.py`:

```python
class TestNameResolution:
    """RdfReader.read() — rdfs:label → properties['name']."""

    def _load(self) -> Graph:
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
        result = RdfReader._pick_best_label(
            [{"value": "Tagged", "lang": "en"}, "Plain"]
        )
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


class TestGraphMetadata:
    """RdfReader.read() — Graph.metadata population."""

    def _load(self) -> Graph:
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `uv run pytest tests/readers/test_rdf.py::TestNameResolution -v && uv run pytest tests/readers/test_rdf.py::TestGraphMetadata -v`
Expected: All 9 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/readers/test_rdf.py
git commit -m "test(rdf): add name resolution and graph metadata tests"
```

---

### Task 8: `exclude_predicates` Configuration Test

**Files:**
- Modify: `tests/readers/test_rdf.py`

- [ ] **Step 1: Write test for exclude_predicates**

Append to `tests/readers/test_rdf.py`:

```python
class TestExcludePredicates:
    def test_excluded_predicate_not_in_relationships(self):
        with pytest.warns(UserWarning):
            reader = RdfReader(exclude_predicates=["http://example.org/memberOf"])
            g = reader.read(str(RDF_FIXTURE))
        member_rels = [r for r in g.relationships if "memberOf" in r.type]
        assert len(member_rels) == 0
        # knows, P14 ×2 remain (usedTool dropped as dangling).
        assert len(g.relationships) == 3
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/readers/test_rdf.py::TestExcludePredicates -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/readers/test_rdf.py
git commit -m "test(rdf): add exclude_predicates configuration test"
```

---

### Task 9: Integration Test with CHAD-KG

**Files:**
- Modify: `tests/readers/test_rdf.py`

- [ ] **Step 1: Write integration test**

Append to `tests/readers/test_rdf.py`:

```python
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
        # CIDOC-CRM types should use CURIE form.
        assert any(t.startswith("crm:") or t.startswith("crmdig:") for t in all_types)

    def test_namespaces_include_cidoc(self, graph):
        ns = graph.metadata["namespaces"]
        assert "crm" in ns
        assert "cidoc-crm" in ns.get("crm", "")

    def test_entities_have_labels(self, graph):
        named = [e for e in graph.entities if "name" in e.properties]
        assert len(named) > 100

    def test_dropped_dangling_count_recorded(self, graph):
        # CHAD-KG references external AAT terms — should have dropped some.
        assert graph.metadata.get("dropped_dangling_count", 0) > 0

    def test_graph_is_queryable(self, graph):
        """The loaded graph works with crategraph's standard select() API."""
        # Use a CURIE type that should exist in CHAD-KG.
        all_types = set()
        for e in graph.entities:
            all_types.update(e.types)
        some_type = next(t for t in all_types if t.startswith("crm:"))
        result = graph.select(entity_types=[some_type])
        assert len(result) >= 1
```

Add `import warnings` to the top of the test file if not already imported.

- [ ] **Step 2: Run integration tests**

Run: `uv run pytest tests/readers/test_rdf.py::TestChadKgIntegration -v`
Expected: All 7 tests PASS (or SKIP if `chad_kg.ttl` is not present).

- [ ] **Step 3: Commit**

```bash
git add tests/readers/test_rdf.py
git commit -m "test(rdf): add CHAD-KG integration tests"
```

---

### Task 10: Final Lint and Full Test Suite

**Files:**
- Possibly modify: `crategraph/readers/rdf.py` (lint fixes)

- [ ] **Step 1: Run ruff lint**

Run: `uv run ruff check crategraph/readers/rdf.py tests/readers/test_rdf.py`
Expected: No errors. If any, fix them.

- [ ] **Step 2: Run ruff format**

Run: `uv run ruff format crategraph/readers/rdf.py tests/readers/test_rdf.py`

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -x`
Expected: All tests pass, including existing tests (no regressions).

- [ ] **Step 4: Commit any lint fixes**

```bash
git add -u
git commit -m "style(rdf): apply ruff formatting"
```
