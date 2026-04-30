"""Native ``list[dict]`` export for graph entities and relationships.

Module-level functions that build plain Python records from a
:class:`Graph`. Each record is a dict with promoted keys first
(``id``, ``label``, ``type``, ``types`` for entities; ``source``,
``target``, ``type``, ``rel_id`` for relationships), followed by
non-colliding properties sorted alphabetically, followed by any
properties whose names collide with a promoted key — those are emitted
as ``prop_<key>`` (also alphabetically within that group), matching
:class:`CsvWriter`'s convention so user-defined names are preserved
when there is no actual collision.

Property values are deep-copied so callers can mutate returned records
freely without touching graph state — matching
:meth:`Graph.to_networkx`'s default ``copy=True`` behaviour. Native
Python types are preserved — lists stay lists, dicts stay dicts,
``None`` stays ``None``. Wrap with the DataFrame library of your
choice:

    pd.DataFrame(graph.entity_records())
    pl.DataFrame(graph.entity_records())
    pa.Table.from_pylist(graph.entity_records())

This module has no third-party dependencies.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity


_ENTITY_PROMOTED_KEYS: frozenset[str] = frozenset({"id", "label", "type", "types"})
_RELATIONSHIP_PROMOTED_KEYS: frozenset[str] = frozenset({"source", "target", "type", "rel_id"})


def _derive_label(entity: Entity) -> str:
    """Return a display label: ``name`` → ``title`` → ``entity.id``.

    Matches :func:`crategraph.writers._flatten.flatten_node`'s label
    fallback chain so the future ``entity_table()`` sugar produces the
    same column as ``nodes.csv``.
    """
    name_val = entity.properties.get("name")
    title_val = entity.properties.get("title")
    if name_val and isinstance(name_val, str):
        return name_val
    if title_val and isinstance(title_val, str):
        return title_val
    if name_val is not None and name_val != "":
        return str(name_val)
    if title_val is not None and title_val != "":
        return str(title_val)
    return entity.id


def _add_properties(
    properties: dict[str, Any],
    promoted_keys: frozenset[str],
    record: dict[str, Any],
) -> None:
    """Add *properties* into *record*, prefixing collisions with ``prop_``.

    Non-colliding property names are emitted in alphabetical order first
    so that user-defined names are preserved when possible. Property
    names that collide with a promoted key (or with an already-emitted
    key) get ``prop_`` prepended repeatedly until the name is unique.
    Values are deep-copied. Mirrors
    :func:`crategraph.writers._flatten._encode_properties` and
    :func:`crategraph.writers._flatten._unique_key`.
    """
    taken: set[str] = set(record)
    # Sort with non-colliding keys first so user-defined names survive when
    # there is no actual collision in *taken* yet.
    ordered = sorted(properties, key=lambda k: (k in promoted_keys, k))
    for key in ordered:
        out_key = key
        while out_key in promoted_keys or out_key in taken:
            out_key = f"prop_{out_key}"
        record[out_key] = copy.deepcopy(properties[key])
        taken.add(out_key)


def entity_records(graph: Graph) -> list[dict[str, Any]]:
    """Return one ``dict`` per entity with native Python values.

    Keys: ``id``, ``label``, ``type``, ``types`` first, then
    non-colliding entity properties sorted alphabetically, then any
    properties whose names collide with a promoted key emitted as
    ``prop_<key>``. ``label`` is derived from ``name → title → id``.
    ``type`` is the first entry of ``entity.types`` (or the empty
    string for an untyped entity). ``types`` is a ``list[str]`` (entity
    ``types`` is a tuple internally — converted for ergonomic
    downstream consumption). Property values are deep-copied.

    Wrap with your DataFrame library of choice:

        import pandas as pd
        df = pd.DataFrame(graph.entity_records())
    """
    records: list[dict[str, Any]] = []
    for entity in graph.entities:
        record: dict[str, Any] = {
            "id": entity.id,
            "label": _derive_label(entity),
            "type": entity.types[0] if entity.types else "",
            "types": list(entity.types),
        }
        _add_properties(entity.properties, _ENTITY_PROMOTED_KEYS, record)
        records.append(record)
    return records
