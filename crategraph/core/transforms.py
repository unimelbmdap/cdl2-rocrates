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

from crategraph.core.models import Entity, Relationship

if TYPE_CHECKING:
    from crategraph.core.graph import Graph


def merge_nodes(graph: Graph, *, by: str) -> Graph:
    """Aggregate nodes by a property, returning a collapsed graph.

    Each unique value of *by* (either entity type via the special
    value ``"type"``, or a property key) becomes one node in the
    result.  Edges between groups are preserved with a ``weight``
    property counting the original edges.

    Args:
        by: ``"type"`` to group by entity type, or a property key
            name (e.g. ``"location"``, ``"decade"``).

    Returns a new ``Graph`` with one node per group and weighted edges.
    """
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


def simplify(graph: Graph, *, min_connections: int | None = None) -> Graph:
    """Remove peripheral nodes to reveal the structural backbone.

    Each call strips away one more layer of weakly-connected nodes
    (k-core peeling).  Chainable: calling ``simplify()`` on an
    already-simplified graph automatically increases the threshold.

    Surviving nodes gain a ``"simplified"`` property -- a dict
    mapping removed-neighbour type to count.

    Args:
        min_connections: Explicit minimum-degree threshold.  When
            omitted the method auto-escalates: first call uses 2,
            subsequent calls increment from the previous level.

    Returns a new ``Graph``, or *graph* if no further
    simplification is possible (with a warning).
    """
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
            stacklevel=3,
        )
        return graph

    result._simplification_k = k
    return result


def _simplify_core(graph: Graph, min_connections: int) -> Graph:
    """BFS k-core peeling implementation (O(V+E), backend-agnostic).

    1. Compute degrees via ``_neighbours()``
    2. BFS-peel nodes below *min_connections*
    3. Annotate survivors with type-counted summary of removed neighbours
    4. Build new ``Graph`` preserving ``_root``
    """
    # Step 1 -- initial degrees (unique neighbours, both directions).
    all_ids = set(graph._entities.keys())
    degree: dict[str, int] = {}
    neighbours: dict[str, set[str]] = {}
    for nid in all_ids:
        nbrs = graph._neighbours(nid) & all_ids
        neighbours[nid] = nbrs
        degree[nid] = len(nbrs)

    # Step 2 -- BFS peel.
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

    # Step 3 -- annotate survivors with removed-neighbour summary.
    removed_direct: dict[str, dict[str, int]] = {}
    for sid in surviving:
        type_counts: dict[str, int] = {}
        for nbr in neighbours[sid]:
            if nbr in removed:
                entity = graph._entities[nbr]
                primary = entity.types[0] if entity.types else "Unknown"
                type_counts[primary] = type_counts.get(primary, 0) + 1
        removed_direct[sid] = type_counts

    # Step 4 -- build new Graph (mirrors _subgraph pattern).
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
    """Collapse parallel edges between node pairs into single summary edges.

    For each pair of nodes, all edges (in either direction) are combined
    into one edge.  The resulting edge carries summary metadata:
    ``count``, ``types`` list, ``bidirectional`` flag, and ``weight``.

    Single edges between a pair pass through unchanged.

    Returns a new ``Graph`` with the same nodes and simplified edges.
    """
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
    for pair_key, edges in pair_edges.items():
        if len(edges) == 1:
            # Single edge -- pass through unchanged.
            collapsed._add_edge(edges[0])
            continue

        # Determine directionality.
        directions = {(r.source, r.target) for r in edges}
        bidirectional = len(directions) > 1

        # Canonical source/target ordering.
        if bidirectional:
            source, target = sorted(pair_key)
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
