# API Design Notes

Early design thinking for the `cdl2-rocrates` Python package API. This document captures brainstorming and is expected to evolve as the design matures.

## Design Principles

- **Immutable results**: Every operation returns a new object. No in-place mutation — avoids the confusion of pandas-style `loc`/`iloc` patterns.
- **Chainable**: Operations can be composed fluently.
- **Consistent types**: `select()` on a crate returns the same type as the crate, so users learn one set of methods.
- **Researcher-friendly vocabulary**: Avoid graph theory jargon (no "subgraph", "ego network", etc. in the public API).
- **Smart defaults**: Visualisations should be readable out of the box, with parameters to adjust.
- **Discoverable vocabulary**: Entity and relationship types are exposed as attributes for IDE autocomplete, with fuzzy validation on string inputs as a safety net.
- **Pluggable architecture**: Readers, writers, visualisation engines, and validators are extensible. RO-Crate support ships built-in but the core is format-agnostic.
- **Escape hatches**: Drop down to NetworkX or export to JSON-LD when needed.

## Backend Architecture

The public API abstracts away the underlying representation — users don't need to know what's underneath. This means the backend can evolve without breaking user-facing code.

### Option A: RDFLib as primary, NetworkX for analysis

- **Parsing**: RDFLib natively parses JSON-LD (the RO-Crate format), ensuring RDF compliance.
- **Querying**: SPARQL is powerful for subgraph extraction and comes free with RDFLib.
- **Scaling**: RDFLib supports pluggable store backends (Oxigraph, Neo4j, Fuseki), providing a path to external graph databases for large collections without changing the API.
- **Concern**: RDFLib is strict about well-formed RDF. Malformed or messy crates (common with legacy cultural databases) may fail at parse time, before the user can even see the data. This is a problem if a key use case is surfacing data quality issues visually.

### Option B: NetworkX as primary, RDFLib for validation/export

