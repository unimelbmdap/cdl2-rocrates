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
choice (the example shows pandas; replace ``pd.DataFrame`` with
``pl.DataFrame`` or ``pa.Table.from_pylist`` for polars / pyarrow)::

    import pandas as pd

    nodes = pd.DataFrame(graph.entity_records())
    edges = pd.DataFrame(graph.relationship_records())

This module has no third-party dependencies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crategraph.core._properties import merge_properties

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity


_ENTITY_PROMOTED_KEYS: frozenset[str] = frozenset({"id", "label", "type", "types"})
_RELATIONSHIP_PROMOTED_KEYS: frozenset[str] = frozenset({"source", "target", "type", "rel_id"})


def _derive_label(entity: Entity) -> str:
    """Return a display label, falling back through the same chain as CSV.

    Order of preference:

    1. ``properties["name"]`` if present and a non-empty ``str``.
    2. ``properties["title"]`` if present and a non-empty ``str``.
    3. ``str(properties["name"])`` if ``name`` is non-``None`` and non-empty
       but not a string (e.g. an ``int`` like ``42``).
    4. ``str(properties["title"])`` under the same coercion rule.
    5. ``entity.id`` as the final fallback.

    Mirrors :func:`crategraph.writers._flatten.flatten_node`'s label
    fallback so the future ``entity_table()`` sugar produces the same
    column as ``nodes.csv``.
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
    Values are deep-copied. The collision/deep-copy rule itself lives in
    :func:`crategraph.core._properties.merge_properties` (shared with
    ``text_records``'s ``include_properties``); this function only owns
    the records-export ordering policy. Mirrors
    :func:`crategraph.writers._flatten._encode_properties` and
    :func:`crategraph.writers._flatten._unique_key`.
    """
    # Sort with non-colliding keys first so user-defined names survive when
    # there is no actual collision yet.
    ordered = sorted(properties, key=lambda k: (k in promoted_keys, k))
    merge_properties(record, properties, ordered, reserved=promoted_keys)


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
    result: list[dict[str, Any]] = []
    for entity in graph.entities:
        record: dict[str, Any] = {
            "id": entity.id,
            "label": _derive_label(entity),
            "type": entity.types[0] if entity.types else "",
            "types": list(entity.types),
        }
        _add_properties(entity.properties, _ENTITY_PROMOTED_KEYS, record)
        result.append(record)
    return result


def relationship_records(graph: Graph) -> list[dict[str, Any]]:
    """Return one ``dict`` per relationship with native Python values.

    Keys: ``source``, ``target``, ``type``, ``rel_id`` first, then
    non-colliding relationship properties sorted alphabetically, then
    any properties whose names collide with a promoted key emitted as
    ``prop_<key>``. ``rel_id`` is ``None`` for inline (non-reified)
    relationships, preserving the distinction between inline and
    reified rather than collapsing both to an empty string the way CSV
    does. Property values are deep-copied.
    """
    result: list[dict[str, Any]] = []
    for rel in graph.relationships:
        record: dict[str, Any] = {
            "source": rel.source,
            "target": rel.target,
            "type": rel.type,
            "rel_id": rel.id,
        }
        _add_properties(rel.properties, _RELATIONSHIP_PROMOTED_KEYS, record)
        result.append(record)
    return result
