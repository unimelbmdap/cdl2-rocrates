# Crate Archetypes

Understanding the structural diversity of RO-Crates is essential for building tools that work well across real-world data. This page documents the graph archetypes we've identified by profiling 47 crates from two collections — 27 OHRM crates and 20 LDaCA crates — and the challenges each presents for visualisation and analysis.

These findings were generated using `Corpus.profile()` and directly inform crategraph's design decisions around defaults, rendering, and filtering.

## Profiling methodology

Each crate was profiled with `Graph.profile()` and aggregated using `Corpus`. All profiling uses the default `include_root=False` — the root Dataset entity and its edges are excluded, and its properties are promoted to `Graph.metadata`. This matches the default `Crate(...)` behaviour and reflects what users see out of the box. Because the two collections encode relationships differently (see [Inline vs reified relationships](#inline-vs-reified-relationships)), OHRM crates were profiled in both modes:

```python
from crategraph import Corpus
from crategraph.readers.rocrate import ROCrateReader

# LDaCA — uses a mix of inline and reified relationships
ldaca = Corpus(
    "data/ldaca/metadata_only/*", "data/ldaca/Australian_Corpus_of_English",
    readers=[ROCrateReader(include_root=False)],
)

# OHRM — inline mode (default): all @id references become edges
ohrm_inline = Corpus(
    "data/ohrm/*", "data/ohrm/metadata_only/*",
    readers=[ROCrateReader(include_root=False)],
)

# OHRM — reified only: only explicit Relationship entities become edges
ohrm_reified = Corpus(
    "data/ohrm/*", "data/ohrm/metadata_only/*",
    readers=[ROCrateReader(inline_relations=False, include_root=False)],
)
```

Key metrics: **hub ratio** (max_degree / entity_count — how star-like the graph is), **density**, **component count**, and **degree skewness**.

## The archetypes

### 1. The Star (hub ratio > 0.9)

A single entity is connected to virtually every other entity. The graph is structurally a star with one central node.

**Examples:** Australian Corpus of English (2,582 entities, hub ratio 0.995). This is the only crate in the corpus that remains a star after root exclusion — the hub is a non-root entity with connections to nearly every file node.

With `include_root=True`, every OHRM crate becomes a star (hub ratio 0.98–1.0) because the root Dataset entity connects to all top-level entities via inline `@id` references. This is an artefact of the export format rather than the underlying data, and is the primary reason `Crate` excludes the root by default.

**Characteristics:**

- One node has degree equal to nearly the entire graph
- Extremely high skewness
- Low density despite the hub — most nodes connect only to the central node

**Challenges:**

- Force-directed layouts produce a uniform ball around the central hub — no structural insight visible
- Node sizing by degree makes the hub enormous and everything else invisible

**Mitigation:** Use `simplify()` to strip peripheral nodes. `glimpse()` (type-level merge) collapses the star into a meaningful type-relationship diagram. For OHRM crates, switching to `inline_relations=False` reveals the reified relationship structure underneath (see [Inline vs reified relationships](#inline-vs-reified-relationships)).

### 2. The Hairball (1,000+ entities, high skewness)

Large graphs with extreme degree inequality. A few hub nodes (licence entities, shared terms, prolific people) connect to thousands of leaf nodes.

**Examples:** Speech of Australian adolescents (37,685 entities, skewness 108), UMAB (50,430 entities, skewness 95), AMAA (82,714 entities, skewness 87), ICE-AUS (6,422 entities, skewness 69), DASC (10,860 entities, skewness 59), COOEE (8,077 entities, skewness 43).

Many OHRM crates that were formerly stars are now hairballs — removing the root reveals that a few non-root entities (e.g. shared organisations, licence nodes, prolific archival functions) still act as hubs, but to a much lesser degree.

**Characteristics:**

- Entity counts in the thousands to tens of thousands
- Degree distribution follows a power law — a handful of hubs, a long tail of degree-1 leaves
- Very low density (0.0001–0.001) because the graph is sparse despite its size
- Often combined with archipelago characteristics — many disconnected components (see below)

**Challenges:**

- Too large to render directly — any visualisation is a meaningless blob
- Even `simplify()` may need multiple rounds of chaining to reveal structure
- Performance matters — profiling and rendering must scale to tens of thousands of nodes

**Mitigation:** Start with `glimpse()` or `merge_nodes(by="type")` for orientation. Use `simplify().simplify()` chains or `select()` to narrow to a workable subgraph before visualising. `collapse_edges=True` is essential.

### 3. The Archipelago (multiple disconnected components)

The graph fragments into separate clusters with no connections between them, plus isolated nodes with zero edges.

**Examples:** UMAB (50,430 entities, 13,033 components), SCPP (2,735 entities, 681 components), CHIA (35,324 entities, 624 components), KHRD (41,107 entities, 599 components), Braided Channels (575 entities, 60 components), Holmer Fieldnotes (93 entities, 63 components).

Many OHRM crates become archipelagos when the root is excluded — the root entity was often the sole connector between otherwise independent subgroups. This reveals that the inline `@id` references in OHRM crates are primarily from the root to its children, with relatively few lateral connections between entities. OHRM crates loaded with `inline_relations=False` are even more extreme archipelagos — reified relationships connect only a small subset of entities, leaving the rest as isolates.

**Characteristics:**

- Multiple weakly connected components, often one large component plus many singletons
- Isolates are typically metadata nodes (e.g. `PropertyValue` entities) with no relationships
- Components may represent independent sessions, interviews, or data subsets within the collection

**Challenges:**

- Force-directed layouts scatter disconnected components randomly — the output looks chaotic
- Isolate nodes are visual noise with no structural information
- No spatial logic groups related components together

**Mitigation:** Use `select(min_connections=1)` to strip isolates. Filter to specific components or entity types with `select()` or `pattern()`. `detect_communities()` can identify clusters within connected portions.

### 4. The Compact (< 100 entities, moderate density)

Small, well-connected graphs with relatively uniform degree distributions.

**Examples:** Expanded Auslan Corpus (11 entities), AusReddit (27 entities), La Trobe Corpus (56 entities), Australian Deafblind Signing Corpus (16 entities). Several smaller OHRM crates also fall into this category (CREG at 91, RCCA at 67, REUN at 55).

**Characteristics:**

- Density 0.02–0.15 — much higher than larger crates
- Low skewness (0–7) — degree is fairly evenly distributed
- May have multiple components after root exclusion, but small enough that this doesn't impede visualisation

**Challenges:**

- Minimal — these render well with default settings
- Good for demos, tutorials, and testing

## Cross-cutting findings

### Inline vs reified relationships

The two collections encode relationships in fundamentally different ways, and the `inline_relations` parameter on `ROCrateReader` controls which edges are extracted:

**OHRM crates** use two relationship mechanisms:
- **Inline `@id` references** in entity properties (e.g. `"hasPart": {"@id": "#file1"}`) — these form the bulk of connections
- **Reified `Relationship` entities** with explicit `source`/`target` properties — these represent curated, typed relationships between entities (e.g. entity-to-function mappings)

The contrast is dramatic. With `inline_relations=True` (root excluded), DASC has 28,976 edges and 429 components. With `inline_relations=False`, it has 16,290 edges from reified relationships but 5,041 components — the reified relationships connect only a subset of entities.

| Crate | Entities | Inline edges | Reified edges | Reified hub ratio |
|-------|----------|-------------|---------------|-------------------|
| DASC  | 10,860   | 28,976      | 16,290        | 0.43              |
| WHSO  | 3,042    | 6,050       | 2,137         | 0.03              |
| CTAC  | 12,740   | 23,505      | 1,353         | 0.03              |
| WAMI  | 4,052    | 7,738       | 689           | 0.06              |
| CHIA  | 35,324   | 61,996      | 453           | 0.004             |
| WALL  | 2,029    | 3,574       | 455           | 0.01              |
| MODC  | 3,707    | 6,287       | 341           | 0.002             |
| ULSS  | 1,795    | 1,743       | 167           | 0.02              |
| IAEA  | 433      | 756         | 20            | 0.009             |

Around a third of OHRM crates have **zero reified relationships** — their structure is entirely inline.

**LDaCA crates** use a mix of inline references and reified relationships, and the structural variety (stars, hairballs, archipelagos, compacts) emerges naturally with `inline_relations=True`.

**Implications for tooling:** When exploring OHRM crates, `inline_relations=True` gives the complete picture but many entities are only connected within their local cluster. `inline_relations=False` reveals the curated relationship structure but loses most connectivity. A selective approach — `inline_relations=["hasPart", "author", ...]` — may offer the best middle ground.

### Multi-edges are universal

Every crate in the corpus has parallel edges between at least some node pairs (max edge multiplicity 2–5). This is because entities commonly share multiple relationship types (e.g. a person might be both `author` and `editor` of the same work). `collapse_edges=True` should be considered the default for readable visualisations.

### Root Dataset handling

The root Dataset entity is a collection-level packaging artefact that connects to most or all top-level entities via inline `@id` references. `Crate` excludes it by default (`include_root=False`), promoting its properties (name, description, licence, etc.) to `Graph.metadata` so collection-level information remains accessible via `crate.metadata["name"]`.

The impact of root exclusion varies by collection:

- **OHRM crates** are transformed. With the root included, every OHRM crate is a star (hub ratio 0.98–1.0). With the root excluded, hub ratios drop to 0.01–0.56, skewness decreases by 50–90%, and single-component graphs fragment into dozens or hundreds of components. The root was the sole structural glue — lateral connections between non-root entities are sparse.
- **LDaCA crates** see modest changes. Most hub ratios shift by less than 0.05, and component counts increase by 1–10. A few small LDaCA crates are more affected — Holmer Fieldnotes drops from hub ratio 0.67 to 0.02 (the root was its hub), and Farms to Freeways drops from 0.61 to 0.18. But the largest LDaCA crates (Speech of Australian adolescents, ICE-AUS) are barely affected because their hubs are non-root entities.

Use `Crate("path/", include_root=True)` to opt back in. When using `ROCrateReader` directly (including via `Corpus`), the root is included by default — pass `include_root=False` to exclude it.

### Scale varies by four orders of magnitude

Entity counts range from 2 (near-empty OHRM crates) to 82,715 (AMAA) across the corpus. No single renderer configuration (label visibility, node sizing, physics tuning) works well across this range. Adaptive defaults based on graph size are important.

### Density inversely correlates with size

Smaller crates are relatively dense (0.02–0.15), while large crates are extremely sparse (0.0001–0.002). This is typical of real-world networks and means that density alone is not a useful quality indicator — it must be interpreted relative to graph size.

### Data entities vs contextual entities

The RO-Crate spec distinguishes between **data entities** (files and datasets — the actual content) and **contextual entities** (people, organisations, places, concepts — metadata describing the context). The `data_entity_fraction` metric captures this split.

The two collections sit at opposite ends of the spectrum:

- **LDaCA crates are data-heavy.** Median data entity fraction is 0.63 — most entities are `File` nodes representing actual corpus data. The contextual entities (speakers, licences, collection metadata) are a minority.
- **OHRM crates are overwhelmingly contextual.** Median data entity fraction is 0.00 — most OHRM crates contain zero or near-zero data entities. Their entities are archival records, people, organisations, functions, and relationships — the graph *is* the data, not a wrapper around files.

A few OHRM crates do contain significant data entities (UMAB at 61%, SCPP at 21%, CTAC at 17%), typically where the archive includes digitised files alongside the archival description. But the typical OHRM crate is a pure knowledge graph with no file-level content.

**Caveat:** `data_entity_fraction` is based on `Entity.has_data`, which identifies `File` and `Dataset` types per the RO-Crate spec. This works well for LDaCA-style crates where data entities are local files. OHRM crates often describe archival resources (`PublishedResource`, `RepositoryObject`, etc.) that reference remote or physical items — these aren't captured by `has_data`, so the near-zero fractions partly reflect the metric's scope rather than a complete absence of describable content.

**Implications for tooling:** For LDaCA crates, the interesting structure often emerges after filtering *out* data entities (e.g. `select(entity_types=["Person", "Organisation"])`) to focus on the contextual relationships. For OHRM crates, the entire graph is already contextual — no filtering needed, but the challenge is navigating a large number of domain-specific entity types.

### Entity type spread

The `top_entity_type_fraction` metric (fraction of entities belonging to the most common type) reveals two distinct patterns:

**LDaCA crates are File-dominated.** In 13 of 20 crates, `File` is the most common entity type — these are primarily collections of data files with metadata wrappers. The top type typically accounts for 50–70% of entities (median 0.55), and crates use a modest vocabulary of 10–21 entity types.

**OHRM crates have domain-specific type vocabularies.** The dominant type varies by collection — `Related`, `Primary`, `PublishedResource`, `Person`, `School`, `Architect`, `Commissioner` — reflecting the subject matter of each archive. Type vocabularies are much richer (median 34 unique types, up to 131), and entities are more evenly distributed across them (median top fraction 0.36). Some OHRM crates are remarkably diverse: ICAE's most common type accounts for just 10% of its entities.

**Implications for tooling:** Type-based filtering (`select(types=...)`) is a powerful reduction strategy for OHRM crates but less useful for LDaCA crates where most entities are `File`. For OHRM, `glimpse()` (type-level merge) produces rich type-relationship diagrams because the type vocabulary is varied; for LDaCA, it tends to collapse into a small number of type nodes dominated by `File`.

### Collection-level uniformity vs diversity

With the root excluded, OHRM crates show substantial structural diversity. Hub ratios range from 0.01 to 0.56, component counts from 1 to 13,033, and skewness from 0 to 95. Many are simultaneously hairballs (large, high skewness) and archipelagos (many disconnected components) — the root was masking this dual nature by acting as a universal connector. LDaCA crates continue to span the full range of archetypes, with hub ratios from 0.02 to 0.99.

With `include_root=True`, OHRM crates collapse to uniform stars (hub ratio 0.98–1.0 across the board) — this is a property of the export format, not the underlying data.

## Using this for development

These archetypes inform which features matter most:

| Feature | Star | Hairball | Archipelago | Compact |
|---------|------|----------|-------------|---------|
| `simplify()` | Essential | Essential | Useful | Unnecessary |
| `glimpse()` | Essential | Essential | Useful | Optional |
| `collapse_edges` | Important | Important | Important | Helpful |
| `select()` / `where()` | Important | Essential | Essential | Optional |
| `detect_communities()` | Useful | Useful | Essential | Optional |
| Adaptive rendering | Important | Essential | Essential | Unnecessary |
| `inline_relations=False` | Reveals structure | N/A | N/A | N/A |

To regenerate this analysis with updated data:

```python
from crategraph import Corpus
from crategraph.readers.rocrate import ROCrateReader

# LDaCA
ldaca = Corpus(
    "data/ldaca/metadata_only/*", "data/ldaca/Australian_Corpus_of_English",
    readers=[ROCrateReader(include_root=False)],
)

# OHRM — both modes
ohrm_inline = Corpus(
    "data/ohrm/*", "data/ohrm/metadata_only/*",
    readers=[ROCrateReader(include_root=False)],
)
ohrm_reified = Corpus(
    "data/ohrm/*", "data/ohrm/metadata_only/*",
    readers=[ROCrateReader(inline_relations=False, include_root=False)],
)

for name, corpus in [("ldaca", ldaca), ("ohrm_inline", ohrm_inline), ("ohrm_reified", ohrm_reified)]:
    result = corpus.profile()
    df = result.to_dataframe()
    df["hub_ratio"] = df["max_degree"] / df["entity_count"]
    df.to_csv(f"crate_profiles_{name}.csv", index=False)
```
