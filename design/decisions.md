# Design Decisions

Rationale behind key architectural choices in crategraph. Companion to [api-design.md](api-design.md).

## Backend: NetworkX Primary, RDFLib Optional

**Decision:** Parse JSON-LD directly as JSON, build a NetworkX graph. RDFLib is an optional dependency used only for validation.

**Why not RDFLib as primary?** Cultural collections are often converted from legacy databases and may not be fully RDF-compliant. RDFLib is strict — malformed crates fail at parse time, before the user can see the data. A key use case is *surfacing data quality issues visually*, which requires loading messy data first.

**Why not a hybrid?** Considered parsing via RDFLib where possible and falling back to JSON for non-compliant crates, but this creates two code paths with subtly different behaviour. Simpler to commit to one approach.

**Backend abstraction:** The `GraphBackend` ABC abstracts storage so the engine can be swapped without changing the public API. NetworkX is the default; rustworkx is available as an optional high-performance alternative. An experimental RDFLib backend exists but is incomplete.

**Scaling:** NetworkX is purely in-memory. This handles tens of thousands of nodes comfortably, which covers expected use cases. If scale becomes an issue, rustworkx provides a significant speedup, or the backend abstraction allows plugging in something more substantial.

## Data Models: Dataclasses + Pydantic

**Decision:** Frozen dataclasses for internal models (`Entity`, `Relationship`), Pydantic for user-facing models where validation and serialisation matter (`FileInfo`, `ValidationReport`).

**Why frozen dataclasses?** The immutable-results principle means entities and relationships should not be mutated after creation. `frozen=True` enforces this at the language level. Dataclasses are stdlib, lightweight, and sufficient for simple containers.

**Why Pydantic for user-facing models?** Automatic validation, type coercion, and JSON serialisation. Useful for configuration, validation reports, and inspection results. Pydantic is already a dependency (used in the core), so there's no cost to using it where it adds value.

## Plugin Contracts: ABCs not Protocols

**Decision:** Extension points (Reader, Writer, Renderer, Validator, Inspector) use abstract base classes.

**Why not Protocols?** Protocols (structural typing) are more Pythonic and friendlier for third-party plugins — contributors don't need to import base classes. But ABCs are better for enforcing contracts and providing helpful error messages when methods are missing. For an early-stage project with few third-party plugins, explicitness wins. Protocols can be adopted later if there's community demand.

**Future:** Entry points (`[project.entry-points."crategraph.readers"]`) could allow `pip install crategraph-myformat` to auto-register readers. Not needed until there are actual third-party plugins.

## Query Language: Cypher over SPARQL

**Decision:** Optional Cypher query support via grand-cypher, rather than SPARQL.

**Why?** The target audience is researchers, not RDF specialists. Cypher's pattern-matching syntax (`(a:Person)-[:knows]->(b:Person)`) maps naturally to how people think about graph relationships. SPARQL is more powerful but has a steeper learning curve. The shorthand support (bare patterns auto-wrapped in `MATCH ... RETURN`) lowers the bar further.

**Tradeoff:** Cypher support depends on grand-cypher, which is a smaller community than RDFLib/SPARQL. This is mitigated by making it optional — the Pythonic filtering API (`select`, `where`, `pattern`, `search`) covers most use cases without any extra dependencies.

## Visualisation: Method not Spelling

**Decision:** The method is `visualise()`, using Australian English consistent with the project's spelling conventions.

Three built-in renderers cover different use cases:
- **Pyvis ("2d")** — interactive network exploration in notebooks
- **3d-force-graph ("3d")** — immersive 3D exploration, good for presentations
- **SVG ("svg")** — static output for documents and reproducible figures

The `glimpse()` method provides a one-call type-level overview by merging nodes by type and rendering as SVG.

## Inline Relations: Configurable Edge Extraction

**Decision:** By default, all `@id` references in entity properties become edges in the graph (`inline_relations=True`). This can be turned off or restricted to specific properties.

**Why default to True?** RO-Crates vary widely in how they encode relationships. Some use reified `Relationship` entities, others use inline `@id` references in properties like `author`, `location`, `memberOf`. Extracting all of these produces a richer, more connected graph. Users working with well-structured crates can restrict this.

For planned features and future directions, see [roadmap.md](roadmap.md).
