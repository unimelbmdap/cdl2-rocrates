"""Analysis methods (summary, most_connected, coverage) mixed into Graph."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import CoverageResult, Entity


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
        lines.append(f"Entities: {self.entity_count} | Relationships: {self.relationship_count}")

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

        return f"<pre style='font-size:13px; line-height:1.4'>{escape(repr(self))}</pre>"


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


def _format_type_rows(counts: dict[str, int], *, top_n: int = 5, max_bar: int = 15) -> list[str]:
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


@dataclass
class GraphProfile:
    """Structural profile of a graph — deeper metrics than GraphSummary.

    Degree is measured as unique neighbour count (not edge count),
    consistent with ``most_connected()``.  Density uses the simple
    directed graph formula n*(n-1) and can exceed 1.0 for multi-edge
    graphs.
    """

    entity_count: int
    relationship_count: int
    density: float
    entity_type_count: int
    relationship_type_count: int
    entity_type_counts: dict[str, int] = field(default_factory=dict)
    relationship_type_counts: dict[str, int] = field(default_factory=dict)
    top_entity_type_fraction: float = 0.0
    data_entity_count: int = 0
    data_entity_fraction: float = 0.0
    component_count: int = 0
    largest_component_fraction: float = 0.0
    max_degree: int = 0
    mean_degree: float = 0.0
    median_degree: float = 0.0
    degree_skewness: float = 0.0
    max_edge_multiplicity: int = 0
    mean_edge_multiplicity: float = 0.0
    self_loop_count: int = 0
    isolate_count: int = 0
    source: str | None = None

    def __repr__(self) -> str:
        lines = ["=== Graph Profile ==="]
        if self.source:
            lines.append(f"Source: {self.source}")
        lines.append(f"Entities: {self.entity_count} | Relationships: {self.relationship_count}")
        lines.append(f"Density: {self.density:.4f}")
        lines.append(
            f"Types: {self.entity_type_count} entity, {self.relationship_type_count} relationship"
        )
        if self.entity_type_counts:
            lines.append("")
            lines.append("Entity types:")
            lines.extend(_format_type_rows(self.entity_type_counts, top_n=5))
        lines.append(
            f"Data entities: {self.data_entity_count} ({self.data_entity_fraction:.0%}) "
            f"| Contextual: {self.entity_count - self.data_entity_count} "
            f"({1 - self.data_entity_fraction:.0%})"
        )
        lines.append("")
        lines.append(
            f"Components: {self.component_count} (largest: {self.largest_component_fraction:.1%})"
        )
        lines.append(
            f"Degree: max={self.max_degree}, mean={self.mean_degree:.1f}, "
            f"median={self.median_degree:.1f}, skew={self.degree_skewness:.2f}"
        )
        lines.append(
            f"Edge multiplicity: max={self.max_edge_multiplicity}, "
            f"mean={self.mean_edge_multiplicity:.1f}"
        )
        lines.append(f"Self-loops: {self.self_loop_count} | Isolates: {self.isolate_count}")
        return "\n".join(lines)

    def _repr_html_(self) -> str:
        from html import escape

        return f"<pre style='font-size:13px; line-height:1.4'>{escape(repr(self))}</pre>"


def profile(graph: Graph) -> GraphProfile:
    """Return a structural profile of the graph."""
    from statistics import median

    import networkx as nx

    n = len(graph._entities)
    m = len(graph._relationships)

    # Density: edges / max possible directed edges.
    max_edges = n * (n - 1) if n > 1 else 0
    density = m / max_edges if max_edges > 0 else 0.0

    # Type distributions.
    entity_type_counter: Counter[str] = Counter()
    for e in graph._entities.values():
        # Count by primary type (first in list) to avoid double-counting
        # multi-typed entities.
        if e.types:
            entity_type_counter[e.types[0]] += 1
    entity_type_counts = dict(entity_type_counter.most_common())
    rel_type_counter: Counter[str] = Counter(r.type for r in graph._relationships)
    rel_type_counts = dict(rel_type_counter.most_common())

    # All unique types (including secondary types from multi-type entities).
    all_entity_types: set[str] = set()
    for e in graph._entities.values():
        all_entity_types.update(e.types)

    # How dominated is the graph by its most common type?
    top_entity_type_fraction = (
        max(entity_type_counter.values()) / n if entity_type_counter else 0.0
    )

    # Data vs contextual entity split.
    data_entity_count = sum(1 for e in graph._entities.values() if e.has_data)
    data_entity_fraction = data_entity_count / n if n > 0 else 0.0

    # Build undirected nx graph for component analysis.
    nx_graph = nx.Graph()
    for eid in graph._entities:
        nx_graph.add_node(eid)
    for rel in graph._relationships:
        if rel.source in graph._entities and rel.target in graph._entities:
            nx_graph.add_edge(rel.source, rel.target)

    # Components.
    if n == 0:
        comp_count = 0
        largest_frac = 0.0
    else:
        components = list(nx.connected_components(nx_graph))
        comp_count = len(components)
        largest_frac = max(len(c) for c in components) / n

    # Degree distribution (unique neighbours, both directions).
    degrees = [len(graph._neighbours(eid)) for eid in graph._entities]
    if degrees:
        max_deg = max(degrees)
        mean_deg = sum(degrees) / len(degrees)
        med_deg = float(median(degrees))
        # Skewness: Fisher-Pearson (avoid scipy dependency).
        if len(degrees) >= 3:
            std = (sum((d - mean_deg) ** 2 for d in degrees) / len(degrees)) ** 0.5
            if std > 0:
                skew = sum((d - mean_deg) ** 3 for d in degrees) / (len(degrees) * std**3)
            else:
                skew = 0.0
        else:
            skew = 0.0
    else:
        max_deg = 0
        mean_deg = 0.0
        med_deg = 0.0
        skew = 0.0

    # Edge multiplicity — count edges per unordered node pair.
    pair_counts: Counter[frozenset[str]] = Counter()
    self_loops = 0
    for rel in graph._relationships:
        if rel.source == rel.target:
            self_loops += 1
        else:
            pair_counts[frozenset((rel.source, rel.target))] += 1

    if pair_counts:
        max_mult = max(pair_counts.values())
        mean_mult = sum(pair_counts.values()) / len(pair_counts)
    else:
        max_mult = 0
        mean_mult = 0.0

    # Isolates.
    isolate_count = sum(1 for d in degrees if d == 0)

    return GraphProfile(
        entity_count=n,
        relationship_count=m,
        density=density,
        entity_type_count=len(all_entity_types),
        relationship_type_count=len(rel_type_counts),
        entity_type_counts=entity_type_counts,
        relationship_type_counts=rel_type_counts,
        top_entity_type_fraction=top_entity_type_fraction,
        data_entity_count=data_entity_count,
        data_entity_fraction=data_entity_fraction,
        component_count=comp_count,
        largest_component_fraction=largest_frac,
        max_degree=max_deg,
        mean_degree=mean_deg,
        median_degree=med_deg,
        degree_skewness=skew,
        max_edge_multiplicity=max_mult,
        mean_edge_multiplicity=mean_mult,
        self_loop_count=self_loops,
        isolate_count=isolate_count,
        source=graph.source,
    )


def coverage(
    graph: Graph,
    *,
    inline_relations: bool | list[str] = False,
    min_occurrences: int = 5,
) -> list[CoverageResult]:
    """Analyse relationship coverage across entity types.

    Discovers structural patterns ``(relationship_type, source_type,
    target_type)`` and measures what fraction of each entity type
    participates.  Partial coverage suggests data quality gaps — entities
    that should be connected but aren't.

    Args:
        inline_relations: Include inline ``@id`` references.
            ``False`` (default) analyses reified relationships only.
            ``True`` includes all inline patterns.
            A list of property names includes only those inline types.
        min_occurrences: Minimum relationship count for a triple to be
            considered a pattern worth reporting.

    Returns a flat list of :class:`CoverageResult` sorted by
    ``fraction`` ascending (worst coverage first).
    """
    from crategraph.core.models import CoveragePattern, CoverageResult

    # Step 1 — Discover patterns: group by (rel_type, src_type, tgt_type, reified).
    pattern_rels = defaultdict(list)
    pattern_sources = defaultdict(set)
    pattern_targets = defaultdict(set)

    for rel in graph._relationships:
        src_entity = graph._entities.get(rel.source)
        tgt_entity = graph._entities.get(rel.target)
        if src_entity is None or tgt_entity is None:
            continue

        src_type = src_entity.types[0] if src_entity.types else "Unknown"
        tgt_type = tgt_entity.types[0] if tgt_entity.types else "Unknown"
        reified = rel.id is not None
        key = (rel.type, src_type, tgt_type, reified)

        pattern_rels[key].append(rel.type)
        pattern_sources[key].add(rel.source)
        pattern_targets[key].add(rel.target)

    # Step 2 — Filter by inline_relations parameter.
    if inline_relations is False:
        # Keep only reified patterns.
        pattern_rels = {k: v for k, v in pattern_rels.items() if k[3]}
    elif isinstance(inline_relations, list):
        # Keep reified + inline patterns whose rel type is in the list.
        allowed = set(inline_relations)
        pattern_rels = {k: v for k, v in pattern_rels.items() if k[3] or k[0] in allowed}
    # inline_relations=True → keep everything.

    # Step 3 — Filter by min_occurrences.
    pattern_rels = {k: v for k, v in pattern_rels.items() if len(v) >= min_occurrences}

    # Step 4 — Measure coverage for each surviving pattern.
    # Pre-compute entity counts by primary type.
    type_counts: Counter[str] = Counter()
    for entity in graph._entities.values():
        primary = entity.types[0] if entity.types else "Unknown"
        type_counts[primary] += 1

    results: list[CoverageResult] = []
    for key in pattern_rels:
        rel_type, src_type, tgt_type, reified = key
        occurrences = len(pattern_rels[key])

        pat = CoveragePattern(
            relationship_type=rel_type,
            source_type=src_type,
            target_type=tgt_type,
            occurrences=occurrences,
            reified=reified,
        )

        # Source side.
        results.append(
            CoverageResult(
                pattern=pat,
                side="source",
                entity_type=src_type,
                reached=len(pattern_sources[key]),
                total=type_counts[src_type],
            )
        )

        # Target side.
        results.append(
            CoverageResult(
                pattern=pat,
                side="target",
                entity_type=tgt_type,
                reached=len(pattern_targets[key]),
                total=type_counts[tgt_type],
            )
        )

    # Step 5 — Sort by fraction ascending (worst coverage first).
    results.sort(key=lambda r: r.fraction)

    return results


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
    nx_graph = nx.Graph()
    for eid in graph._entities:
        nx_graph.add_node(eid)
    for rel in graph._relationships:
        if rel.source in graph._entities and rel.target in graph._entities:
            nx_graph.add_edge(rel.source, rel.target)

    communities = nx.community.louvain_communities(
        nx_graph,
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
