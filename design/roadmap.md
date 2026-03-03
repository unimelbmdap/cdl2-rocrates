# Roadmap

Planned features and future directions for crategraph. These are deferred until there's a concrete use case driving the design, rather than building speculatively.

## Plugin Implementations

Extension points that exist as ABCs but have no concrete implementations yet:

- **Writers** — serialisation to JSON-LD, GEXF, Gephi-ready formats (with pre-computed layout and styling)
- **Validators** — RDF/schema.org compliance checking, crate structure validation. Should report issues without blocking usage.
- **Additional readers** — GEXF, CSV, NetworkX graph import

## Interoperability

Export methods to bridge crategraph with other tools:

```python
# Drop down to NetworkX for custom analysis
G = result.to_networkx()

# Export to JSON-LD
result.to_jsonld("output.json")

# Export to Gephi with pre-computed layout
result.to_gephi("output.gexf", layout=True, colour_by="type", size_by="degree")
```

## Natural Language Query Interface

LLM-driven graph querying — ask a question in plain language, get back a result:

```python
result = crate.ask("Which organisations in Melbourne had the most members in the 1880s?")
result.visualise()
```

This is likely simpler to implement over a NetworkX backend (LLM generates Python using the existing `select`/`where`/`pattern` API) than over SPARQL or Cypher. The existing chainable API is already close to natural language in structure, which should make prompt engineering more tractable.

## `Entity.has_data` Naming

The `has_data` property name aligns with the RO-Crate spec's "data entity" terminology, but may not be immediately intuitive to users unfamiliar with the spec — they might read it as "has any data/metadata." Alternatives considered: `has_file` (clear but slightly wrong for directories), `has_content` (ambiguous), `is_data_entity` (jargon-heavy). Revisit once there's user feedback on whether the name causes confusion.

## CreativeWork Data Entities

The RO-Crate spec allows data entities of `@type: "CreativeWork"` (e.g. online databases). `Entity.has_data` currently only recognises `File` and `Dataset` types because `CreativeWork` is too ambiguous — contextual entities like publications may also use it. If a concrete use case arises where `CreativeWork` data entities need to be distinguished, the heuristic could be extended (e.g. by also checking for an absolute URI `@id` as the spec suggests).

## Full-Text Search Over File Content

An indexing process that runs inspectors across all data entities and stores extracted markdown in SQLite FTS5 for searchable content discovery. This would complement the existing `search()` (which covers entity metadata) by enabling queries like "find all files mentioning 'colonial architecture'". Design considerations: persistence and cache invalidation, progress feedback for large crates, result ranking and snippet highlighting, incremental re-indexing.

## Bulk Inspect on Subgraphs

Extending `inspect()` to work on filtered subgraphs rather than single entities, returning results in a DataFrame-friendly shape. An `extract_content=False` default would make the cheap case (paths and metadata only) the default, with opt-in to the expensive markitdown step. This would smooth the handoff from crategraph into external analysis tools (NLP pipelines, image processing, etc.).

## Third-Party Plugin Registration

Entry points for installable plugins:

```toml
# In a third-party package's pyproject.toml
[project.entry-points."crategraph.readers"]
my_format = "my_package:MyFormatReader"
```

This would let users `pip install crategraph-myformat` and have it automatically available. Not needed until there are actual third-party plugins.
