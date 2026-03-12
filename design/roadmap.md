# Roadmap

Planned features and future directions for crategraph. These are deferred until there's a concrete use case driving the design, rather than building speculatively.

## Archetype-related API Challenges

Profiling 47 crates across two collections identified four structural archetypes (Star, Hairball, Archipelago, Compact — see [crate-archetypes](../docs/crate-archetypes.md)). These findings expose gaps between the current API surface and the workflows users actually need. The challenges below are listed in priority order.

### Root Dataset handling

**The problem.** The root Dataset entity (`./`) is connected to virtually every other entity in most crates. It inflates degree metrics, dominates force-directed layouts, and is informationally empty for structural analysis purposes. The archetypes doc calls filtering it out "almost always the right first step," yet the current API requires users to do this manually every time via `select()`.

The question is not whether to address this, but *where in the stack* to address it. Making every analysis/rendering method accept an `include_root` parameter would be a maintenance burden and inconsistent across the API. The root needs to be dealt with once, in one place.

**What the root entity is used for today:**

- It carries collection-level metadata (name, description, licence, datePublished, etc.) in its properties
- `Entity.has_data` already explicitly excludes it (`models.py:43`)
- `inspect()` and `view()` already explicitly reject it (`graph.py:281, 360`)
- `Graph.metadata` currently only stores `@context` from the JSON-LD wrapper — *not* the root entity's properties

So several methods already special-case the root. It's a packaging artefact, not a structural participant.

**Options:**

**A. Exclude at load time** — `Crate("path/", include_root=False)` as the default, with `include_root=True` to opt back in.

The `ROCrateReader` would skip the `./` entity and all its incident edges during parsing. The root entity's properties (name, description, licence) would be merged into `Graph.metadata` so they're accessible via `crate.metadata["name"]` etc., rather than lost entirely.

- *For:* Cleanest downstream — no method ever sees the root node. The graph represents the crate's *content*, while `metadata` describes the *collection*. This matches how researchers actually think about the data.
- *Against:* Breaking change to default behaviour. Users who currently iterate `crate.entities` and expect to find `./` would need to update code. Multi-crate loading would need to handle per-crate metadata. Edges from other entities that reference `./` as a target (e.g. `isPartOf: {"@id": "./"}`) would become orphaned and need handling (drop silently? redirect to a synthetic collection node?).
- *Edge case:* Some edges point *to* the root (e.g. `isPartOf: ./`). These would need to either be dropped or redirected. Dropping them is likely fine — `isPartOf: ./` is tautological ("this entity is part of the collection") and carries no structural information.

**B. Promote root metadata to `Graph.metadata`, keep node, add convenience method** — `crate.without_root()` returns a new Graph with the root entity and its edges removed.

The root entity's properties would be copied to `Graph.metadata` at load time (in addition to `@context`), so metadata access doesn't require the node. The root node would remain in the graph for backwards compatibility but could be explicitly removed.

- *For:* Non-breaking. Metadata accessible either way. Users who need the root can keep it.
- *Against:* Root still distorts every default `profile()`, `summary()`, `most_connected()`, and `visualise()` call. Users still need to remember to remove it. Doesn't solve the "almost always the right first step" problem — it just makes the step slightly more convenient.

**C. Shadow entity — root stored on `Crate` but excluded from graph traversal** — `crate.root` returns the Entity, but it doesn't appear in `crate.entities`, `crate.relationships`, or any graph operation.

- *For:* Root metadata accessible via `crate.root.properties["name"]`. Graph operations are clean without explicit removal.
- *Against:* Two-tier entity system is confusing. "Is the root in the graph or not?" Edges involving the root would also need to be shadowed, adding complexity to the backend. Hard to explain in documentation.

**D. Exclude from analysis/rendering defaults** — every method that computes metrics or renders the graph skips the root by default, with an `include_root=True` escape hatch.

- *For:* Root stays in the graph for iteration/access. Analysis is clean by default.
- *Against:* Every method needs the parameter. Inconsistent behaviour — `len(crate)` includes the root, `profile()` doesn't. Testing burden multiplies. This is the approach the archetypes doc implicitly warns against.

**Recommendation:** Option A (exclude at load time) is the cleanest long-term design, with Option B as a non-breaking stepping stone. The root entity's properties should be promoted to `Graph.metadata` regardless of which option is chosen — that metadata belongs on the collection, not on a graph node. If Option A is adopted, `isPartOf: ./` edges should be silently dropped (they're tautological), and the parameter should be `include_root=True` to opt back in rather than `exclude_root` to avoid double-negatives.

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
