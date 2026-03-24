# Design Decisions

Rationale behind key architectural choices in crategraph. Companion to [api-design.md](api-design.md).

## Backend: NetworkX Direct

**Decision:** `Graph` owns an `nx.MultiDiGraph` directly. There is no swappable backend abstraction. RDFLib is an optional dependency reserved for future validation and RDF-based readers (e.g. RiC-O), not as a graph engine.

**History:** The project originally had a `GraphBackend` ABC with NetworkX, rustworkx, and RDFLib implementations. This was removed because the abstraction only covered storage (add/query nodes and edges) while the algorithm layer (Cypher queries, community detection, connected components) imported NetworkX directly. A non-NetworkX backend could be plugged in for storage but was silently ignored by every analytical operation.

**Why not RDFLib as a backend?** RDF export is a serialisation concern (Writer), not a storage concern. Forcing crates through RDF validation at load time would either drop data or hide quality issues — both unacceptable when surfacing data quality is a core use case.

**Scaling:** NetworkX handles tens of thousands of nodes comfortably. If a specific algorithm becomes a bottleneck, rustworkx can be used locally within that function without a full backend abstraction. See [roadmap.md](roadmap.md) for requirements of a full backend abstraction if ever needed.

## Data Models: Dataclasses + Pydantic

**Decision:** Frozen dataclasses for internal models (`Entity`, `Relationship`) and result types (`FileInfo`, `ViewInfo`). Pydantic for user-facing models where validation and serialisation matter (`ValidationReport`, `SelectOptions`).

**Why frozen dataclasses?** The immutable-results principle means entities and relationships should not be mutated after creation. `frozen=True` enforces this at the language level. Dataclasses are stdlib, lightweight, and sufficient for simple containers. Inspection and viewer results (`FileInfo`, `ViewInfo`) also use frozen dataclasses — they're immutable result objects, not configuration.

**Why Pydantic for validation and configuration models?** Automatic validation, type coercion, and JSON serialisation. Useful for validation reports and structured option types. Pydantic is already a dependency (used in the core), so there's no cost to using it where it adds value.

## Plugin Contracts: ABCs not Protocols

**Decision:** Extension points (Reader, Writer, Renderer, Validator, Inspector, Viewer) use abstract base classes.

**Why not Protocols?** Protocols (structural typing) are more Pythonic and friendlier for third-party plugins — contributors don't need to import base classes. But ABCs are better for enforcing contracts and providing helpful error messages when methods are missing. For an early-stage project with few third-party plugins, explicitness wins. Protocols can be adopted later if there's community demand.

**Future:** Entry points (`[project.entry-points."crategraph.readers"]`) could allow `pip install crategraph-myformat` to auto-register readers. Not needed until there are actual third-party plugins.

## Query Language: Cypher over SPARQL

**Decision:** Optional Cypher query support via grand-cypher, rather than SPARQL.

**Why?** The target audience is researchers, not RDF specialists. Cypher's pattern-matching syntax (`(a:Person)-[:knows]->(b:Person)`) maps naturally to how people think about graph relationships. SPARQL is more powerful but has a steeper learning curve. The shorthand support (bare patterns auto-wrapped in `MATCH ... RETURN`) lowers the bar further.

**Tradeoff:** Cypher support depends on grand-cypher, which is a smaller community than RDFLib/SPARQL. This is mitigated by making it optional — the Pythonic filtering API (`select`, `where`, `pattern`, `search`) covers most use cases without any extra dependencies.

## Visualisation: Method not Spelling

**Decision:** The method is `visualise()`, using Australian English consistent with the project's spelling conventions.

Four built-in renderers cover different use cases:
- **Pyvis ("2d")** — interactive network exploration in notebooks
- **3d-force-graph ("3d")** — immersive 3D exploration, good for presentations
- **SVG ("svg")** — static output for documents and reproducible figures
- **Sigma.js ("sigma")** — WebGL-accelerated rendering for large graphs via ForceAtlas2 layout

The `glimpse()` method provides a one-call type-level overview by merging nodes by type and rendering as SVG.

## Inline Relations: Configurable Edge Extraction

**Decision:** By default, all `@id` references in entity properties become edges in the graph (`inline_relations=True`). This can be turned off or restricted to specific properties.

**Why default to True?** RO-Crates vary widely in how they encode relationships. Some use reified `Relationship` entities, others use inline `@id` references in properties like `author`, `location`, `memberOf`. Extracting all of these produces a richer, more connected graph. Users working with well-structured crates can restrict this.

For planned features and future directions, see [roadmap.md](roadmap.md).
