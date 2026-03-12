# Crate Archetypes

Understanding the structural diversity of RO-Crates is essential for building tools that work well across real-world data. This page documents the graph archetypes we've identified by profiling 47 crates from two collections — 27 OHRM crates and 20 LDaCA crates — and the challenges each presents for visualisation and analysis.

These findings were generated using `Corpus.profile()` and directly inform crategraph's design decisions around defaults, rendering, and filtering.

## Profiling methodology

Each crate was profiled with `Graph.profile()` and aggregated using `Corpus`. Because the two collections encode relationships differently (see [Inline vs reified relationships](#inline-vs-reified-relationships)), OHRM crates were profiled in both modes:

```python
from crategraph import Corpus
from crategraph.readers.rocrate import ROCrateReader

# LDaCA — uses a mix of inline and reified relationships
ldaca = Corpus("data/ldaca/metadata_only/*", "data/ldaca/Australian_Corpus_of_English")

# OHRM — inline mode (default): all @id references become edges
ohrm_inline = Corpus("data/ohrm/*", "data/ohrm/metadata_only/*")

# OHRM — reified only: only explicit Relationship entities become edges
ohrm_reified = Corpus(
    "data/ohrm/*", "data/ohrm/metadata_only/*",
    readers=[ROCrateReader(inline_relations=False)],
)
```

Key metrics: **hub ratio** (max_degree / entity_count — how star-like the graph is), **density**, **component count**, and **degree skewness**.

## The archetypes

### 1. The Star (hub ratio > 0.9)

The root Dataset entity (`./`) is connected to virtually every other entity. The graph is structurally a star with one central node.

**Examples:** ASMP (3,750 entities, hub ratio 1.0), Australian Corpus of English (2,583 entities, hub ratio 0.995). Every OHRM crate is a star when loaded with `inline_relations=True` — this is an artefact of the export format rather than the underlying data (see [Inline vs reified relationships](#inline-vs-reified-relationships)).

**Characteristics:**

- One node (the root `Dataset`) has degree equal to nearly the entire graph
- Extremely high skewness (28–280)
- Low density despite the hub — most nodes connect only to the root

**Challenges:**

- Force-directed layouts produce a uniform ball around the central hub — no structural insight visible
- The root node is informationally empty (it's just "the collection") but dominates every metric
- Node sizing by degree makes the root enormous and everything else invisible

**Mitigation:** Use `simplify()` to strip peripheral nodes, or `select()` to exclude the root Dataset. `glimpse()` (type-level merge) collapses the star into a meaningful type-relationship diagram. For OHRM crates, switching to `inline_relations=False` reveals the reified relationship structure underneath the star (see [Inline vs reified relationships](#inline-vs-reified-relationships)).

### 2. The Hairball (1,000+ entities, high skewness)

Large graphs with extreme degree inequality. A few hub nodes (root dataset, licence entities, shared terms) connect to thousands of leaf nodes.

**Examples:** Speech of Australian adolescents (37,686 entities, skewness 105), ICE-AUS (6,423 entities, skewness 69), COOEE (8,078 entities, skewness 40).

**Characteristics:**

- Entity counts in the thousands to tens of thousands
- Degree distribution follows a power law — a handful of hubs, a long tail of degree-1 leaves
- Very low density (0.0001–0.001) because the graph is sparse despite its size

**Challenges:**

- Too large to render directly — any visualisation is a meaningless blob
- Even `simplify()` may need multiple rounds of chaining to reveal structure
- Performance matters — profiling and rendering must scale to tens of thousands of nodes

**Mitigation:** Start with `glimpse()` or `merge_nodes(by="type")` for orientation. Use `simplify().simplify()` chains or `select()` to narrow to a workable subgraph before visualising. `collapse_edges=True` is essential.

### 3. The Archipelago (multiple disconnected components)

The graph fragments into separate clusters with no connections between them, plus isolated nodes with zero edges.

**Examples:** Braided Channels (576 entities, 56 components, 55 isolates), Farms to Freeways (764 entities, 10 components, 9 isolates), COOEE (8,078 entities, 11 components, 10 isolates). OHRM crates loaded with `inline_relations=False` are extreme archipelagos — reified relationships connect only a small subset of entities, leaving the rest as isolates.

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

**Examples:** Expanded Auslan Corpus (12 entities), AusReddit (28 entities), La Trobe Corpus (57 entities), Holmer Fieldnotes (94 entities). Several smaller OHRM crates also fall into this category.

**Characteristics:**

- Density 0.02–0.15 — much higher than larger crates
- Low skewness (1–7) — degree is fairly evenly distributed
- Typically a single connected component

**Challenges:**

- Minimal — these render well with default settings
- Good for demos, tutorials, and testing

## Cross-cutting findings

### Inline vs reified relationships

The two collections encode relationships in fundamentally different ways, and the `inline_relations` parameter on `ROCrateReader` controls which edges are extracted:

**OHRM crates** use two relationship mechanisms:
- **Inline `@id` references** in entity properties (e.g. `"hasPart": {"@id": "#file1"}`) — these form the bulk of connections and create the star topology when `inline_relations=True`
- **Reified `Relationship` entities** with explicit `source`/`target` properties — these represent curated, typed relationships between entities (e.g. entity-to-function mappings)

The contrast is dramatic. With `inline_relations=True`, DASC has 39,836 edges and a single connected component. With `inline_relations=False`, it has 16,290 edges from reified relationships but 5,041 disconnected components — the reified relationships connect only a subset of entities.

| Crate | Entities | Inline edges | Reified edges | Reified hub ratio |
|-------|----------|-------------|---------------|-------------------|
| DASC  | 10,861   | 39,836      | 16,290        | 0.43              |
| WHSO  | 3,043    | 9,093       | 2,137         | 0.03              |
| CTAC  | 12,741   | 36,245      | 1,353         | 0.03              |
| WAMI  | 4,053    | 11,790      | 689           | 0.06              |
| CHIA  | 35,325   | 97,325      | 453           | 0.004             |
| WALL  | 2,030    | 5,603       | 455           | 0.01              |
| MODC  | 3,708    | 9,994       | 341           | 0.002             |
| ULSS  | 1,796    | 3,538       | 167           | 0.02              |
| IAEA  | 434      | 1,189       | 20            | 0.009             |

Around a third of OHRM crates have **zero reified relationships** — their structure is entirely inline.

**LDaCA crates** use a mix of inline references and reified relationships, and the structural variety (stars, hairballs, archipelagos, compacts) emerges naturally with `inline_relations=True`.

**Implications for tooling:** When exploring OHRM crates, `inline_relations=True` gives the complete picture but produces uniform stars. `inline_relations=False` reveals the curated relationship structure but loses most connectivity. A selective approach — `inline_relations=["hasPart", "author", ...]` — may offer the best middle ground.

### Multi-edges are universal

Every crate in the corpus has parallel edges between at least some node pairs (max edge multiplicity 2–5). This is because entities commonly share multiple relationship types (e.g. a person might be both `author` and `editor` of the same work). `collapse_edges=True` should be considered the default for readable visualisations.

### The root Dataset dominates most graphs

The root entity (`./`, type `Dataset`) acts as a collection-level hub in nearly every crate. It connects to all top-level entities and inflates degree metrics. For structural analysis of the *content* of a crate (rather than its packaging), filtering out the root is almost always the right first step.

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

Different collections can produce very different archetype distributions. OHRM crates are uniformly stars with `inline_relations=True` (hub ratio 0.98–1.0 across the board), while LDaCA crates span the full range of archetypes with hub ratios from 0.20 to 0.99. This is a property of the export format, not the underlying data — the OHRM format lists every entity via inline references from the root Dataset, masking the richer reified structure underneath.

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
ldaca = Corpus("data/ldaca/metadata_only/*", "data/ldaca/Australian_Corpus_of_English")

# OHRM — both modes
ohrm_inline = Corpus("data/ohrm/*", "data/ohrm/metadata_only/*")
ohrm_reified = Corpus(
    "data/ohrm/*", "data/ohrm/metadata_only/*",
    readers=[ROCrateReader(inline_relations=False)],
)

for name, corpus in [("ldaca", ldaca), ("ohrm_inline", ohrm_inline), ("ohrm_reified", ohrm_reified)]:
    result = corpus.profile()
    df = result.to_dataframe()
    df["hub_ratio"] = df["max_degree"] / df["entity_count"]
    df.to_csv(f"crate_profiles_{name}.csv", index=False)
```
