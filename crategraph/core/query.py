"""Cypher query support via grand-cypher."""

from __future__ import annotations

import logging
import re
import warnings
from typing import TYPE_CHECKING

import networkx as nx

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from crategraph.core.graph import Graph


class CypherQueryWarning(UserWarning):
    """Emitted when a Cypher query triggers a temporary NetworkX conversion."""


def _build_nx_graph(graph: Graph) -> nx.MultiDiGraph:
    """Build a NetworkX MultiDiGraph with ``__labels__`` for grand-cypher.

    Grand-cypher expects:
    - Nodes: ``__labels__`` (set of strings) for ``MATCH (a:Label)``
    - Nodes: properties as top-level attributes
    - Edges: ``__labels__`` (set of strings) for ``[:Type]``
    - Edges: properties as top-level attributes
    """
    nxg = nx.MultiDiGraph()

    for eid, entity in graph._entities.items():
        attrs = dict(entity.properties)
        attrs["__labels__"] = set(entity.types)
        attrs["__entity_id__"] = eid
        nxg.add_node(eid, **attrs)

    for rel in graph._relationships:
        if rel.source in graph._entities and rel.target in graph._entities:
            attrs = dict(rel.properties)
            attrs["__labels__"] = {rel.type}
            nxg.add_edge(rel.source, rel.target, **attrs)

    return nxg


def _get_nx_graph(graph: Graph) -> nx.MultiDiGraph:
    """Get or build a NetworkX graph for Cypher querying.

    Always builds a fresh graph with ``__labels__`` set, since the
    internal NetworkX backend graph doesn't have them by default.
    Emits a ``CypherQueryWarning`` when the backend is not NetworkX.
    """
    from crategraph.core.backends.networkx import NetworkXBackend

    if not isinstance(graph._backend, NetworkXBackend):
        n_entities = len(graph._entities)
        warnings.warn(
            f"Cypher queries use NetworkX internally. Converting {n_entities} "
            f"entities from the current backend to a temporary NetworkX graph. "
            f"This is faster with the NetworkX backend.",
            CypherQueryWarning,
            stacklevel=3,
        )

    return _build_nx_graph(graph)


def _extract_node_ids(result: dict, graph: Graph) -> set[str]:
    """Extract entity IDs from a grand-cypher result dict.

    Grand-cypher returns ``{column: [values...]}``.  When a column
    contains node references, the values are dicts with the node's
    attributes.  We match these back to entity IDs by reading the
    ``__entity_id__`` marker attribute added during graph construction.
    """
    entity_ids = set(graph._entities.keys())
    found: set[str] = set()

    for _column, values in result.items():
        for value in values:
            if isinstance(value, dict):
                # Node result — grand-cypher returns node attrs as a dict.
                eid = value.get("__entity_id__")
                if eid is not None and eid in entity_ids:
                    found.add(eid)
            elif isinstance(value, str) and value in entity_ids:
                # ID() function returns string IDs directly.
                found.add(value)

    return found


_NODE_VAR_RE = re.compile(r"\((\w+)")


def _normalise_cypher(cypher: str) -> str:
    """Wrap a bare pattern in ``MATCH ... RETURN`` if needed.

    Allows shorthand like ``"(a:Person)-[:author]->(b)"`` instead of
    the full ``"MATCH (a:Person)-[:author]->(b) RETURN a, b"``.
    """
    upper = cypher.strip().upper()

    if "RETURN" in upper:
        return cypher

    if upper.startswith("MATCH"):
        msg = (
            "Your query starts with MATCH but has no RETURN clause. "
            "Either add RETURN (e.g. MATCH (a:Person) RETURN a) "
            "or use pattern shorthand (e.g. (a:Person))."
        )
        raise ValueError(msg)

    variables = _NODE_VAR_RE.findall(cypher)
    if not variables:
        return cypher

    # Deduplicate while preserving order.
    return_clause = ", ".join(dict.fromkeys(variables))
    expanded = f"MATCH {cypher} RETURN {return_clause}"
    logger.debug("Expanded pattern shorthand to: %s", expanded)
    return expanded


def run_cypher(graph: Graph, cypher: str) -> Graph:
    """Execute a Cypher query against *graph* and return a subgraph.

    Args:
        graph: The graph to query.
        cypher: A Cypher query string, or a bare pattern like
            ``"(a:Person)-[:author]->(b)"`` which is automatically
            wrapped in ``MATCH ... RETURN``.

    Returns:
        A ``Graph`` containing the matched entities and their mutual
        relationships.

    Raises:
        ImportError: If grand-cypher is not installed.
        ValueError: If the query returns only scalar/aggregate values
            (no node references).
    """
    try:
        from grandcypher import GrandCypher
    except ImportError:
        msg = "Cypher queries require grand-cypher. Install it with: uv add crategraph[cypher]"
        raise ImportError(msg) from None

    cypher = _normalise_cypher(cypher)
    nxg = _get_nx_graph(graph)
    result = GrandCypher(nxg).run(cypher)

    matched_ids = _extract_node_ids(result, graph)

    if not matched_ids:
        # Check whether the query returned any data at all.
        has_data = any(len(values) > 0 for values in result.values())
        if has_data:
            msg = (
                "query() returns a Graph — your query returned scalar values "
                "only. Use node references in RETURN "
                "(e.g. MATCH (n:Person) RETURN n)."
            )
            raise ValueError(msg)

    return graph._subgraph(matched_ids)
