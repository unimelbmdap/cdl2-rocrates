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

The plugin-style architecture is unevenly mature across subsystems. Current ranking from least complete to most complete:

1. **Validators** — least complete. The `Validator` ABC and validation result models exist, but there are no concrete validators, no validator registry, and no public validation workflow yet. Likely first implementations: RDF/schema.org compliance checks, RO-Crate structure checks, broken-link checks, and completeness checks. Validators should report issues without blocking graph loading or exploration.
2. **Registration and discovery consistency** — cross-cutting architectural gap. Writers have the clearest registry (`register_writer`, `get_writer`, `list_formats`). Inspectors and viewers use private ordered lists plus `find_*()`. Renderers are selected through hard-coded dispatch in `visualise()`. Readers are mostly selected through direct construction or ad hoc reader lists. Before adding many more plugins, standardise the registration surface.
3. **Inspectors** — useful but thin. `MarkItDownInspector` provides broad content extraction, but there are no specialised inspectors yet for tabular structure, image metadata, audio/video metadata, geospatial data, or other common research file types.
4. **Viewers** — functional but shallow. `DefaultViewer` handles common preview cases, but the subsystem is still a single catch-all viewer rather than a mature ecosystem of specialised previews.
5. **Writers** — partially complete. GraphML and CSV are shipped and documented (see [Writers guide](../docs/writers.md)). RDF, RO-Crate round-trip export, and GEXF remain planned.
6. **Readers and renderers** — most complete in user-visible capability. Readers cover RO-Crate, folders, RDF, OHRM CSV, and OHRM SQL. Renderers cover 2D, 3D, SVG, and Pyvis. Their remaining plugin gap is mostly registration/discovery consistency rather than lack of built-in implementations.

Recommended next step: standardise plugin registration before adding many new plugin implementations. Use private dictionaries or ordered lists internally, expose public helpers (`register_*`, `get_*` or `find_*`, and `list_*`), and define built-ins declaratively so they can be lazily registered. Named plugins such as writers, renderers, readers, and validators should use name-based registries; capability-matched plugins such as inspectors and viewers should use ordered registries where specialised plugins can take priority over broad defaults.

## Matplotlib (static, styleable) Renderer

The current renderers (2D sigma, 3D force-graph, SVG, Pyvis) all colour nodes from a fixed
vivid palette via `resolve_colour_map()`, and the sigma legend is always built from entity
*types* regardless of `colour_by`. This works well for type-coloured exploration but blocks two
things that came up writing the EOAS case study:

- **Highlight-and-dim views.** A common analytical move is to draw a large network with a few
  nodes emphasised (the connectivity hubs, the isolated records, a query result) and everything
  else faded to a muted grey. `colour_by` on an annotated binary field *does* drive the node
  colours correctly, but both groups get saturated palette colours, so the common mass is as loud
  as the highlighted few. The case study had to drop to raw matplotlib (`graph.layout()` for
  positions, then `scatter`/`LineCollection` with hand-set colours, sizes, and alpha) to get a
  readable highlight-on-grey figure.
- **Correct legends for non-type colourings.** When `colour_by` is not `"type"`, the sigma legend
  still lists types, which is misleading. The `simple=True` variant sidesteps this by omitting the
  legend entirely, but then there is no key at all.

A `renderer="matplotlib"` (static PNG/SVG) option would cover these: reuse the graph's existing
`layout()`, expose per-group colours (or a base-plus-highlight scheme), node size/alpha control,
and a legend keyed to whatever `colour_by` resolved. It would also give publication-quality static
figures for papers and docs without a browser. A lighter alternative that stays within the existing
renderers is to (a) let `colour_by` accept an explicit colour map / a "dim everything except these
ids" highlight mode, and (b) make the sigma legend follow `colour_by` rather than always showing
types.

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

## File Content Analysis Strategy

crategraph's role should be to help researchers find, select, preview, extract, search, and hand off files for analysis. It should not try to become a complete analysis library for every file format found in RO-Crates.

The current architecture already supports this boundary:

- `Graph` remains the metadata and relationship layer.
- `view()` remains a presentation layer for human preview.
- `inspect()` / inspectors remain the extraction layer, currently backed by MarkItDown for broad text-oriented conversion.
- External tools such as pandas, spaCy, scikit-learn, librosa, OpenCV, GIS libraries, or domain-specific notebooks remain responsible for deeper analysis.

This keeps crategraph useful at the research workflow boundary without letting the package scope explode. The package should make it easy to assemble a meaningful subset of files from crate metadata and relationships, then pass those files and their context to the right downstream tool.

### File handoff APIs

Add lightweight APIs that expose selected file entities in analysis-friendly shapes:

```python
# Paths plus entity metadata and graph context.
# This would be a new file-level helper; the existing
# CorpusProfile.to_dataframe() covers aggregate crate profiles only,
# and graph.write(..., format="csv") exports graph nodes and edges.
files = crate.select(entity_types=["File"]).files_dataframe()

# Iterator for custom pipelines
for entity, path in crate.where(encodingFormat="text/plain").iter_files():
    ...

# Cheap by default; optional content extraction
rows = crate.select(entity_types=["File"]).inspect_all(extract_content=False)
rows_with_text = crate.select(entity_types=["File"]).inspect_all(extract_content=True)
```

The important design choice is that these methods should help users move from a graph selection to ordinary Python analysis inputs. They should not prescribe the analysis itself.

The existing CSV writer already covers graph-shaped export by writing `nodes.csv` and `edges.csv`. File handoff needs a different tabular shape: one row per selected file, with resolved path, entity metadata, source crate, media type, optional extracted content, and possibly selected relationship/context columns. That output could be exposed both as a DataFrame and as a single CSV manifest:

```python
files = crate.select(entity_types=["File"]).files_dataframe()
files.to_csv("selected_files.csv", index=False)

# Convenience wrapper around the same rows, if the use case is common enough.
crate.select(entity_types=["File"]).write_file_manifest("selected_files.csv")
```

### User-defined file functions

A callback-style API could make ad hoc analysis concise while preserving crategraph's boundary:

```python
def word_count(path, entity):
    text = path.read_text(encoding="utf-8")
    return {"entity_id": entity.id, "words": len(text.split())}

results = crate.where(encodingFormat="text/plain").map_files(word_count)
```

This would let crategraph handle entity coercion, path resolution, crate-root safety checks, and result collation, while users supply the actual file-specific analysis. Return values should be DataFrame-friendly dictionaries or simple Python values.

### Optional analyser plugins

An `Analyser` plugin subsystem could be added later if repeated use cases show a stable shape. This should not be the first step: "analysis" is too broad and risks becoming a dumping ground for unrelated file-format logic.

If introduced, analysers should have narrow contracts, for example:

- Accept a resolved file path plus the corresponding `Entity`.
- Return a structured immutable result.
- Avoid mutating the graph in place.
- Optionally provide a separate transform that returns a new `Graph` with derived annotations and clear provenance.

This is a longer-term extension point, not a prerequisite for helping researchers analyse crate files.

### Recipes and examples

Documented workflows should carry part of this feature area. Example notebooks may be more useful than built-in algorithms:

- Find all text files connected to a person, place, collection, or event.
- Extract markdown from selected files and run keyword or topic analysis.
- Export selected files and metadata for use in R, pandas, or a qualitative analysis tool.
- Search file content, then return to the graph to inspect surrounding context.
- Demonstrate handoff from crategraph selections to LDaCA text-analysis Python tools, especially where both sides already understand RO-Crate-style inputs and metadata.

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
