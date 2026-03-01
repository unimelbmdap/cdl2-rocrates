"""Shared colour palettes and helpers for renderers."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity

# 15 distinct, accessible-ish colours used by resolve_colour_map().
PALETTE = [
    "#4e79a7",
    "#f28e2b",
    "#e15759",
    "#76b7b2",
    "#59a14f",
    "#edc948",
    "#b07aa1",
    "#ff9da7",
    "#9c755f",
    "#bab0ac",
    "#86bcb6",
    "#d37295",
    "#FF6B6B",
    "#4ECDC4",
    "#45B7D1",
]

# Legacy aliases — kept for external compatibility.
TYPE_COLOURS = PALETTE[:12]
COMMUNITY_COLOURS = [
    "#FF6B6B",
    "#4ECDC4",
    "#45B7D1",
    "#96CEB4",
    "#FECA57",
    "#FF9FF3",
    "#54A0FF",
    "#5F27CD",
    "#00D2D3",
    "#FFA500",
    "#FF6348",
    "#2ED573",
    "#3742FA",
    "#F8B500",
    "#7C4DFF",
]


def colour_for_type(entity_type: str, type_list: list[str]) -> str:
    """Return a consistent colour for an entity type."""
    try:
        idx = type_list.index(entity_type)
    except ValueError:
        idx = hash(entity_type)
    return TYPE_COLOURS[idx % len(TYPE_COLOURS)]


_ENTITY_ATTRS = frozenset({"type", "source", "name", "id"})


def _resolve_group(entity: Entity, colour_by: str) -> str:
    """Determine the group value for a single entity.

    Built-in Entity attributes (``type``, ``source``, ``name``, ``id``)
    are checked first so they aren't shadowed by RO-Crate data
    properties with the same name (e.g. a reified ``source`` reference).
    All other keys resolve from ``entity.properties``.
    """
    if colour_by in _ENTITY_ATTRS:
        val = getattr(entity, colour_by, None)
        if val is not None:
            return str(val)
    val = entity.properties.get(colour_by)
    if val is not None:
        return str(val)
    if colour_by not in _ENTITY_ATTRS:
        val = getattr(entity, colour_by, None)
        if val is not None:
            return str(val)
    return "(no value)"


def resolve_colour_map(graph: Graph, colour_by: str) -> dict[str, str]:
    """Build ``{entity_id: hex_colour}`` for every entity in *graph*.

    Resolves each entity's group value generically: built-in Entity
    attributes (``type``, ``source``, ``name``, ``id``) take priority
    over data properties with the same name, then falls back to
    ``entity.properties`` for everything else.

    Special case: ``colour_by="community"`` auto-computes Louvain
    communities when no entity already has a ``"community"`` property.
    """
    if not graph._entities:
        return {}

    # Auto-compute communities if needed.
    if colour_by == "community" and not any(
        "community" in e.properties for e in graph._entities.values()
    ):
        graph = graph.detect_communities()

    groups = {eid: _resolve_group(e, colour_by) for eid, e in graph._entities.items()}
    unique = sorted(set(groups.values()))
    val_to_colour = {v: PALETTE[i % len(PALETTE)] for i, v in enumerate(unique)}
    return {eid: val_to_colour[g] for eid, g in groups.items()}
