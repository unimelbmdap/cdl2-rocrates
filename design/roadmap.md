# Roadmap

Planned features and future directions for crategraph. These are deferred until there's a concrete use case driving the design, rather than building speculatively.

## Archetype-related API Challenges

Profiling 47 crates across two collections identified four structural archetypes (Star, Hairball, Archipelago, Compact — see [crate-archetypes](../docs/crate-archetypes.md)). These findings expose gaps between the current API surface and the workflows users actually need. The challenges below are listed in priority order.

### Root Dataset handling — implemented

The root Dataset entity is excluded at load time by default. `Crate` defaults to `include_root=False`, and `ROCrateReader` accepts the same parameter (defaulting to `True` for backward compatibility when used directly).

**What was implemented (Option A from the original analysis):**

- `ROCrateReader` detects the root entity via the metadata descriptor's `about` property per the RO-Crate spec, falling back to `"./"` if no descriptor is present. This handles both OHRM crates (which use `@id: "./"`) and LDaCA crates (which use `arcp://` URIs).
- Root entity properties (name, description, licence, etc.) are always promoted to `Graph.metadata`, regardless of `include_root`. For single crates, these are accessible as `crate.metadata["name"]`. For multi-crate graphs, they're nested under per-crate prefixes: `crate.metadata["prefix"]["name"]`.
- All edges to/from the root are silently dropped when `include_root=False`. `isPartOf: ./` edges are tautological and carry no structural information.
- The root entity is marked with an `_is_root` property flag, used by `Entity.has_data`, `inspect()`, and `view()` to identify the root regardless of its `@id` format.
- `Crate._restore_root()` reconstructs the root entity from stored metadata when needed (e.g. for writers that need a complete RO-Crate representation).

**Impact on profiling data** (see [crate-archetypes](../docs/crate-archetypes.md)):

- OHRM crates: 24 of 27 stars eliminated. Hub ratios drop from ~1.0 to 0.01–0.56. Graphs fragment from 1 component into dozens or hundreds — the root was the sole structural glue.
- LDaCA crates: modest changes for most. A few small crates (Holmer Fieldnotes, Expanded Auslan) see dramatic hub ratio drops where the root was the dominant hub.

### Archetype detection

`profile()` produces the raw metrics (hub ratio, density, component count, skewness) and the archetypes doc defines classification thresholds, but there's no method bridging the two. An `archetype()` or `classify()` method returning `"star"` / `"hairball"` / `"archipelago"` / `"compact"` would enable downstream logic — adaptive rendering defaults, suggested workflows, automated simplification strategies — to key off structure rather than requiring users to interpret profile output manually.

The feature matrix in the archetypes doc (`crate-archetypes.md:188-196`) maps methods to archetypes with Essential/Important/Useful/Optional ratings. This is an implicit API contract that archetype detection would make executable.

### Goal-oriented simplification

The Hairball mitigation recommends `simplify().simplify()` chains, which works but is trial-and-error. Users don't want "remove nodes with fewer than N connections" — they want "get me to a renderable size." A `target_size` parameter or predicate-based `until` would save significant iteration on the 37,000-entity crates:

```python
# Peel until under 200 nodes
crate.simplify(target_size=200)

# Or peel until hub ratio drops below a threshold
crate.simplify(until=lambda g: g.profile().hub_ratio < 0.5)
```

The `until` callback approach is more flexible but harder to document. A `target_size` parameter covers the most common case.

### Adaptive rendering defaults

Entity counts range from 2 to 82,715 across the corpus — no single renderer configuration works across this range. `visualise()` should pick sensible defaults based on `len(graph)`: label visibility thresholds, physics tuning, node sizing strategy. The archetype classification (if implemented) could further inform renderer choice — e.g. archipelagos benefit from component-aware layout, hairballs need aggressive simplification before rendering.

### `inline_relations` discoverability

The archetypes doc identifies `inline_relations=["hasPart", "author", ...]` as the best middle ground for OHRM crates, but users need domain knowledge to pick the right properties. An introspection method — e.g. `ROCrateReader.inline_relation_summary(path)` or `crate.edge_type_counts()` — that shows which property keys produce how many edges would let users make informed choices without inspecting raw JSON-LD.

### `glimpse()` collection-awareness

