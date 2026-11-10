"""Shared colour palettes and helpers for renderers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity

# 15 distinct, accessible-ish colours used by resolve_colour_groups().
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


_HEX_COLOUR = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")


def normalise_colour_map(colour_map: Mapping[Any, str] | None) -> dict[str, str]:
    """Check a user ``colour_map`` and return it as ``{group value: "#rrggbb"}``.

    Keys are values of ``colour_by``; they are compared as strings, the way
    group values are, so ``{2020: ...}`` matches a ``2020`` year. Values must
    be hex colours (``"#d62728"`` or ``"#d22"``). Raises ``ValueError`` for
    anything else, and ``TypeError`` if *colour_map* is not a mapping, so a
    typo fails before any layout work.
    """
    if colour_map is None:
        return {}
    if not isinstance(colour_map, Mapping):
        msg = (
            "colour_map must map colour_by values to hex colours, such as "
            f"{{'Person': '#d62728'}}; got {type(colour_map).__name__}"
        )
        raise TypeError(msg)
    normalised: dict[str, str] = {}
    for value, colour in colour_map.items():
        if not isinstance(colour, str) or not _HEX_COLOUR.fullmatch(colour):
            msg = (
                f"colour_map colour {colour!r} for {value!r} is not a hex colour such as '#d62728'"
            )
            raise ValueError(msg)
        digits = colour[1:].lower()
        if len(digits) == 3:
            digits = "".join(c * 2 for c in digits)
        normalised[str(value)] = f"#{digits}"
    return normalised


def resolve_entity_colours(
    graph: Graph, colour_by: str, colour_map: Mapping[Any, str] | None = None
) -> dict[str, str]:
    """Build ``{entity_id: hex_colour}`` for every entity in *graph*.

    See :func:`resolve_colour_groups`, which also returns the legend.
    """
    return resolve_colour_groups(graph, colour_by, colour_map)[0]


def resolve_colour_groups(
    graph: Graph, colour_by: str, colour_map: Mapping[Any, str] | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Build ``{entity_id: hex_colour}`` and the matching ``{group value: hex_colour}``.

    The second mapping is the legend: one entry per value of *colour_by*
    present in *graph*, with the colour its entities are drawn in. Values
    named in *colour_map* get its colour; the rest keep the palette colour
    they would have had without it.

    Resolves each entity's group value generically: built-in Entity
    attributes (``type``, ``source``, ``name``, ``id``) take priority
    over data properties with the same name, then falls back to
    ``entity.properties`` for everything else.

    Special case: ``colour_by="community"`` auto-computes Louvain
    communities when no entity already has a ``"community"`` property.
    """
    chosen = normalise_colour_map(colour_map)
    if not graph._entities:
        return {}, {}

    # Auto-compute communities if needed.
    if colour_by == "community" and not any(
        "community" in e.properties for e in graph._entities.values()
    ):
        graph = graph.detect_communities()

    groups = {eid: _resolve_group(e, colour_by) for eid, e in graph._entities.items()}
    unique = sorted(set(groups.values()))
    val_to_colour = {v: chosen.get(v, PALETTE[i % len(PALETTE)]) for i, v in enumerate(unique)}
    return {eid: val_to_colour[g] for eid, g in groups.items()}, val_to_colour
