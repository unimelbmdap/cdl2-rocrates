# Graph Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `crategraph/core/graph.py` (~1160 lines) into focused modules by extracting filtering, transform, and presentation methods into `filtering.py`, `transforms.py`, and `presentation.py`, leaving Graph as a thin facade.

**Architecture:** Follow the existing `analysis.py` pattern — plain functions that receive a `Graph`, with one-liner delegations on the class. Lazy imports inside delegation methods avoid circular imports. No public API changes; all existing tests pass without modification.

**Tech Stack:** Pure Python refactor, no new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-01-graph-decomposition-design.md`

---

## File Structure

### New files

| File | Responsibility |
|------|----------------|
| `crategraph/core/filtering.py` | Narrow the graph: select, where, search, expand, pattern, query |
| `crategraph/core/transforms.py` | Reshape the graph: merge_nodes, simplify, collapse_edges |
| `crategraph/core/presentation.py` | Visualise, layout, and file access: layout, visualise, glimpse, inspect, view |

### Modified files

| File | Change |
|------|--------|
| `crategraph/core/graph.py` | Replace method bodies with thin delegation; remove moved constants and private helpers |

### Unchanged files

All test files — tests call `graph.select()`, `graph.visualise()`, etc. through the public API which is preserved.

---

### Task 1: Create `filtering.py` and move query/selection methods

**Files:**
- Create: `crategraph/core/filtering.py`
- Modify: `crategraph/core/graph.py`

- [ ] **Step 1: Create `crategraph/core/filtering.py`**

```python
"""Filtering and query methods mixed into Graph.

Functions that narrow a graph to a subset of its entities and
relationships: select, where, search, expand, pattern, and Cypher
query. Each returns a new Graph — the original is never mutated.
"""

from __future__ import annotations

import math
import re
from typing import TYPE_CHECKING, Any

from rapidfuzz import fuzz

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity

# --- Temporal constants (used by select's time_range filter) ---

_TEMPORAL_RANGE_PAIRS = (
    ("startDateISOString", "endDateISOString"),
    ("startDate", "endDate"),
)
_TEMPORAL_POINT_KEYS = (
    "datePublished",
    "dateCreated",
    "dateModified",
    "date",
    "year",
)
_YEAR_RE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def select(
    graph: Graph,
    *,
    entity_types: list[str] | None = None,
    relationship_types: list[str] | str | None = None,
    time_range: tuple[int, int] | None = None,
    min_connections: int | None = None,
    max_connections: int | None = None,
    source: str | None = None,
    id: str | None = None,
) -> Graph:
    """Filter by graph structure — type, time, source, connectivity."""
    # Normalise string args to lists.
    if isinstance(relationship_types, str):
        relationship_types = [relationship_types]

    # Validate time_range ordering.
    if time_range is not None and time_range[0] > time_range[1]:
        msg = (
            f"Start of range must be before end — got {time_range}. "
            f"Did you mean ({time_range[1]}, {time_range[0]})?"
        )
        raise ValueError(msg)

    candidates = set(graph._entities.keys())

    # Filter by id.
    if id is not None:
        candidates &= {id} if id in graph._entities else set()

    # Filter by entity type — matches if any of the entity's types are in the list.
    if entity_types is not None:
        type_set = set(entity_types)
        for t in entity_types:
            graph.types.validate(t)
        candidates = {
            eid for eid in candidates if type_set.intersection(graph._entities[eid].types)
        }

    # Filter by source.
    if source is not None:
        candidates = {
            eid
            for eid in candidates
            for src in (graph._entities[eid].source,)
            if src is not None and source in src
        }

    # Filter by direct temporal properties.
    if time_range is not None:
        low, high = time_range
        candidates = {
            eid
            for eid in candidates
            if _entity_matches_time_range(graph._entities[eid], low=low, high=high)
        }

    # Filter by connectivity.
    if min_connections is not None or max_connections is not None:
        filtered: set[str] = set()
        for eid in candidates:
            degree = len(graph._neighbours(eid))
            if min_connections is not None and degree < min_connections:
                continue
            if max_connections is not None and degree > max_connections:
                continue
            filtered.add(eid)
        candidates = filtered

    # Filter by relationship types — keep entities connected by matching rels.
    if relationship_types is not None:
        for t in relationship_types:
            graph.relationship_types.validate(t)
        connected: set[str] = set()
        for rel in graph._relationships:
            if rel.type in relationship_types:
                connected.add(rel.source)
                connected.add(rel.target)
        candidates &= connected

    return graph._subgraph(candidates)


