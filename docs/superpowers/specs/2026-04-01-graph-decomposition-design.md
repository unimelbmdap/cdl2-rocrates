# Graph Decomposition Design

**Date:** 2026-04-01
**Status:** Approved

## Summary

Split `crategraph/core/graph.py` (~1160 lines) into four focused modules
by extracting method implementations into `filtering.py`, `transforms.py`,
and `presentation.py`. Graph remains the public facade with thin
delegation methods. No public API changes.

## Motivation

`graph.py` has grown to ~1160 lines mixing state management, filtering,
transforms, visualisation, and file access. Individual methods are hard
to find and reason about in context. The project already demonstrates the
target pattern — `analysis.py` and `query.py` hold plain functions that
receive a `Graph`, with one-liner delegations on the class.

## Design

### New modules

#### `crategraph/core/filtering.py` (~300 lines)

```python
"""Filtering and query methods mixed into Graph.

Functions that narrow a graph to a subset of its entities and
relationships: select, where, search, expand, pattern, and Cypher
query. Each returns a new Graph — the original is never mutated.
"""
```

**Functions moved:**

| Function | Current location |
|----------|-----------------|
| `select(graph, ...)` | `graph.py:699-783` |
| `where(graph, ...)` | `graph.py:785-800` |
| `_entity_matches_where(entity, filters)` | `graph.py:802-818` |
| `search(graph, ...)` | `graph.py:820-853` |
| `expand(graph, ...)` | `graph.py:855-906` |
| `pattern(graph, ...)` | `graph.py:905-956` |
| `query(graph, cypher)` | `graph.py:958-977` (delegates to `query.py`) |
| `_entity_matches_time_range(entity, ...)` | `graph.py:979-1011` |
| `_looks_temporal_key(key)` | `graph.py:1013-1016` |
| `_extract_year(value)` | `graph.py:1018-1040` |

**Module-level constants moved from Graph class:**

- `_TEMPORAL_RANGE_PAIRS`
- `_TEMPORAL_POINT_KEYS`
- `_YEAR_RE`

#### `crategraph/core/transforms.py` (~200 lines)

```python
"""Transform methods mixed into Graph.

Functions that reshape a graph's structure: merging nodes by
property, simplifying by removing low-connectivity nodes, and
collapsing parallel edges. Each returns a new Graph.
"""
```

**Functions moved:**

| Function | Current location |
|----------|-----------------|
| `merge_nodes(graph, ...)` | `graph.py:456-512` |
| `simplify(graph, ...)` | `graph.py:514-558` |
| `_simplify_core(graph, min_connections)` | `graph.py:560-625` |
| `collapse_edges(graph)` | `graph.py:627-695` |

#### `crategraph/core/presentation.py` (~200 lines)

```python
"""Visualisation, layout, and file access methods mixed into Graph.

Functions for rendering graphs (2D, 3D, SVG, sigma.js), computing
node positions, and accessing data files referenced by entities.
"""
```

**Functions moved:**

| Function | Current location |
|----------|-----------------|
| `layout(graph)` | `graph.py:207-259` |
| `visualise(graph, ...)` | `graph.py:263-329` |
| `glimpse(graph, ...)` | `graph.py:331-355` |
| `inspect(graph, entity)` | `graph.py:359-399` |
| `view(graph, entity)` | `graph.py:403-441` |

**Constants moved from Graph class:**

- `_FA2_FALLBACK_LIMIT`

### What stays in `graph.py` (~450 lines)

- Constructor (`__init__`)
- Read-only properties: `types`, `relationship_types`, `entities`,
  `relationships`, `files`, `sources`, `__len__`
- Display: `__repr__`, `_repr_html_`
- Lookup: `get()`
- Analysis delegation (already one-liners to `analysis.py`)
- All private plumbing:
  - `_add_node`, `_add_edge`
  - `_neighbours`, `_display_name`
  - `_subgraph`, `_build_derived_graph`
  - `_coerce_entity`, `_require_local_entity_file`

### Delegation pattern

Each public method on `Graph` becomes a thin wrapper:

```python
def select(
    self,
    *,
    entity_types: list[str] | None = None,
    relationship_types: list[str] | None = None,
    time_range: tuple[int, int] | None = None,
    min_connections: int | None = None,
    max_connections: int | None = None,
    source: str | None = None,
    id: str | None = None,
) -> Graph:
    from crategraph.core.filtering import select
    return select(self, entity_types=entity_types, ...)
```

Lazy imports inside each method (matching the existing `analysis.py`
pattern) to avoid circular imports.

### Extracted function signatures

Functions receive `graph: Graph` as the first argument and access
internals via `graph._entities`, `graph._relationships`,
`graph._subgraph()`, etc. This is the same private access pattern
that `analysis.py` already uses.

Functions that were instance methods referencing `self` become plain
functions with `graph` as the first parameter. Class methods like
`_looks_temporal_key` and `_extract_year` become module-level functions.

### Files unchanged

- `crategraph/core/query.py` — stays as-is; `filtering.py` calls
  `run_cypher()` from it, same as `graph.py` does today.
- `crategraph/core/analysis.py` — unchanged.
- All test files — unchanged. Tests call `graph.select()`,
  `graph.expand()`, etc. through the public API, which is preserved.

### Import considerations

The extracted modules import `Graph` for type annotations only
(`TYPE_CHECKING`). `Graph` imports the extracted modules lazily inside
delegation methods. This avoids circular imports — the same pattern
used by `analysis.py` today.

## Risks

- **Private API coupling:** The extracted functions access `Graph`
  internals (`_entities`, `_relationships`, `_subgraph`). This is
  already the case for `analysis.py` — it's an accepted pattern in
  this codebase, not a new risk.
- **Method resolution:** Someone reading `graph.select()` must follow
  the delegation to `filtering.select()`. This is already the case
  for `graph.summary()` → `analysis.summary()`. Consistent use of the
  pattern makes it predictable.

## Success criteria

- `graph.py` drops to ~450 lines
- No public API changes — all existing tests pass without modification
- Each new module has a clear docstring explaining its purpose
- `ruff check` and `ruff format` pass
