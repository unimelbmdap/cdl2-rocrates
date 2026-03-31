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
        include_dangling_targets: bool = False,
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
- `include_dangling_targets` — whether to create stub entities for URIs
  referenced as objects but never defined as subjects (e.g. external
  vocabulary terms like `aat:300266792`). Default `False` — relationships
  to undefined URIs are dropped and a summary warning is emitted (e.g.
  "Dropped 142 relationships to 38 undefined target URIs"); the count is
  also stored in `graph.metadata["dropped_dangling_count"]`. When `True`,
  stubs are created with `properties["_external"] = True` and all
  relationships are preserved.

### Core Flow

1. `rdflib.Graph().parse(path, format=format)` — rdflib auto-detects format.
2. Store the namespace prefix map from the parsed graph in
   `Graph.metadata["namespaces"]`.
3. Walk all distinct subjects:
   a. Collect `rdf:type` triples → `Entity.types` (CURIEs, e.g.
      `crm:E21_Person`) and `Entity.properties["_type_uris"]` (full URIs).
   b. Collect literal-valued predicates → `Entity.properties` (keyed by
      predicate CURIE when a prefix exists, otherwise full URI — never
      bare local names).
   c. Collect URI-valued predicates → `Relationship` edges (type stored
      as CURIE or full URI, same rule as property keys).
4. Resolve display name from label predicates → `properties["name"]`.
   Tie-break: prefer un-tagged → `en` → lexicographic sort of language
   tags → lexicographic sort of values.
5. Handle dangling targets (URIs referenced as objects but never appearing
   as subjects): when `include_dangling_targets=True`, create stub entities
   with `properties["_external"] = True`; when `False` (default), drop the
   relationship and record the count.  Emit a single `warnings.warn()`
   summary and store the count in `graph.metadata["dropped_dangling_count"]`.
6. Return the populated crategraph `Graph`.

**Directory handling:** `read()` parses all RDF files in the directory into
one rdflib graph (rdflib supports multiple `parse()` calls on the same
graph object). Non-recursive — only immediate children. Files are parsed
in sorted-by-name order for deterministic results. All triples share the
same `Graph.source` (the directory path). This is a single merged source,
not multi-crate loading.

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
| `rdf:type` objects | `Entity.types` (CURIEs, e.g. `crm:E21_Person`) |
| `rdf:type` objects (full) | `Entity.properties["_type_uris"]` |
| Literal-valued predicates | `Entity.properties` (keyed by CURIE or full URI) |
| `rdfs:label` / `skos:prefLabel` / etc. | `Entity.properties["name"]` (also kept under original CURIE key) |
| Source file path | `Entity.source` |

### Name Resolution Priority

Predicate priority (first match wins):

1. `rdfs:label`
2. `skos:prefLabel`
3. `foaf:name`
4. `dcterms:title` / `dc:title`
5. Fall back to `Entity.id` (default `Entity.name` behaviour)

**Tie-breaking** (when multiple values exist at the same priority level):
prefer un-tagged literal → `en` language tag → lexicographic sort of
language tags → lexicographic sort of values. This ensures deterministic
output across parses, since RDF triple order is not guaranteed.

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
(e.g. `crm:P14_carried_out_by`). If no prefix is registered for the
predicate's namespace, the **full URI** is used as the key — never a
bare local name. This eliminates collision risk (two predicates from
different namespaces cannot map to the same key) and makes every key
reversible to a full URI via the namespace map alone, without needing a
separate `_predicate_map`.

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
| Predicate URI (CURIE or full URI) | `Relationship.type` |
| — | `Relationship.id = None` (RDF triples are not reified) |

### Dangling Targets

If a triple references a URI that never appears as a subject (e.g. external
vocabulary terms like `aat:300266792`), behaviour depends on
`include_dangling_targets`:

- **`False` (default):** The relationship is dropped. A single
  `warnings.warn()` summary is emitted (e.g. "Dropped 142 relationships
  to 38 undefined target URIs") and the count is stored in
  `graph.metadata["dropped_dangling_count"]`. This keeps the graph clean
  for exploration — external ontology terms and controlled vocabulary
  nodes don't clutter analyses and visualisations.
- **`True`:** A stub entity is created with `properties["_external"] = True`,
  and the relationship is preserved. External stubs can be filtered via
  `where()` (e.g. `graph.where(lambda e: not e.properties.get("_external"))`).
  This supports round-trip fidelity at the cost of a noisier graph.

```python
# Stub entity (when include_dangling_targets=True):
Entity(id=full_uri, types=[], properties={"_external": True})
```

## Graph Metadata

```python
graph.metadata = {
    "namespaces": {
        "crm": "http://www.cidoc-crm.org/cidoc-crm/",
        "crmdig": "http://www.ics.forth.gr/isl/CRMdig/",
        # ... all prefixes from the source file
    },
    "format": "turtle",              # detected or specified format
    "base_uri": None,                 # if one was declared in the source
    "dropped_dangling_count": 142,    # only present when include_dangling_targets=False
}
```

The namespace map is the key to round-trip fidelity — it allows a future
RDF writer to reconstruct full URIs from CURIEs stored in relationship
types and property keys.

## Round-Trip Fidelity

The design preserves all information needed for a future RDF writer to
produce a semantically equivalent (not byte-identical) output, **provided
no triples are dropped by configuration** (`exclude_predicates`,
`include_dangling_targets=False`).

| RDF concept | Preserved via |
|-------------|---------------|
| Subject URIs | `Entity.id` (full URI) |
| Predicate URIs | CURIE or full URI in property keys / relationship types; CURIEs are reversible via namespace map, full URIs are already complete |
| Object URIs | `Relationship.target` / `Entity.id` (full URI) |
| `rdf:type` | `Entity.properties["_type_uris"]` (full URIs) |
| Literal datatypes | `{"value": ..., "datatype": ...}` for non-trivial types |
| Language tags | `{"value": ..., "lang": ...}` |
| Namespace prefixes | `Graph.metadata["namespaces"]` |
| Blank node structure | Preserved as entities with `_:bN` IDs |

**Not preserved:**
- Byte-level formatting, triple ordering, comments — not part of the RDF
  abstract model and lost in any RDF parse/serialise cycle.
- Triples explicitly excluded via `exclude_predicates`.
- Relationships to dangling targets when `include_dangling_targets=False`
  (default) — intentionally dropped for cleaner exploration graphs. The
  count is observable via `graph.metadata["dropped_dangling_count"]` and a
  warning summary.

**Design stance:** The reader optimises for exploration by default. Clean,
navigable graphs take priority over maximal RDF preservation. Round-trip
metadata (`_type_uris`, namespace map) is always stored so that
preservation-focused use cases can reconstruct the original data when
`include_dangling_targets=True` and no `exclude_predicates` are set.

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