`glimpse()` (type-level merge) produces rich diagrams for OHRM crates (34+ unique types) but collapses into a few nodes dominated by `File` for LDaCA crates. For File-dominated crates, merging by a secondary property (parent dataset, media type, or directory path) would produce more informative type-level views.

### Isolate handling

Archipelago crates have dozens of zero-edge isolate nodes that add visual noise. The mitigation is `select(min_connections=1)`, which works but isn't discoverable. Options: make `simplify()` strip isolates by default (it already strips low-degree nodes), add a `drop_isolates()` convenience, or add a `min_connections=1` default to `visualise()`.

### Data vs contextual entity convenience

The `data_entity_fraction` finding reveals LDaCA crates are 63% data entities while OHRM crates are ~0%. The doc recommends filtering out data entities for LDaCA structural analysis and notes OHRM crates are already entirely contextual. `Entity.has_data` exists but there's no convenience like `crate.select(contextual_only=True)` or `crate.data_entities` / `crate.contextual_entities` properties to make the split easy.

## Graph Engine Abstraction

The `GraphBackend` ABC was removed because it only abstracted storage while the algorithm layer (Cypher queries, community detection, connected components) imported NetworkX directly, bypassing the backend. A non-NetworkX backend could be plugged in for storage but was silently ignored by every analytical operation.

The RDFLib backend was reconsidered: RDF export is better served by a Writer (serialisation concern) than a backend (storage concern). This avoids forcing messy real-world crates through RDF validation at load time, which would either drop data or hide quality issues — both unacceptable when surfacing data quality is a core use case. rustworkx was never used outside uncommitted benchmarks.

**Trade-offs accepted:**
- No swappable graph engine. NetworkX is the only backend.
- If NetworkX becomes a bottleneck, targeted optimisation (caching, lazy evaluation, or selective use of rustworkx for specific algorithms) is the first response — not a full engine swap.

**Requirements for a full backend abstraction (if ever needed):**

A genuine swappable backend would need to abstract both storage *and* algorithms:
1. The backend interface would need to expose algorithm operations (shortest path, centrality, community detection, connected components), not just CRUD.
2. Cypher query support would need a backend-agnostic path (grand-cypher is NetworkX-specific).
3. Every analytical function in `analysis.py` and `query.py` would need to go through the abstraction rather than importing NetworkX directly.
4. The subgraph operation would need to preserve backend type through filtering chains.

This is a significantly larger undertaking than the original ABC, which is why it should only be pursued when there's a concrete performance or capability requirement driving it — not speculatively.

## Plugin Implementations

Extension points that exist as ABCs but have no concrete implementations yet:

- **Writers** (partial) — GraphML and CSV shipped (see [Writers guide](../docs/writers.md)). RDF and RO-Crate export planned.
- **Validators** — RDF/schema.org compliance checking, crate structure validation. Should report issues without blocking usage.
- **Additional readers** — GEXF, RiC-O (via RDFLib), NetworkX graph import

## Interoperability

Export methods to bridge crategraph with other tools:

```python
# Drop down to NetworkX for custom analysis
G = crate.to_networkx()

# Export to GraphML for Gephi / yEd
crate.write("crate.graphml", format="graphml")

# Export to CSV (two files: nodes.csv and edges.csv in the given directory)
crate.write("crate_tables/", format="csv")
```

RDF (JSON-LD, Turtle) and GEXF export are planned future formats.

## Natural Language Query Interface

LLM-driven graph querying — ask a question in plain language, get back a result:

```python
result = crate.ask("Which organisations in Melbourne had the most members in the 1880s?")
result.visualise()
```

This is likely simpler to implement over a NetworkX backend (LLM generates Python using the existing `select`/`where`/`pattern` API) than over SPARQL or Cypher. The existing chainable API is already close to natural language in structure, which should make prompt engineering more tractable.

## `inspect()` / `view()` Naming

The names `inspect()` and `view()` may be confusing — `inspect` suggests "look at" but actually extracts text content, while `view` is the one that produces a visual preview. In the current implementation, `inspect` is effectively `extract` (convert file to markdown via markitdown). The name may make more sense if other inspector implementations emerge that do something other than text extraction (e.g. metadata extraction, structural analysis), but for now the distinction is unintuitive. Revisit once the inspector plugin ecosystem has more shape — renaming to `extract()` would be a breaking change but might be clearer if text extraction remains the primary use case.

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
