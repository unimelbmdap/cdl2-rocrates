"""Analysis methods (summary, most_connected) mixed into Graph."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity


@dataclass
class GraphSummary:
    """Result of ``Graph.summary()`` — structured overview of a graph."""

    entity_count: int
    relationship_count: int
    entity_type_counts: dict[str, int] = field(default_factory=dict)
    relationship_type_counts: dict[str, int] = field(default_factory=dict)
    source: str | None = None
    sources: list[str] = field(default_factory=list)
    most_connected: list[tuple[str, int]] = field(default_factory=list)

    def __repr__(self) -> str:
        lines = ["=== Graph Summary ==="]
        if len(self.sources) > 1:
            lines.append(f"Sources: {', '.join(self.sources)}")
        elif self.source:
            lines.append(f"Source: {self.source}")
        lines.append(
            f"Entities: {self.entity_count} | Relationships: {self.relationship_count}"
        )

        if self.entity_type_counts:
            lines.append("")
            lines.append("Entity types:")
            lines.extend(_format_type_rows(self.entity_type_counts, top_n=5))

        if self.relationship_type_counts:
            lines.append("")
            lines.append("Relationship types:")
            lines.extend(_format_type_rows(self.relationship_type_counts, top_n=5))

        if self.most_connected:
            lines.append("")
            parts = [f"{name} ({degree})" for name, degree in self.most_connected]
            lines.append(f"Most connected: {', '.join(parts)}")

        return "\n".join(lines)

    def _repr_html_(self) -> str:
        """Compact HTML representation — same content as __repr__ in a pre block."""
        from html import escape

        return (
            f"<pre style='font-size:13px; line-height:1.4'>{escape(repr(self))}</pre>"
        )


def summary(graph: Graph) -> GraphSummary:
    """Return a structured summary of the graph."""
    top = most_connected(graph, n=3)
    return GraphSummary(
        entity_count=len(graph._entities),
        relationship_count=len(graph._relationships),
        entity_type_counts=dict(Counter(e.type for e in graph._entities.values())),
        relationship_type_counts=dict(Counter(r.type for r in graph._relationships)),
        source=graph.source,
        sources=graph.sources,
        most_connected=[(entity.name, degree) for entity, degree in top],
    )


def most_connected(
    graph: Graph,
    *,
    n: int = 10,
    entity_types: list[str] | None = None,
) -> list[tuple[Entity, int]]:
    """Return the top *n* entities by number of connections (degree).

    Args:
        n: Maximum number of results.
        entity_types: Only include entities matching these types.
            Degree is still computed from the full graph.

    Returns a list of ``(entity, degree)`` tuples sorted by degree
    descending.
    """
    type_set = set(entity_types) if entity_types is not None else None
    degrees: list[tuple[Entity, int]] = []
    for eid, entity in graph._entities.items():
        if type_set is not None and not type_set.intersection(entity.types):
            continue
        degree = len(graph._neighbours(eid))
        degrees.append((entity, degree))
    degrees.sort(key=lambda x: x[1], reverse=True)
    return degrees[:n]


def _format_type_rows(
    counts: dict[str, int], *, top_n: int = 5, max_bar: int = 15
) -> list[str]:
    """Format type counts as aligned rows with Unicode sparkline bars."""
    sorted_items = sorted(counts.items(), key=lambda x: -x[1])
    top = sorted_items[:top_n]
    remaining = len(sorted_items) - top_n

    if not top:
        return []

    max_count = top[0][1]
    name_width = max(len(name) for name, _ in top)
    count_width = max(len(str(c)) for _, c in top)

    rows: list[str] = []
    for name, count in top:
        bar_len = round(count / max_count * max_bar) if max_count > 0 else 0
        bar = "\u2592" * bar_len
        rows.append(f"  {name:<{name_width}}  {count:>{count_width}}  {bar}")

    if remaining > 0:
        rows.append(f"  +{remaining} more")

    return rows


def detect_communities(
    graph: Graph,
    *,
    resolution: float = 1.0,
    seed: int | None = None,
) -> dict[str, int]:
    """Partition entities into communities using the Louvain algorithm.

    Uses ``networkx.algorithms.community.louvain_communities()``.

    Args:
        resolution: Louvain resolution — higher produces more, smaller
            communities.  Lower produces fewer, larger communities.
        seed: Random seed for reproducible results.

    Returns a mapping of entity ID to community index (``int``).
    """
    import networkx as nx

    if not graph._entities:
        return {}

    # Build an undirected NetworkX graph for community detection.
    G = nx.Graph()
    for eid in graph._entities:
        G.add_node(eid)
    for rel in graph._relationships:
        if rel.source in graph._entities and rel.target in graph._entities:
            G.add_edge(rel.source, rel.target)

    communities = nx.community.louvain_communities(
        G,
        resolution=resolution,
        seed=seed,
    )

    partition: dict[str, int] = {}
    for idx, community in enumerate(communities):
        for node_id in community:
            partition[node_id] = idx

    return partition


def detect_communities_transform(
    graph: Graph,
    *,
    resolution: float = 1.0,
    seed: int | None = None,
) -> Graph:
    """Return a new graph with a ``"community"`` property on each entity.

    Uses :func:`detect_communities` internally — this is the transform
    variant exposed as ``Graph.detect_communities()``.
    """
    from dataclasses import replace

    from crategraph.core.graph import Graph as _Graph

    partition = detect_communities(graph, resolution=resolution, seed=seed)
    new_graph = _Graph(source=graph.source, metadata=dict(graph.metadata))
    for eid, entity in graph._entities.items():
        new_props = {**entity.properties, "community": partition.get(eid, 0)}
        new_graph._add_node(replace(entity, properties=new_props))
    for rel in graph._relationships:
        new_graph._add_edge(rel)
    return new_graph


def merge_by_primary_type(graph: Graph) -> Graph:
    """Merge entities by their primary type (``types[0]``).

    Returns a new ``Graph`` with one node per primary type and weighted
    edges between groups.  Similar to ``merge_nodes(by="type")`` but
    collapses multi-type entities by their first type only.
    """
    from crategraph.core.graph import Graph as _Graph
    from crategraph.core.models import Entity, Relationship

    if not graph._entities:
        return _Graph()

    # Assign each entity to its primary type group.
    groups: dict[str, str] = {}
    for eid, entity in graph._entities.items():
        groups[eid] = entity.types[0] if entity.types else "Unknown"

    # Build group nodes.
    merged = _Graph(source=graph.source, metadata=dict(graph.metadata))
    group_counts: Counter[str] = Counter(groups.values())

    for label, count in group_counts.items():
        merged._add_node(
            Entity(
                id=label,
                types=[label],
                properties={"label": label, "count": count},
            )
        )

    # Build weighted edges between groups (no self-loops).
    edge_weights: Counter[tuple[str, str]] = Counter()
    for rel in graph._relationships:
        src_group = groups.get(rel.source)
        tgt_group = groups.get(rel.target)
        if src_group is not None and tgt_group is not None and src_group != tgt_group:
            edge_weights[(src_group, tgt_group)] += 1

    for (src, tgt), weight in edge_weights.items():
        merged._add_edge(
            Relationship(
                source=src,
                target=tgt,
                type="merged",
                properties={"weight": weight},
            )
        )

    return merged
