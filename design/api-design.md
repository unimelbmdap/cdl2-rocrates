# API Design

Overview of `crategraph`'s design principles and current API surface. For the rationale behind key architectural decisions, see [decisions.md](decisions.md).

## Design Principles

- **Immutable results**: Every operation returns a new Graph. No in-place mutation.
- **Chainable**: Operations compose fluently — `crate.select(...).where(...).expand(...)`.
- **Consistent types**: Every method that returns a subset returns a `Graph`, so users learn one set of methods.
- **Researcher-friendly vocabulary**: Avoid graph theory jargon in the public API. "Select", "expand", "pattern" instead of "subgraph", "ego network", "motif".
- **Smart defaults**: Visualisations are readable out of the box.
- **Discoverable vocabulary**: Entity and relationship types are exposed as attributes (`crate.types.Person`) with fuzzy validation on string inputs.
- **Pluggable architecture**: Readers, writers, renderers, validators, and inspectors are all extensible via ABCs. RO-Crate ships built-in but the core is format-agnostic.
- **Escape hatches**: The underlying NetworkX graph is accessible when needed.

## Architecture

The core uses **NetworkX** (`nx.MultiDiGraph`) directly for graph storage and traversal. See [decisions.md](decisions.md) for the reasoning.

```
crategraph/
├── core/           # Graph class, data models, query, analysis, corpus
│   ├── graph.py       # Graph class — public facade, state, and plumbing
│   ├── filtering.py   # select, where, search, expand, pattern, query
│   ├── transforms.py  # merge_nodes, simplify, collapse_edges
│   ├── presentation.py # layout, visualise, glimpse, inspect, view
│   ├── analysis.py    # summary, most_connected, profile, detect_communities
│   ├── models.py      # Entity, Relationship, FileInfo, ViewInfo, validation models
│   ├── types.py       # TypeRegistry (fuzzy type discovery)
│   ├── corpus.py      # Corpus (batch profiling across multiple crates)
│   ├── query.py       # Cypher query support (via grand-cypher)
│   ├── _files.py      # Entity file path resolution helpers
│   ├── interfaces.py  # ABCs: Reader, Writer, Renderer, Validator, Inspector, Viewer
├── readers/        # ROCrateReader, OHRMCsvReader, OHRMSqlReader
│   └── shared/     # TabularGraphReader, CsvGraphReader, SqlGraphReader
├── renderers/      # Pyvis (2D), ForceGraph3D (3D), SVG (static), Sigma (WebGL)
├── inspectors/     # MarkItDown file inspector
├── viewers/        # Rich file previews (DefaultViewer)
├── validators/     # (planned)
└── writers/        # GraphML, CSV (RDF, RO-Crate planned)
```

## Core API

### Loading

```python
from crategraph import Crate

# Single crate — root Dataset excluded by default, its properties
# promoted to crate.metadata["name"], crate.metadata["description"], etc.
crate = Crate("path/to/ro-crate")

# Multiple crates merged into one graph
crate = Crate("crate1/", "crate2/", "crate3/")

# Include the root Dataset entity as a graph node
crate = Crate("path/", include_root=True)

# Control which inline @id references become edges
crate = Crate("path/", inline_relations=True)         # all (default)
crate = Crate("path/", inline_relations=False)         # only reified Relationships
crate = Crate("path/", inline_relations=["author"])    # only these properties
```

### Summary

```python
crate.summary()
# === Graph Summary ===
# Source: path/to/ro-crate
# Entities: 1,879 | Relationships: 1,800
#
# Entity types:
#   Person          1,247  ████████████████
#   Organisation      384  █████
#   Place             156  ██
#   Event              92  █

crate.most_connected(n=5)
# [(Entity("org-42", ...), 128), (Entity("person-7", ...), 94), ...]
```

### Type and Relationship Discovery

```python
# Attribute access with IDE autocomplete
crate.types.Person           # → "Person"
crate.relationship_types.author  # → "author"

# Fuzzy validation catches typos
crate.select(entity_types=["Persom"])
# ValueError: Unknown type "Persom". Did you mean "Person"?

# Types narrow to what's in the current result
people = crate.select(entity_types=["Person"])
people.types  # only types present in this subset
```

### Filtering

All filtering methods return a new `Graph` and can be chained.

```python
# select() — structural/type filtering
orgs = crate.select(entity_types=["Organisation"])
orgs_from_source = crate.select(source="crate1")
well_connected = crate.select(min_connections=5)

# where() — property value filtering
victorians = crate.where(birth_year=(1837, 1901))   # range
melbourne = crate.where(location="Melbourne")         # exact match

# search() — fuzzy text search across properties
results = crate.search("Melbourne", threshold=60)
results = crate.search("botany", properties=["description"])

# pattern() — match relationship patterns
authored = crate.pattern(from_type="Person", via="author", to_type="CreativeWork")

# expand() — grow outward from current selection
neighbourhood = people.expand(depth=2, entity_types=["Organisation"])

# query() — Cypher queries (via grand-cypher)
result = crate.query("MATCH (p:Person)-[:author]->(w) RETURN p, w")
result = crate.query("(:Person)-[:knows]->(:Person)")  # shorthand
```