def where(graph: Graph, **kwargs: Any) -> Graph:
    """Filter by entity property values."""
    if not kwargs:
        return graph._subgraph(set(graph._entities.keys()))

    candidates: set[str] = set()
    for eid, entity in graph._entities.items():
        if _entity_matches_where(entity, kwargs):
            candidates.add(eid)
    return graph._subgraph(candidates)


def _entity_matches_where(entity: Entity, filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        value = entity.properties.get(key)
        if value is None:
            return False
        if isinstance(expected, tuple) and len(expected) == 2:
            # Range filter.
            low, high = expected
            try:
                numeric = float(value) if not isinstance(value, (int, float)) else value
                if not (low <= numeric <= high):
                    return False
            except (ValueError, TypeError):
                return False
        elif value != expected:
            return False
    return True


def search(
    graph: Graph,
    query_text: str,
    *,
    properties: list[str] | None = None,
    threshold: int = 60,
) -> Graph:
    """Fuzzy content search across entity properties."""
    candidates: set[str] = set()
    query_lower = query_text.lower()

    for eid, entity in graph._entities.items():
        props = entity.properties
        keys = properties if properties is not None else list(props.keys())
        for key in keys:
            value = props.get(key)
            if value is None:
                continue
            text = str(value)
            score = fuzz.partial_ratio(query_lower, text.lower())
            if score >= threshold:
                candidates.add(eid)
                break

    return graph._subgraph(candidates)


def expand(
    graph: Graph,
    *,
    depth: int = 1,
    entity_types: list[str] | None = None,
    via: str | None = None,
) -> Graph:
    """Grow this selection outward to include connected neighbours."""
    root = graph._root
    current = set(graph._entities.keys())

    # Build adjacency index once: node -> list of neighbour IDs.
    adjacency: dict[str, list[str]] = {}
    for rel in root._relationships:
        if rel.source not in root._entities or rel.target not in root._entities:
            continue
        if via is not None and rel.type != via:
            continue
        adjacency.setdefault(rel.source, []).append(rel.target)
        adjacency.setdefault(rel.target, []).append(rel.source)

    entity_type_set = set(entity_types) if entity_types is not None else None

    for _ in range(depth):
        new_neighbours: set[str] = set()
        for eid in current:
            for candidate in adjacency.get(eid, ()):
                if entity_type_set is not None and not entity_type_set.intersection(
                    root._entities[candidate].types
                ):
                    continue
                new_neighbours.add(candidate)
        current |= new_neighbours

    return root._subgraph(current)


def pattern(
    graph: Graph,
    *,
    from_type: str | None = None,
    via: str | None = None,
    to_type: str | None = None,
) -> Graph:
    """Match relationships by source type, relationship type, and/or target type."""
    # Validate types if provided.
    if from_type is not None:
        graph.types.validate(from_type)
    if to_type is not None:
        graph.types.validate(to_type)
    if via is not None:
        graph.relationship_types.validate(via)

    # No filters -> return full graph.
    if from_type is None and via is None and to_type is None:
        return graph._subgraph(set(graph._entities.keys()))

    matched_ids: set[str] = set()
    for rel in graph._relationships:
        if via is not None and rel.type != via:
            continue

        source_entity = graph._entities.get(rel.source)
        target_entity = graph._entities.get(rel.target)

        if source_entity is None or target_entity is None:
            continue

        if from_type is not None and from_type not in source_entity.types:
            continue

        if to_type is not None and to_type not in target_entity.types:
            continue

        matched_ids.add(rel.source)
        matched_ids.add(rel.target)

    return graph._subgraph(matched_ids)


def query(graph: Graph, cypher: str) -> Graph:
    """Run a Cypher query and return a subgraph of matched entities."""
    from crategraph.core.query import run_cypher

    return run_cypher(graph, cypher)


# --- Temporal helpers ---


def _entity_matches_time_range(entity: Entity, *, low: int, high: int) -> bool:
    props = entity.properties

    for start_key, end_key in _TEMPORAL_RANGE_PAIRS:
        start_year = _extract_year(props.get(start_key))
        end_year = _extract_year(props.get(end_key))
        if start_year is None and end_year is None:
            continue
        if start_year is None:
            start_year = end_year
        if end_year is None:
            end_year = start_year
        if (
            start_year is not None
            and end_year is not None
            and start_year <= high
            and end_year >= low
        ):
            return True

    seen_keys = {key for pair in _TEMPORAL_RANGE_PAIRS for key in pair}
    candidate_keys = list(_TEMPORAL_POINT_KEYS)
    candidate_keys.extend(key for key in props if key not in seen_keys and _looks_temporal_key(key))

    for key in candidate_keys:
        year = _extract_year(props.get(key))
        if year is not None and low <= year <= high:
            return True

    return False


def _looks_temporal_key(key: str) -> bool:
    lowered = key.lower()
    return "date" in lowered or lowered == "year" or lowered.endswith("_year")


def _extract_year(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isfinite(value) and value == int(value):
            return int(value)
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.isdigit():
            return int(stripped)
        match = _YEAR_RE.search(stripped)
        return int(match.group(1)) if match else None
    if isinstance(value, list):
        for item in value:
            year = _extract_year(item)
            if year is not None:
                return year
    return None
```

- [ ] **Step 2: Replace method bodies in `graph.py` with delegations**

In `crategraph/core/graph.py`, remove the section marker `# --- Public query methods ---` and everything from `def select(` through `def _extract_year(` (lines 697-1040). Also remove the class-level constants `_TEMPORAL_RANGE_PAIRS`, `_TEMPORAL_POINT_KEYS`, and `_YEAR_RE` (lines 194-205). Remove `import math`, `import re`, and the `from rapidfuzz import fuzz` import (lines 5, 6, 12) since they're no longer used in graph.py.

Replace with these delegations (insert after the `_coverage` method, before `# --- Layout ---`):

```python
    # --- Filtering methods (delegated to core/filtering.py) ---

    def select(
        self,
        *,
        entity_types: list[str] | None = None,
        relationship_types: list[str] | str | None = None,
        time_range: tuple[int, int] | None = None,
        min_connections: int | None = None,
        max_connections: int | None = None,
        source: str | None = None,
        id: str | None = None,
    ) -> Graph:
        """Filter by graph structure — type, time, source, connectivity."""
        from crategraph.core import filtering

        return filtering.select(
            self,
            entity_types=entity_types,
            relationship_types=relationship_types,
            time_range=time_range,
            min_connections=min_connections,
            max_connections=max_connections,
            source=source,
            id=id,
        )

    def where(self, **kwargs: Any) -> Graph:
        """Filter by entity property values."""
        from crategraph.core import filtering

        return filtering.where(self, **kwargs)

    def search(
        self,
        query: str,
        *,
        properties: list[str] | None = None,
        threshold: int = 60,
    ) -> Graph:
        """Fuzzy content search across entity properties."""
        from crategraph.core import filtering

        return filtering.search(self, query, properties=properties, threshold=threshold)

    def expand(
        self,
        *,
        depth: int = 1,
        entity_types: list[str] | None = None,
        via: str | None = None,
    ) -> Graph:
        """Grow this selection outward to include connected neighbours."""
        from crategraph.core import filtering

        return filtering.expand(self, depth=depth, entity_types=entity_types, via=via)

    def pattern(
        self,
        *,
        from_type: str | None = None,
        via: str | None = None,
        to_type: str | None = None,
    ) -> Graph:
        """Match relationships by source type, relationship type, and/or target type."""
        from crategraph.core import filtering

        return filtering.pattern(self, from_type=from_type, via=via, to_type=to_type)

    def query(self, cypher: str) -> Graph:
        """Run a Cypher query and return a subgraph of matched entities."""
        from crategraph.core import filtering

        return filtering.query(self, cypher)
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -x --ignore=tests/inspectors --ignore=tests/renderers/test_sigma.py --ignore=tests/renderers/test_svg.py`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add crategraph/core/filtering.py crategraph/core/graph.py
git commit -m "refactor: extract filtering methods from Graph into filtering.py"
```

---

### Task 2: Create `transforms.py` and move transform methods

**Files:**
- Create: `crategraph/core/transforms.py`
- Modify: `crategraph/core/graph.py`

- [ ] **Step 1: Create `crategraph/core/transforms.py`**

```python
"""Transform methods mixed into Graph.

Functions that reshape a graph's structure: merging nodes by
property, simplifying by removing low-connectivity nodes, and
collapsing parallel edges. Each returns a new Graph.
"""

from __future__ import annotations

import warnings
from collections import Counter, defaultdict, deque
from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.graph import Graph

from crategraph.core.models import Entity, Relationship


def merge_nodes(graph: Graph, *, by: str) -> Graph:
    """Aggregate nodes by a property, returning a collapsed graph."""
    from crategraph.core.graph import Graph as _Graph

    # Assign each entity to a group.
    groups: dict[str, str] = {}  # entity_id -> group_label
    for eid, entity in graph._entities.items():
        if by == "type":
            groups[eid] = entity.type
        else:
            value = entity.properties.get(by)
            groups[eid] = str(value) if value is not None else "(no value)"

    # Build group nodes.
    merged = _Graph(source=graph.source, metadata=dict(graph.metadata))
    group_counts: Counter[str] = Counter(groups.values())

    for label, count in group_counts.items():
        merged._add_node(
            Entity(
                id=label,
                types=[label] if by == "type" else ["MergedGroup"],
                properties={"label": label, "count": count, "merged_by": by},
            )
        )

    # Build weighted edges between groups, preserving relationship types.
    edge_weights: Counter[tuple[str, str, str]] = Counter()
    for rel in graph._relationships:
        src_group = groups.get(rel.source)
        tgt_group = groups.get(rel.target)
        if src_group is not None and tgt_group is not None and src_group != tgt_group:
            edge_weights[(src_group, tgt_group, rel.type)] += 1

    for (src, tgt, rel_type), weight in edge_weights.items():
        merged._add_edge(
            Relationship(
                source=src,
                target=tgt,
                type=rel_type,
                properties={"weight": weight},
            )
        )

    return merged


def simplify(
    graph: Graph,
    *,
    min_connections: int | None = None,
) -> Graph:
    """Remove peripheral nodes to reveal the structural backbone."""
    prev_k = graph._simplification_k
    if min_connections is not None:
        k = min_connections
    elif prev_k is not None:
        k = prev_k + 1
    else:
        k = 2

    result = _simplify_core(graph, k)

    if len(result) == 0 or len(result) == len(graph):
        warnings.warn(
            f"Graph is fully simplified: all {len(graph)} remaining "
            f"nodes have fewer than {k} connections. "
            f"Returning the current graph.",
            stacklevel=2,
        )
        return graph

    result._simplification_k = k
    return result


def _simplify_core(graph: Graph, min_connections: int) -> Graph:
    """BFS k-core peeling implementation (O(V+E), backend-agnostic)."""
    # Step 1 — initial degrees (unique neighbours, both directions).
    all_ids = set(graph._entities.keys())
    degree: dict[str, int] = {}
    neighbours: dict[str, set[str]] = {}
    for nid in all_ids:
        nbrs = graph._neighbours(nid) & all_ids
        neighbours[nid] = nbrs
        degree[nid] = len(nbrs)

    # Step 2 — BFS peel.
    removed: set[str] = set()
    queue: deque[str] = deque(nid for nid, deg in degree.items() if deg < min_connections)
    while queue:
        nid = queue.popleft()
        if nid in removed:
            continue
        removed.add(nid)
        for nbr in neighbours[nid]:
            if nbr not in removed:
                degree[nbr] -= 1
                if degree[nbr] < min_connections:
                    queue.append(nbr)

    surviving = all_ids - removed

    # Step 3 — annotate survivors with removed-neighbour summary.
    removed_direct: dict[str, dict[str, int]] = {}
    for sid in surviving:
        type_counts: dict[str, int] = {}
        for nbr in neighbours[sid]:
            if nbr in removed:
                entity = graph._entities[nbr]
                primary = entity.types[0] if entity.types else "Unknown"
                type_counts[primary] = type_counts.get(primary, 0) + 1
        removed_direct[sid] = type_counts

    # Step 4 — build new Graph.
    entities: dict[str, Entity] = {}
    for nid in surviving:
        entity = graph._entities[nid]
        annotation = removed_direct[nid]
        if annotation:
            new_props = {**entity.properties, "simplified": annotation}
            entities[nid] = replace(entity, properties=new_props)
        else:
            entities[nid] = entity

    relationships = [
        r for r in graph._relationships if r.source in surviving and r.target in surviving
    ]
    return graph._build_derived_graph(
        node_ids=surviving,
        entities=entities,
        relationships=relationships,
    )


def collapse_edges(graph: Graph) -> Graph:
    """Collapse parallel edges between node pairs into single summary edges."""
    from crategraph.core.graph import Graph as _Graph

    # Group edges by unordered node pair.
    pair_edges: dict[frozenset[str], list[Relationship]] = defaultdict(list)
    for rel in graph._relationships:
        pair_key = frozenset((rel.source, rel.target))
        pair_edges[pair_key].append(rel)

    # Build the new graph with same nodes.
    collapsed = _Graph(
        source=graph.source,
        metadata=dict(graph.metadata),
    )
    for entity in graph._entities.values():
        collapsed._add_node(entity)

    # Collapse each group of edges.
    for _pair_key, edges in pair_edges.items():
        if len(edges) == 1:
            # Single edge — pass through unchanged.
            collapsed._add_edge(edges[0])
            continue

        # Determine directionality.
        directions = {(r.source, r.target) for r in edges}
        bidirectional = len(directions) > 1

        # Canonical source/target ordering.
        if bidirectional:
            source, target = sorted(_pair_key)
        else:
            source, target = edges[0].source, edges[0].target

        # Collect types (sorted, deduplicated).
        types_list = sorted(set(r.type for r in edges))

        # Sum existing weights or count edges.
        total_weight = sum(r.properties.get("weight", 1) for r in edges)

        # Type label.
        type_label = types_list[0] if len(types_list) == 1 else f"{len(edges)} relationships"

        collapsed._add_edge(
            Relationship(
                source=source,
                target=target,
                type=type_label,
                properties={
                    "collapsed": True,
                    "count": len(edges),
                    "types": types_list,
                    "bidirectional": bidirectional,
                    "weight": total_weight,
                },
            )
        )

    return collapsed
```

- [ ] **Step 2: Replace method bodies in `graph.py` with delegations**

Remove the `# --- Transform methods ---` section (from `def detect_communities` through `def collapse_edges`, lines 443-695). Also remove `import warnings` from the top of graph.py if it's no longer used there (check first — `_add_edge` still uses `warnings.warn`).

Replace with these delegations (insert after the filtering delegations):

```python
    # --- Transform methods (delegated to core/transforms.py) ---

    def detect_communities(self, *, resolution: float = 1.0, seed: int | None = None) -> Graph:
        """Return a new graph with a ``"community"`` property on each entity."""
        return analysis_mod.detect_communities_transform(
            self,
            resolution=resolution,
            seed=seed,
        )

    def merge_nodes(self, *, by: str) -> Graph:
        """Aggregate nodes by a property, returning a collapsed graph."""
        from crategraph.core import transforms

        return transforms.merge_nodes(self, by=by)

    def simplify(
        self,
        *,
        min_connections: int | None = None,
    ) -> Graph:
        """Remove peripheral nodes to reveal the structural backbone."""
        from crategraph.core import transforms

        return transforms.simplify(self, min_connections=min_connections)

    def collapse_edges(self) -> Graph:
        """Collapse parallel edges between node pairs into single summary edges."""
        from crategraph.core import transforms

        return transforms.collapse_edges(self)
```

Note: `detect_communities` already delegates to `analysis_mod` — it stays as-is, just moves up next to the other transform delegations.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -x --ignore=tests/inspectors --ignore=tests/renderers/test_sigma.py --ignore=tests/renderers/test_svg.py`
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add crategraph/core/transforms.py crategraph/core/graph.py
git commit -m "refactor: extract transform methods from Graph into transforms.py"
```

---

### Task 3: Create `presentation.py` and move visualisation/file access methods

**Files:**
- Create: `crategraph/core/presentation.py`
- Modify: `crategraph/core/graph.py`

- [ ] **Step 1: Create `crategraph/core/presentation.py`**

```python
"""Visualisation, layout, and file access methods mixed into Graph.

Functions for rendering graphs (2D, 3D, SVG, sigma.js), computing
node positions, and accessing data files referenced by entities.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity, FileInfo, ViewInfo

# Threshold above which the spring_layout fallback is too slow.
_FA2_FALLBACK_LIMIT = 2000


def layout(graph: Graph) -> dict[str, tuple[float, float]]:
    """Compute 2D node positions for visualisation."""
    import networkx as nx

    if not graph._entities:
        return {}

    n = len(graph._entities)
    nx_undirected = graph._graph.to_undirected()

    try:
        from fa2 import ForceAtlas2

        fa2 = ForceAtlas2(
            outboundAttractionDistribution=False,
            barnesHutOptimize=n > 2000,
            barnesHutTheta=0.5,
            scalingRatio=10,
            strongGravityMode=True,
            gravity=0.05,
            verbose=False,
        )
        iters = min(200, 50 + n // 100)
        return fa2.forceatlas2_networkx_layout(nx_undirected, iterations=iters)
    except ImportError:
        pass

    if n > _FA2_FALLBACK_LIMIT:
        msg = (
            f"This graph has {n:,} nodes — the fallback spring layout "
            f"will be extremely slow without the fa2 package.\n"
            f"Install it with: pip install crategraph[fa2]"
        )
        raise ImportError(msg)

    return nx.spring_layout(nx_undirected, seed=42)


def visualise(
    graph: Graph,
    *,
    renderer: str = "2d",
    colour_by: str = "type",
    size_by: str = "connections",
    height: str = "100vh",
    width: str = "100%",
    filepath: str | None = None,
    collapse_edges: bool = False,
    **kwargs: Any,
) -> Any:
    """Render the graph as a network visualisation."""
    from crategraph.core.transforms import collapse_edges as _collapse_edges

    render_graph = _collapse_edges(graph) if collapse_edges else graph

    if renderer == "2d":
        from crategraph.renderers.pyvis import PyvisRenderer

        impl = PyvisRenderer()
    elif renderer == "3d":
        from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer

        impl = ForceGraph3DRenderer()
    elif renderer == "svg":
        from crategraph.renderers.svg import SvgRenderer

        impl = SvgRenderer()
    elif renderer == "sigma":
        from crategraph.renderers.sigma import SigmaRenderer

        impl = SigmaRenderer()
    else:
        msg = (
            f'Unknown renderer "{renderer}". '
            'Choose "2d" (pyvis), "3d" (3d-force-graph), '
            '"svg" (static SVG), or "sigma" (sigma.js WebGL).'
        )
        raise ValueError(msg)

    return impl.render(
        render_graph,
        colour_by=colour_by,
        size_by=size_by,
        height=height,
        width=width,
        filepath=filepath,
        **kwargs,
    )


def glimpse(graph: Graph, *, filepath: str | None = None) -> Any:
    """Inline snapshot of the type-level graph structure."""
    from crategraph.core.analysis import merge_by_primary_type
    from crategraph.renderers.svg import SvgRenderer

    merged = merge_by_primary_type(graph)
    return SvgRenderer().render(
        merged,
        width=600,
        height=450,
        filepath=filepath,
    )


def inspect(graph: Graph, entity: Entity | str) -> FileInfo:
    """Inspect the data file associated with an entity."""
    from crategraph.core.models import FileInfo
    from crategraph.inspectors import find_inspector

    entity = graph._coerce_entity(entity)
    entity_id, file_path = graph._require_local_entity_file(entity, action="inspect")

    # Find an inspector.
    inspector = find_inspector(entity)
    if inspector is None:
        msg = f"Could not inspect {entity_id!r} — format not supported."
        raise ValueError(msg)

    # Inspect and fill in media_type from entity properties.
    info = inspector.inspect(file_path)
    media_type = entity.properties.get("encodingFormat")

    return FileInfo(
        path=info.path,
        content=info.content,
        title=info.title,
        size_bytes=info.size_bytes,
        media_type=media_type if media_type else info.media_type,
    )


def view(graph: Graph, entity: Entity | str) -> ViewInfo:
    """View the data file associated with an entity."""
    from crategraph.core.models import ViewInfo
    from crategraph.viewers import find_viewer

    entity = graph._coerce_entity(entity)
    entity_id, file_path = graph._require_local_entity_file(entity, action="view")

    # Find a viewer.
    viewer = find_viewer(entity)
    if viewer is None:
        msg = f"Could not view {entity_id!r} — format not supported."
        raise ValueError(msg)

    # View and fill in media_type from entity properties if available.
    info = viewer.view(file_path)
    media_type = entity.properties.get("encodingFormat")

    return ViewInfo(
        path=info.path,
        html=info.html,
        title=info.title,
        size_bytes=info.size_bytes,
        media_type=media_type if media_type else info.media_type,
    )
```

- [ ] **Step 2: Replace method bodies in `graph.py` with delegations**

Remove the `# --- Layout ---`, `# --- Visualisation ---`, `# --- Inspection ---`, and `# --- View ---` sections (lines 191-441). Also remove the `_FA2_FALLBACK_LIMIT` class constant (line 193).

Replace with these delegations (insert after the analysis delegations, before the filtering delegations):

```python
    # --- Presentation methods (delegated to core/presentation.py) ---

    def layout(self) -> dict[str, tuple[float, float]]:
        """Compute 2D node positions for visualisation."""
        from crategraph.core import presentation

        return presentation.layout(self)

    def visualise(
        self,
        *,
        renderer: str = "2d",
        colour_by: str = "type",
        size_by: str = "connections",
        height: str = "100vh",
        width: str = "100%",
        filepath: str | None = None,
        collapse_edges: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Render the graph as a network visualisation."""
        from crategraph.core import presentation

        return presentation.visualise(
            self,
            renderer=renderer,
            colour_by=colour_by,
            size_by=size_by,
            height=height,
            width=width,
            filepath=filepath,
            collapse_edges=collapse_edges,
            **kwargs,
        )

    def glimpse(self, *, filepath: str | None = None) -> Any:
        """Inline snapshot of the type-level graph structure."""
        from crategraph.core import presentation

        return presentation.glimpse(self, filepath=filepath)

    def inspect(self, entity: Entity | str) -> FileInfo:
        """Inspect the data file associated with an entity."""
        from crategraph.core import presentation

        return presentation.inspect(self, entity)

    def view(self, entity: Entity | str) -> ViewInfo:
        """View the data file associated with an entity."""
        from crategraph.core import presentation

        return presentation.view(self, entity)
```

- [ ] **Step 3: Clean up `graph.py` imports**

After all three extractions, `graph.py` should no longer need these imports at the top level:
- `import math` — moved to filtering.py
- `import re` — moved to filtering.py
- `from rapidfuzz import fuzz` — moved to filtering.py
- `import networkx as nx` — check if still used (yes, in `_add_node`, `_add_edge`, `_neighbours`, `_build_derived_graph`, `__init__`)
- `from pathlib import Path` — check if still used (yes, in `_require_local_entity_file`)
- `import warnings` — check if still used (yes, in `_add_edge`)

Remove `import math`, `import re`, and `from rapidfuzz import fuzz`. Keep `networkx`, `Path`, and `warnings`.

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -x --ignore=tests/inspectors --ignore=tests/renderers/test_sigma.py --ignore=tests/renderers/test_svg.py`
Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add crategraph/core/presentation.py crategraph/core/graph.py
git commit -m "refactor: extract presentation methods from Graph into presentation.py"
```

---

### Task 4: Final verification

**Files:**
- No changes — verification only.

- [ ] **Step 1: Run ruff lint**

Run: `uv run ruff check crategraph/core/`
Expected: No errors.

- [ ] **Step 2: Run ruff format**

Run: `uv run ruff format crategraph/core/`

- [ ] **Step 3: Verify graph.py line count**

Run: `wc -l crategraph/core/graph.py`
Expected: ~450 lines (down from ~1160).

- [ ] **Step 4: Run full test suite one more time**

Run: `uv run pytest -x --ignore=tests/inspectors --ignore=tests/renderers/test_sigma.py --ignore=tests/renderers/test_svg.py`
Expected: All tests pass, no regressions.

- [ ] **Step 5: Commit any lint fixes**

```bash
git add -u
git commit -m "style: apply ruff formatting to extracted modules"
```
