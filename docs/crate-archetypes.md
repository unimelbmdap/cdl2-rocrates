# Crate Archetypes

Understanding the structural diversity of RO-Crates is essential for building tools that work well across real-world data. This page documents the graph archetypes we've identified by profiling 23 crates from the LDaCA collection and other sources, and the challenges each presents for visualisation and analysis.

These findings were generated using `Corpus.profile()` and directly inform crategraph's design decisions around defaults, rendering, and filtering.

## Profiling methodology

Each crate was loaded with `ROCrateReader` (default `inline_relations=True`), profiled with `Graph.profile()`, and aggregated using `Corpus`:

```python
from crategraph import Corpus

corpus = Corpus("data/ldaca/*", "data/ASMP-2", "data/IAEA-ro-crate")
result = corpus.profile()
df = result.to_dataframe()
```

Key metrics: **hub ratio** (max_degree / entity_count — how star-like the graph is), **density**, **component count**, and **degree skewness**.

## The archetypes

### 1. The Star (hub ratio > 0.9)

The root Dataset entity (`./`) is connected to virtually every other entity. The graph is structurally a star with one central node.

**Examples:** ASMP-2 (3,753 entities, hub ratio 0.999), IAEA (251 entities, hub ratio 0.996), Australian Corpus of English (2,583 entities, hub ratio 0.995).

**Characteristics:**

- One node (the root `Dataset`) has degree equal to nearly the entire graph
- Extremely high skewness (28–60)
- Low density despite the hub — most nodes connect only to the root

**Challenges:**

- Force-directed layouts produce a uniform ball around the central hub — no structural insight visible
- The root node is informationally empty (it's just "the collection") but dominates every metric
- Node sizing by degree makes the root enormous and everything else invisible

**Mitigation:** Use `simplify()` to strip peripheral nodes, or `select()` to exclude the root Dataset. `glimpse()` (type-level merge) collapses the star into a meaningful type-relationship diagram.

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

**Examples:** Braided Channels (576 entities, 56 components, 55 isolates), Farms to Freeways (764 entities, 10 components, 9 isolates), COOEE (8,078 entities, 11 components, 10 isolates).

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

**Examples:** Expanded Auslan Corpus (12 entities), Deafblind Signing (17 entities), AuTS (22 entities), AusReddit (28 entities), La Trobe Corpus (57 entities), Holmer Fieldnotes (94 entities).

**Characteristics:**

- Density 0.07–0.15 — much higher than larger crates
- Low skewness (1–3) — degree is fairly evenly distributed
- Typically a single connected component

**Challenges:**

- Minimal — these render well with default settings
- Good for demos, tutorials, and testing

## Cross-cutting findings

### Multi-edges are universal

Every crate in the corpus has parallel edges between at least some node pairs (max edge multiplicity 2–5). This is because entities commonly share multiple relationship types (e.g. a person might be both `author` and `editor` of the same work). `collapse_edges=True` should be considered the default for readable visualisations.

### The root Dataset dominates most graphs

The root entity (`./`, type `Dataset`) acts as a collection-level hub in nearly every crate. It connects to all top-level entities and inflates degree metrics. For structural analysis of the *content* of a crate (rather than its packaging), filtering out the root is almost always the right first step.

### Scale varies by three orders of magnitude

Entity counts range from 12 to 37,686 across the corpus. No single renderer configuration (label visibility, node sizing, physics tuning) works well across this range. Adaptive defaults based on graph size are important.

### Density inversely correlates with size

Smaller crates are relatively dense (0.08–0.15), while large crates are extremely sparse (0.0001–0.002). This is typical of real-world networks and means that density alone is not a useful quality indicator — it must be interpreted relative to graph size.

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

To regenerate this analysis with updated data:

```python
from crategraph import Corpus

corpus = Corpus("data/ldaca/*", "data/ASMP-2", "data/IAEA-ro-crate")
result = corpus.profile()
df = result.to_dataframe()
df["hub_ratio"] = df["max_degree"] / df["entity_count"]
df.to_csv("crate_profiles.csv", index=False)
```
