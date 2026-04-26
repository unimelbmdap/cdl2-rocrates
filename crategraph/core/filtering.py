"""Filtering and query methods mixed into Graph.

Functions that narrow a graph to a subset of its entities and
relationships: select, exclude, where, search, expand, pattern, and Cypher
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

# ---------------------------------------------------------------------------
# Module-level constants (moved from Graph class)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Public filtering functions
# ---------------------------------------------------------------------------


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
    """Filter by graph structure — type, time, source, connectivity.

    Returns a new ``Graph`` containing only the matching entities and
    their mutual relationships.
    """
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
            if (src := graph._entities[eid].source) is not None and source in src
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


def exclude(
    graph: Graph,
    *,
    entity_types: list[str] | str | None = None,
    relationship_types: list[str] | str | None = None,
    drop_isolated: bool = True,
) -> Graph:
    """Filter out matching entities and relationships.

    Args:
        entity_types: Entity type, or types, to remove.
        relationship_types: Relationship type, or types, to remove.
        drop_isolated: If ``True`` (default), remove entities that become
            isolated as a result of the exclusion. Entities that were already
            isolated are preserved unless they directly match ``entity_types``.
            Unknown entity or relationship types raise ``ValueError``, matching
            ``select()``.

    Returns a new ``Graph`` containing the remaining entities and their mutual
    relationships. Like ``select()``, the returned graph preserves the original
    expansion root, so later ``expand()`` calls may widen the result again.
    """
    if isinstance(entity_types, str):
        entity_types = [entity_types]
    if isinstance(relationship_types, str):
        relationship_types = [relationship_types]

    node_ids = set(graph._entities.keys())

    if entity_types is not None:
        excluded_entity_types = set(entity_types)
        for entity_type in excluded_entity_types:
            graph.types.validate(entity_type)
        node_ids = {
            entity_id
            for entity_id in node_ids
            if not excluded_entity_types.intersection(graph._entities[entity_id].types)
        }

    if relationship_types is not None:
        excluded_relationship_types = set(relationship_types)
        for relationship_type in excluded_relationship_types:
            graph.relationship_types.validate(relationship_type)
    else:
        excluded_relationship_types = set()

    relationships = [
        relationship
        for relationship in graph._relationships
        if relationship.source in node_ids
        and relationship.target in node_ids
        and relationship.type not in excluded_relationship_types
    ]

    if drop_isolated:
        before_isolated = {
            entity_id for entity_id in graph._entities if not graph._neighbours(entity_id)
        }
        connected_after = {
            entity_id
            for relationship in relationships
            for entity_id in (relationship.source, relationship.target)
        }
        became_isolated = node_ids - connected_after - before_isolated
        node_ids -= became_isolated

    return graph._build_derived_graph(node_ids=node_ids, relationships=relationships)


def where(graph: Graph, **kwargs: Any) -> Graph:
    """Filter by entity property values.

    Scalar values are matched exactly.  Tuple ``(low, high)`` values
    match entities whose property falls within the inclusive range.

    Returns a new ``Graph`` containing only the matching entities.
    """
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


_SEARCH_TOP_N = 10


def search(
    graph: Graph,
    query_text: str,
    *,
    properties: list[str] | None = None,
    threshold: int = 80,
    top_n: int = _SEARCH_TOP_N,
) -> Graph:
    """Fuzzy content search across entity properties.

    Args:
        query_text: The search term.
        properties: Limit search to these property keys (default: all).
        threshold: Minimum match score 0-100 (default 80).
        top_n: Print this many top hits to stdout (default 10).
            Set to 0 to suppress output.

    Returns a new ``Graph`` containing matching entities and their
    mutual relationships.  Also prints the top hits so results are
    visible even without inspecting the returned graph.
    """
    hits: list[tuple[float, str, str, str]] = []  # (score, eid, key, snippet)
    query_lower = query_text.lower()

    for eid, entity in graph._entities.items():
        props = entity.properties
        keys = properties if properties is not None else list(props.keys())
        best_score = 0
        best_key = ""
        best_text = ""
        for key in keys:
            value = props.get(key)
            if value is None:
                continue
            text = str(value)
            text_lower = text.lower()
            # token_set_ratio handles multi-word matching well;
            # partial_ratio finds the query as a substring of the value
            # but is only safe when value >= query (otherwise short values
            # like "F" score 100 against any query containing that letter).
            ts = fuzz.token_set_ratio(query_lower, text_lower)
            pr = (
                fuzz.partial_ratio(query_lower, text_lower)
                if len(text_lower) >= len(query_lower)
                else 0
            )
            score = max(ts, pr)
            if score > best_score:
                best_score = score
                best_key = key
                best_text = text
        if best_score >= threshold:
            snippet = best_text if len(best_text) <= 80 else best_text[:77] + "..."
            hits.append((best_score, eid, best_key, snippet))

    hits.sort(key=lambda h: (-h[0], h[1]))

    if top_n > 0 and hits:
        print(f'Found {len(hits)} match(es) for "{query_text}":\n')
        for score, eid, key, snippet in hits[:top_n]:
            print(f"  {score:3.0f}  {eid}  ({key}: {snippet})")
        if len(hits) > top_n:
            print(f"  ... and {len(hits) - top_n} more")

    candidates = {eid for _, eid, _, _ in hits}
    return graph._subgraph(candidates)


def expand(
    graph: Graph,
    *,
    depth: int = 1,
    entity_types: list[str] | None = None,
    via: str | None = None,
) -> Graph:
    """Grow this selection outward to include connected neighbours.

    Reaches into the root graph to find neighbours beyond the current
    subgraph — so ``crate.select(...).expand()`` discovers entities
    not in the initial selection.

    Args:
        depth: Number of hops outward (default 1).
        entity_types: Only include neighbours of these types.
        via: Only follow relationships of this type.

    Returns a new ``Graph`` (rooted at the same root) containing the
    original entities plus their neighbours.
    """

    root = graph._root
    current = set(graph._entities.keys())

    # Build adjacency index once: node → list of neighbour IDs.
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
    """Match relationships by source type, relationship type, and/or target type.

    Returns a subgraph containing all matched source and target entities
    and the relationships between them.

    Args:
        from_type: Only include relationships from entities of this type.
        via: Only include relationships of this type.
        to_type: Only include relationships to entities of this type.

    All parameters are optional — omit any to match everything.
    """
    # Validate types if provided.
    if from_type is not None:
        graph.types.validate(from_type)
    if to_type is not None:
        graph.types.validate(to_type)
    if via is not None:
        graph.relationship_types.validate(via)

    # No filters → return full graph.
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
    """Run a Cypher query and return a subgraph of matched entities.

    Args:
        cypher: A Cypher query string, or a bare pattern shorthand.

    Returns a new ``Graph`` containing matched entities and their
    mutual relationships.

    Examples::

        # Full Cypher
        crate.query("MATCH (a:Person)-[:author]->(b) RETURN a, b")

        # Shorthand — MATCH/RETURN added automatically
        crate.query("(a:Person)-[:author]->(b)")
    """
    from crategraph.core.query import run_cypher

    return run_cypher(graph, cypher)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


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
    candidate_keys.extend(
        key for key in props if key not in seen_keys and _looks_temporal_key(key)
    )

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
