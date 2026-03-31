# RDF Reader Design

**Date:** 2026-03-31
**Status:** Approved

## Summary

A general-purpose RDF reader (`RdfReader`) that loads any RDF serialisation
into crategraph's `Graph` model via rdflib. Designed as a "trojan horse" to
bring HASS researchers who already work with linked data into the crategraph
ecosystem, where they discover that RO-Crates are just a JSON-LD profile of
the same RDF foundation they already use.

## Motivation

- Humanities researchers working with linked data (CIDOC-CRM, FOAF, Dublin
  Core, SKOS, etc.) have no easy path into crategraph today.
- RO-Crates are JSON-LD (an RDF serialisation). Showing researchers that
  their RDF data maps to the same entity/relationship model as RO-Crates
  builds conceptual familiarity and lowers the adoption barrier.
- rdflib is already an optional dependency (`rdf` extra).

## Test Dataset

**CHAD-KG** — a cultural heritage knowledge graph describing museum
exhibitions and digitisation processes.

| Property | Value |
|----------|-------|
| Triples | 52,080 |
| Entities | 14,506 |
| Ontologies | CIDOC-CRM 7.1.3, LRMoo 1.0, CRMdig 4.0, Getty AAT |
| Licence | CC0 1.0 |
| Format | Turtle (.ttl) |
| Source | https://doi.org/10.5281/zenodo.15102846 |
| SPARQL | https://w3id.org/dharc/sparql/chad-kg |
| Local path | `data/rdf/chad_kg.ttl` |

## Architecture

### Reader Class

`crategraph/readers/rdf.py` — implements the `Reader` ABC.

```python
class RdfReader(Reader):
    def __init__(
        self,
        format: str | None = None,
        label_predicates: list[str] | None = None,
        exclude_predicates: list[str] | None = None,
    ): ...

    def can_read(self, path: str) -> bool: ...
    def read(self, path: str) -> Graph: ...
```

**Parameters:**

- `format` — RDF serialisation format override. `None` (default) auto-detects
  from file extension via rdflib.
- `label_predicates` — custom ordered list of predicates to resolve
  `Entity.name`. Defaults to the standard resolution order (see below).
- `exclude_predicates` — predicates to skip entirely (not stored as
  properties or relationships).

### Core Flow

1. `rdflib.Graph().parse(path, format=format)` — rdflib auto-detects format.
2. Store the namespace prefix map from the parsed graph in
   `Graph.metadata["namespaces"]`.
3. Walk all distinct subjects:
   a. Collect `rdf:type` triples → `Entity.types` (local name) and
      `Entity.properties["_type_uris"]` (full URIs).
   b. Collect literal-valued predicates → `Entity.properties` (keyed by
      CURIE or local name of the predicate).
   c. Collect URI-valued predicates → `Relationship` edges.
4. Resolve display name from label predicates → `properties["name"]`.
5. Create stub entities for dangling targets (URIs referenced as objects
   but never appearing as subjects).
6. Return the populated crategraph `Graph`.

### File Detection (`can_read`)

Matches file extensions: `.ttl`, `.rdf`, `.owl`, `.xml`, `.nt`, `.nq`,
`.jsonld`, `.trig`.

For directories: scans for any file with a matching extension.

## Entity Construction

### Mapping

Each distinct subject URI becomes one `Entity`:

| RDF | crategraph |
|-----|------------|
| Subject URI | `Entity.id` (full URI string) |
| `rdf:type` objects | `Entity.types` (local names, e.g. `E21_Person`) |
| `rdf:type` objects (full) | `Entity.properties["_type_uris"]` |
| Literal-valued predicates | `Entity.properties` (keyed by predicate CURIE) |
| `rdfs:label` / `skos:prefLabel` / etc. | `Entity.properties["name"]` (also kept under original CURIE key) |
| Source file path | `Entity.source` |

### Name Resolution Priority

First found wins:

1. `rdfs:label`
2. `skos:prefLabel`
3. `foaf:name`
4. `dcterms:title` / `dc:title`
5. Fall back to `Entity.id` (default `Entity.name` behaviour)

### Literal Handling

| RDF Literal | Stored as |
|-------------|-----------|
| Plain string / `xsd:string` | `str` |
| `xsd:integer`, `xsd:int`, `xsd:long` | `int` |
| `xsd:float`, `xsd:double`, `xsd:decimal` | `float` |
| `xsd:boolean` | `bool` |
| Other typed literal (e.g. `xsd:date`) | `{"value": "2023-01-15", "datatype": "xsd:date"}` |
| Language-tagged literal | `{"value": "label", "lang": "en"}` |
| Multiple values for same predicate | `list` |

### Blank Nodes

Included as entities with `id="_:bN"` (rdflib's generated bnode ID).
Allows structural round-tripping, though blank node identity is inherently
unstable across serialisations.

### Property Keys

Predicate URIs are shortened to CURIE form using the namespace map
(e.g. `crm:P14_carried_out_by`). Falls back to the predicate's local name
if no prefix is registered, or the full URI as a last resort.

## Relationship Construction

Each triple where the object is a URI (not a literal) becomes a
`Relationship`, with the following exceptions:

- `rdf:type` triples are excluded (already consumed by `Entity.types`).
- Predicates in `exclude_predicates` are skipped.

### Mapping

| RDF | crategraph |
|-----|------------|
| Subject URI | `Relationship.source` |
| Object URI | `Relationship.target` |
| Predicate URI (CURIE) | `Relationship.type` |
| — | `Relationship.id = None` (RDF triples are not reified) |

### Dangling Targets

If a triple references a URI that never appears as a subject (e.g. external
vocabulary terms like `aat:300266792`), a stub entity is created:

```python
Entity(id=full_uri, types=[], properties={})
```

This ensures the relationship is not dropped by `Graph._add_edge` validation.

## Graph Metadata

```python
graph.metadata = {
    "namespaces": {
        "crm": "http://www.cidoc-crm.org/cidoc-crm/",
        "crmdig": "http://www.ics.forth.gr/isl/CRMdig/",
        # ... all prefixes from the source file
    },
    "format": "turtle",   # detected or specified format
    "base_uri": None,      # if one was declared in the source
}
```

The namespace map is the key to round-trip fidelity — it allows a future
RDF writer to reconstruct full URIs from CURIEs stored in relationship
types and property keys.

## Round-Trip Fidelity

The design preserves all information needed for a future RDF writer to
produce a semantically equivalent (not byte-identical) output:

| RDF concept | Preserved via |
|-------------|---------------|
| Subject URIs | `Entity.id` (full URI) |
| Predicate URIs | CURIE in property keys / relationship types + namespace map |
| Object URIs | `Relationship.target` / `Entity.id` (full URI) |
| `rdf:type` | `Entity.properties["_type_uris"]` (full URIs) |
| Literal datatypes | `{"value": ..., "datatype": ...}` for non-trivial types |
| Language tags | `{"value": ..., "lang": ...}` |
| Namespace prefixes | `Graph.metadata["namespaces"]` |
| Blank node structure | Preserved as entities with `_:bN` IDs |

**Not preserved:** byte-level formatting, triple ordering, comments. These
are not part of the RDF abstract model and are lost in any RDF
parse/serialise cycle.

## File Layout

```
crategraph/
└── readers/
    └── rdf.py              # RdfReader implementation
tests/
└── readers/
    └── test_rdf.py          # Tests using CHAD-KG fixture + synthetic data
data/
└── rdf/
    └── chad_kg.ttl          # CC0 test fixture (already present)
```

## Dependencies

- `rdflib` — already declared as optional under `[project.optional-dependencies] rdf`.
- No new dependencies required.