- **Parsing**: Parse JSON-LD directly as JSON (it's just JSON with conventions), extract entities and relationships into NetworkX without going through RDF. This means the tool works with messy or non-compliant crates.
- **Querying**: Pythonic filtering via NetworkX. Less powerful than SPARQL for complex graph patterns, but more intuitive for the target audience.
- **Validation**: RDFLib used as an optional, separate step — validate against RDF/schema.org and report issues, but don't block usage. This supports the use case of visualising crates to identify data quality issues.
- **Scaling**: NetworkX is purely in-memory. Handles tens of thousands of nodes/edges comfortably, but has no path to external graph databases. If scale becomes an issue, igraph is a faster in-memory alternative, or the backend would need a larger architectural shift.
- **Dependencies**: RDFLib becomes optional (only needed for validation and RDF export), keeping the core package lightweight.

### Option C: Hybrid approaches

- Parse via RDFLib where possible, fall back to direct JSON-LD parsing for non-compliant crates.
- Use RDFLib for initial parsing but convert immediately to NetworkX, discarding the RDF representation. Keeps RDFLib's parsing capability but avoids its strictness for downstream operations.

### Key Considerations

- **Data quality**: Cultural collections are often converted from legacy databases and may not be fully RDF-compliant. The tool should work with imperfect data, not just valid data.
- **Scale**: How large are the biggest crate collections likely to be? This determines whether the in-memory constraint of NetworkX is a practical limitation.
- **Community expectations**: The RO-Crate community values RDF compliance. Using RDFLib signals alignment with standards.
- **Query complexity**: Whether researchers need SPARQL-level query power, or whether Pythonic filtering with a good API is sufficient.
- **Declarative query languages**: Whether Cypher / GQL add value over Pythonic filtering, given the target audience. Note that Kuzu (an embedded Cypher-compatible graph DB) was archived in October 2025, limiting lightweight options in this space.

## Core API

### Loading a Crate

```python
from rocrate_tools import Crate

crate = Crate("path/to/ro-crate")

# Load multiple crates as a single collection
collection = Crate.load_many(["crate1/", "crate2/", "crate3/"])
```

### Summary — What's in Here?

`summary()` is always available on any object to describe its contents.

```python
crate.summary()
# Entity types:
#   Person          1,247
#   Organisation      384
#   Place             156
#   Event              92
#
# Relationship types:
#   memberOf          823
#   locatedIn         412
#   knows             367
#   attendedEvent     198
#
# Time range: 1832–1901
```

### Type and Relationship Discovery

Entity types and relationship types are exposed as attributes on the crate, enabling IDE autocomplete and reducing typos.

```python
# Attribute access — autocomplete works in notebooks and IDEs
crate.types.Person
crate.types.Organisation
crate.relationships.memberOf

# Assign to short variables for convenience
t = crate.types
r = crate.relationships

result = crate.select(entity_types=[t.Person, t.Organisation])
result = crate.select(relationship_types=[r.memberOf])
```

String inputs are also accepted, with fuzzy validation:

```python
# Strings still work
crate.select(entity_types=["Person"])

# Typos produce helpful errors
crate.select(entity_types=["Persom"])
# ValueError: Unknown entity type "Persom". Did you mean "Person"?
# Available types: Person, Place, Organisation, Event
```

Attributes are generated dynamically from the crate contents, so they always reflect the actual data. Results also expose types and relationships for their subset:

```python
result = crate.select(entity_types=[t.Person, t.Organisation])
result.types            # only types present in this result
result.relationships    # only relationships present in this result
```

### Selecting — Narrowing Down

`select()` returns a new immutable object of the same type. It can be chained.

```python
# Filter by entity type
orgs = crate.select(entity_types=["Organisation"])

# Filter by time range
orgs_1880s = orgs.select(time_range=(1880, 1890))

# Filter by properties (Django ORM-style lookups)
victorians = crate.select(
    entity_types=["Person"],
).select(birth_year__gte=1837, birth_year__lte=1901)

# Include neighbouring nodes
orgs_with_people = crate.select(
    entity_types=["Organisation"],
    include_neighbours=True,
    neighbour_types=["Person"],
)

# Chain fluently
result = (
    crate
    .select(entity_types=["Organisation"])
    .select(time_range=(1880, 1890))
    .select(include_neighbours=True, neighbour_types=["Person"])
)

# Summary works on results too
result.summary()
```

### Branching

Since results are immutable, you can branch from any point:

```python
orgs = crate.select(entity_types=["Organisation"])

orgs_1880s = orgs.select(time_range=(1880, 1890))
orgs_1890s = orgs.select(time_range=(1890, 1900))

orgs_1880s.summary()
orgs_1890s.summary()
```

### Entity Access

```python
# Get a single entity
person = crate.get("entity-id-123")

# Direct connections
person.connections()
person.connections(type="Place")
person.connections(relationship="memberOf")

# Pathfinding
person.path_to(other_entity)
```

### Aggregation

```python
# Most connected entities
result.most_connected(n=10)
result.most_connected(n=10, metric="betweenness")
```

## Visualisation

> **Note on method naming**: `visualise()` is used throughout this document for clarity. The final method name may differ (candidates include `view()`, `plot()`, `show()`) to avoid spelling ambiguity between British/Australian and American English.

### Basic Visualisation

```python
result.visualise()
```

Smart defaults based on graph size to avoid hairball visualisations:
- Small graphs (< ~100 nodes): show everything
- Medium graphs: raise minimum degree threshold automatically
- Large graphs: show top N nodes by degree

A message indicates what's being shown: *"Showing 47 of 1,247 entities (degree >= 5). Adjust with `min_degree` or `max_nodes`."*

### Adjusting the View

```python
result.visualise(min_degree=5)     # only well-connected nodes
result.visualise(min_degree=1)     # show everything
result.visualise(max_nodes=50)     # cap the number of nodes
```

### Grouped / Aggregated View

`group_by` collapses nodes into aggregate groups — useful for seeing the overall shape before drilling in.

```python
# Group by entity type
result.visualise(group_by="type")
# Shows: [Person (1,247)] ---knows(367)--- [Organisation (384)]

# Group by other properties
result.visualise(group_by="location")
# Shows: [Melbourne (423)] ---connected(89)--- [Sydney (312)]

result.visualise(group_by="decade")
# Shows: [1880s (234)] ---connected(56)--- [1890s (412)]
```

### Typical Workflow

1. Start with `group_by` to see the shape
2. `select()` to narrow down
3. `visualise()` without grouping to see detail

```python
# What's the overall shape?
crate.visualise(group_by="type")

# Drill into organisations and their people
result = (
    crate
    .select(entity_types=["Organisation"])
    .select(include_neighbours=True, neighbour_types=["Person"])
    .select(time_range=(1880, 1900))
)

result.visualise()
```

## Plugin Architecture

The package is designed with a pluggable architecture so that the core graph exploration API is format-agnostic. RO-Crate is the first and default implementation, but others can be added through the same interfaces.

### Extension Points

- **Readers** — how to get data in. Each reader converts a source format into the internal graph representation.
- **Writers** — how to get data out. Each writer serialises the graph to a target format.
- **Visualisation engines** — rendering backends. Each engine takes a graph and produces an interactive or static visualisation.
- **Validators** — optional format-specific checks. Each validator reports issues without blocking usage.

### Usage

```python
from graph_explore import Graph
from graph_explore.readers import ROCrateReader, GEXFReader, CSVReader

# Load via a reader (RO-Crate is the default)
graph = Graph.load("path/to/ro-crate", reader=ROCrateReader)
graph = Graph.load("path/to/file.gexf", reader=GEXFReader)

# Or auto-detect from file format
graph = Graph.load("path/to/ro-crate")

# Core API works the same regardless of source
graph.summary()
graph.select(entity_types=[graph.types.Person])
graph.visualise()

# Export via a writer
graph.save("output.json", writer=JSONLDWriter)
graph.save("output.gexf", writer=GEXFWriter)

# Choose a visualisation engine
graph.visualise(engine="gravis")
graph.visualise(engine="pyvis")
graph.visualise(engine="plotly")

# Validate against a format-specific schema
graph.validate(validator=ROCrateValidator)
# Reports issues but does not block usage
```

### Shipped Built-in

- **Readers**: RO-Crate (JSON-LD), GEXF, NetworkX graph objects
- **Writers**: JSON-LD, GEXF, GEFX (Gephi with pre-computed layout)
- **Visualisation engines**: one default (TBD — evaluating gravis, pyvis, and others)
- **Validators**: RO-Crate (RDF/schema.org compliance)

### Why This Matters

The core API (`select`, `summary`, `visualise`, type discovery, fuzzy validation) is useful to anyone working with attributed graphs — digital humanities, social network analysis, biological networks, etc. The RO-Crate layer is the first domain-specific implementation, but the plugin architecture means others can add support for their own formats without modifying the core.

This also makes the project more publishable as a research output: it's a researcher-friendly graph exploration framework, demonstrated with RO-Crate cultural collections.

## Interoperability

### Drop down to NetworkX

```python
G = result.to_networkx()
```

### Export to JSON-LD

```python
result.to_jsonld("output.json")
```

### Export to Gephi

```python
result.to_gephi("output.gexf",
    layout=True,          # pre-compute node positions
    colour_by="type",     # set node colours
    size_by="degree",     # set node sizes
)
```

## Stretch Goals

### Natural Language Query Interface

LLM-driven graph querying — ask a question in plain language, get back a result:

```python
result = crate.ask("Which organisations in Melbourne had the most members in the 1880s?")
result.visualise()
```

This may be simpler to implement over a NetworkX backend (LLM generates Python) than over SPARQL or Cypher.