### Branching

Since results are immutable, branching is natural:

```python
orgs = crate.select(entity_types=["Organisation"])

by_source_a = orgs.select(source="crate-a")
by_source_b = orgs.select(source="crate-b")
```

### Transforms

Transforms return new graphs with modified structure.

```python
# Merge nodes by type (or any property)
merged = crate.merge_nodes(by="type")
# Nodes become: "Person (1,247)", "Organisation (384)", ...

# Collapse parallel edges into weighted summary edges
collapsed = crate.collapse_edges()

# Community detection (Louvain algorithm)
communities = crate.detect_communities(resolution=1.0, seed=42)
# Each entity gains a "community" property
```

### Writers / Export

`graph.write(path, *, format, overwrite=False, **kwargs)` is the single entry point for all export formats. `format` is a required keyword argument. Passing an unrecognised format raises `UnknownFormatError` (a `ValueError` subclass). `overwrite` defaults to `False`; each writer raises `FileExistsError` when the target already exists and `overwrite` is not set.

Path semantics are writer-specific: `"graphml"` expects a file path, while `"csv"` expects a directory (created if absent).

`graph.to_networkx(copy=True)` returns the underlying `nx.MultiDiGraph`. With `copy=True` (default), the return value is a fully detached deep copy — safe to mutate. With `copy=False`, the internal graph is returned directly; the caller must not mutate it.

```python
# Export to GraphML for Gephi / yEd
crate.write("crate.graphml", format="graphml")

# Overwrite an existing file
crate.write("crate.graphml", format="graphml", overwrite=True)

# Export to CSV (nodes.csv + edges.csv written into the directory)
crate.write("crate_tables/", format="csv")

# Drop down to NetworkX for custom analysis
G = crate.to_networkx()

# Bypass the copy for read-only algorithms (no mutation guarantee)
G_direct = crate.to_networkx(copy=False)
```

See [docs/writers.md](../docs/writers.md) for attribute-flattening rules, format-specific notes, and how to register a custom writer.

### Visualisation

```python
# Interactive 2D network (pyvis)
crate.visualise()
crate.visualise(renderer="2d", colour_by="type", size_by="connections")

# Interactive 3D (3d-force-graph / Three.js)
crate.visualise(renderer="3d")

# Static SVG
crate.visualise(renderer="svg", width=800, height=600)

# Save to file
crate.visualise(filepath="output.html")

# Quick type-level snapshot (merge + SVG)
crate.glimpse()
crate.glimpse(filepath="overview.svg")
```

### File Inspection

Preview files referenced by data entities (requires `crategraph[inspect]`).

```python
info = crate.inspect("sample.csv")
# FileInfo(path='...sample.csv', media_type='text/csv', size_bytes=1234, ...)
print(info.content)  # markdown conversion of file contents
```

## Data Models

**Internal (frozen dataclasses):**

```python
@dataclass(frozen=True)
class Entity:
    id: str
    types: list[str]                     # e.g. ["Person", "Agent"]
    properties: dict[str, Any]
    source: str | None = None            # crate directory path

@dataclass(frozen=True)
class Relationship:
    source: str                          # source entity ID
    target: str                          # target entity ID
    type: str                            # relationship type
    properties: dict[str, Any]
    id: str | None = None                # set if reified

@dataclass(frozen=True)
class FileInfo:                          # inspect() result
    path: str
    content: str
    title: str | None
    size_bytes: int
    media_type: str | None

@dataclass(frozen=True)
class ViewInfo:                          # view() result
    path: str
    html: str
    title: str | None
    size_bytes: int
    media_type: str | None
```

**User-facing (Pydantic):**

- `ValidationIssue` — severity + message + entity_id
- `ValidationReport` — list of issues with `.is_valid` property
- `SelectOptions` — parameters for structural filtering via `Graph.select()`

## Plugin Interfaces

All extension points use abstract base classes defined in `crategraph.core.interfaces`:

| Interface   | Methods                              | Implementations                            |
|-------------|--------------------------------------|--------------------------------------------|
| `Reader`    | `can_read(path)`, `read(path)`       | ROCrateReader, OHRMCsvReader, OHRMSqlReader |
| `Writer`    | `can_write(path)`, `write(graph, path)` | GraphMLWriter, CsvWriter                |
| `Renderer`  | `render(graph, **kwargs)`            | Pyvis, ForceGraph3D, SVG, Sigma            |
| `Validator` | `validate(graph)` → ValidationReport | (planned)                                  |
| `Inspector` | `supports(entity)`, `inspect(path)`  | MarkItDownInspector                        |
| `Viewer`    | `supports(entity)`, `view(path)`     | DefaultViewer                              |

## Optional Dependencies

| Extra       | Package          | Unlocks                          |
|-------------|------------------|----------------------------------|
| `rdf`       | rdflib           | RDF/schema.org validation (planned) |
| `inspect`   | markitdown[all]  | File content inspection          |
| `ohrm`      | pandas           | OHRM CSV/SQL readers, Corpus DataFrames |
