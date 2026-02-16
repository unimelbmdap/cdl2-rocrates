# API Design Notes

Early design thinking for the `cdl2-rocrates` Python package API. This document captures brainstorming and is expected to evolve as the design matures.

## Design Principles

- **Immutable results**: Every operation returns a new object. No in-place mutation — avoids the confusion of pandas-style `loc`/`iloc` patterns.
- **Chainable**: Operations can be composed fluently.
- **Consistent types**: `select()` on a crate returns the same type as the crate, so users learn one set of methods.
- **Researcher-friendly vocabulary**: Avoid graph theory jargon (no "subgraph", "ego network", etc. in the public API).
- **Smart defaults**: Visualisations should be readable out of the box, with parameters to adjust.
- **Discoverable vocabulary**: Entity and relationship types are exposed as attributes for IDE autocomplete, with fuzzy validation on string inputs as a safety net.
- **Escape hatches**: Drop down to NetworkX or export to JSON-LD when needed.

## Backend Architecture

- **RDFLib** for parsing JSON-LD to ensure RO-Crate compliance.
- **NetworkX** (or potentially an alternative graph engine) for internal representation, querying, and analysis.
- The public API abstracts away the underlying representation — users don't need to know what's underneath.

### Open Questions

- Whether to keep RDFLib as the primary representation with NetworkX for analysis, or parse via RDFLib and convert to NetworkX as the primary store.
- Whether declarative query languages (Cypher / GQL) add value over Pythonic filtering, given the target audience.

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

## Interoperability

### Drop down to NetworkX

```python
G = result.to_networkx()
```

### Export to JSON-LD

```python
result.to_jsonld("output.json")
```

## Stretch Goals

### Natural Language Query Interface

LLM-driven graph querying — ask a question in plain language, get back a result:

```python
result = crate.ask("Which organisations in Melbourne had the most members in the 1880s?")
result.visualise()
```

This may be simpler to implement over a NetworkX backend (LLM generates Python) than over SPARQL or Cypher.
