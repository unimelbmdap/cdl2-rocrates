"""Reader-agnostic text extraction from a Graph.

``text_records()`` walks a graph's entities and yields one record per
source unit:

- For each entity with ``has_data=True``, yields the file's text
  (extracted via the registered ``Inspector`` — typically markitdown).
- For every other entity, yields a short text block built from selected
  text-typed properties with the entity's types as a header.

This low-level helper can yield both source kinds. The public
``Graph.text_records()`` method defaults to file records and uses
``source_kind="properties"`` or ``source_kind="all"`` to opt into
metadata-derived text.

This module is reader-agnostic: it produces the same records regardless
of whether the graph came from RO-Crate, RDF, CSV, or any other reader.
The vocabulary uses ``source_id`` (the stable per-source identifier
derived from ``entity.source``) rather than reader-specific terms.

Returned records are dicts with keys: ``source_id``, ``entity_id``,
``source_kind`` (``"file"`` or ``"properties"``), ``entity_types``,
``text``. Callers may opt into additional entity properties with
``include_properties``. No ``token_count`` — that depends on a tokenizer
and lives in the index.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator, Sequence
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any, Literal

from crategraph.core._properties import merge_properties

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity

logger = logging.getLogger(__name__)

SourceKind = Literal["properties", "file"]


DEFAULT_TEXT_PROPERTIES: tuple[str, ...] = (
    "name",
    "title",
    "description",
    "abstract",
    "text",
    "keywords",
    "subject",
    "alternateName",
    "headline",
    "comment",
)


def text_records(
    graph: Graph,
    *,
    text_properties: Sequence[str] = DEFAULT_TEXT_PROPERTIES,
    include_properties: Sequence[str] | bool = False,
    filters: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield one text record per source unit in *graph*.

    Args:
        graph: The graph to walk.
        text_properties: Which entity properties contribute text content
            (used for the property-record path; reference dicts and
            non-string values are skipped).
        include_properties: Entity properties to copy into each output
            record. Pass a sequence of property names, or ``True`` to
            include all *public* entity properties (internal
            ``_``-prefixed loader flags such as ``_is_root`` are
            excluded; an explicit allowlist is honoured verbatim).
            Values are deep-copied and emitted as top-level keys;
            collisions with standard record keys are prefixed with
            ``prop_``.
        filters: Optional ``{"source_id": [...], "entity_types": [...],
            "source_kind": ["file" | "properties"], "entity_id": [...]}``.
            Filters are applied as the records are produced — non-matching
            records are not yielded.

    Yields:
        Dicts with keys ``source_id``, ``entity_id``, ``source_kind``,
        ``entity_types``, ``text``, plus any requested entity properties.

    Notes:
        - File extraction relies on the registered ``Inspector`` (see
          ``Graph.inspect``). Failures are logged and skipped — the
          generator never raises mid-iteration.
        - This is a generator; iterate once. Wrap with ``list(...)`` or
          ``pd.DataFrame(...)`` to materialise.
    """
    keep_source_id = _as_set(filters, "source_id")
    keep_entity_id = _as_set(filters, "entity_id")
    keep_entity_types = _as_set(filters, "entity_types")
    keep_source_kind = _as_set(filters, "source_kind")
    allowed = tuple(text_properties)
    included = _normalise_include_properties(include_properties)

    for entity in graph.entities:
        if entity.properties.get("_is_root"):
            continue
        if keep_entity_id is not None and entity.id not in keep_entity_id:
            continue
        if keep_entity_types is not None and not (set(entity.types) & keep_entity_types):
            continue

        source_id = _source_id_for(entity, graph)
        if keep_source_id is not None and source_id not in keep_source_id:
            continue

        # Property record (always yielded if non-empty).
        if keep_source_kind is None or "properties" in keep_source_kind:
            text = _format_property_text(entity, allowed)
            if text.strip():
                record = {
                    "source_id": source_id,
                    "entity_id": entity.id,
                    "source_kind": "properties",
                    "entity_types": tuple(entity.types),
                    "text": text,
                }
                yield enrich_record_with_entity_properties(record, entity, included)

        # File record (data entities only).
        if entity.has_data and (keep_source_kind is None or "file" in keep_source_kind):
            file_text = _extract_file_text(graph, entity)
            if file_text and file_text.strip():
                record = {
                    "source_id": source_id,
                    "entity_id": entity.id,
                    "source_kind": "file",
                    "entity_types": tuple(entity.types),
                    "text": file_text,
                }
                yield enrich_record_with_entity_properties(record, entity, included)


def enrich_record_with_entity_properties(
    record: dict[str, Any],
    entity: Entity,
    include_properties: Sequence[str] | bool = False,
) -> dict[str, Any]:
    """Return *record* with requested entity properties added.

    With ``include_properties=True``, internal ``_``-prefixed loader
    flags (e.g. ``_is_root``) are excluded — ``True`` means *public*
    entity metadata. An explicit allowlist is honoured verbatim.

    Property values are deep-copied so callers can freely mutate returned
    records. Property names that collide with existing record keys are
    prefixed with ``prop_`` repeatedly until unique, matching the graph
    record export convention — the shared rule lives in
    :func:`crategraph.core._properties.merge_properties`.
    """
    included = _normalise_include_properties(include_properties)
    if not included:
        return record

    out = dict(record)
    keys = (
        sorted(
            (key for key in entity.properties if not key.startswith("_")),
            key=lambda key: (key in out, key),
        )
        if included is True
        else included
    )
    merge_properties(out, entity.properties, keys)
    return out


def _normalise_include_properties(
    include_properties: Sequence[str] | bool,
) -> tuple[str, ...] | Literal[True]:
    """Return a stable representation of the requested metadata properties."""
    if include_properties is True:
        return True
    if include_properties is False:
        return ()
    if isinstance(include_properties, str):
        msg = "include_properties must be a sequence of property names, True, or False."
        raise TypeError(msg)
    return tuple(include_properties)


def _source_id_for(entity: Entity, graph: Graph) -> str:
    """Derive the stable per-source identifier for an entity.

    For RO-Crate readers, this is the crate directory name. For other
    readers, it's the basename of whatever path/IRI ``entity.source``
    holds. Falls back to ``graph.source`` then to a sentinel.
    """
    if entity.source:
        return PurePosixPath(entity.source).name
    if graph.source:
        return PurePosixPath(graph.source).name
    return "unknown"


def _format_property_text(entity: Entity, allowed: Iterable[str]) -> str:
    """Render an entity's selected text properties as one short block.

    Includes the entity's types as a header line. Skips properties
    whose values are reference dicts (``{"@id": "..."}``) or other
    non-textual structures.

    Returns the empty string when no property in *allowed* contributes
    text — emitting a type-header-only block would be noise (and would
    cause a property record to leak through when the caller has
    deliberately suppressed properties via ``text_properties=[]``).
    """
    property_lines: list[str] = []
    for key in allowed:
        if key not in entity.properties:
            continue
        rendered = _render_value(entity.properties[key])
        if rendered:
            property_lines.append(f"{key}: {rendered}")

    if not property_lines:
        return ""

    types = ", ".join(entity.types) if entity.types else "Untyped"
    return f"[{types}]\n" + "\n".join(property_lines)


def _render_value(value: object) -> str:
    """Stringify a property value, dropping references and other structures."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [_render_value(v) for v in value]
        return ", ".join(p for p in parts if p)
    return ""


def _extract_file_text(graph: Graph, entity: Entity) -> str | None:
    """Return the inspector-extracted text for a data entity, or None."""
    try:
        info = graph.inspect(entity)
    except (FileNotFoundError, ValueError) as exc:
        logger.debug("Skipping inspect of %s: %s", entity.id, exc)
        return None
    except Exception as exc:
        logger.warning("inspect(%s) failed: %s", entity.id, exc)
        return None
    return info.content or None


def _as_set(filters: dict[str, Any] | None, key: str) -> set[str] | None:
    """Pull a filter value as a set of strings, or None if unset/empty."""
    if not filters or key not in filters:
        return None
    value = filters[key]
    if value is None:
        return None
    return set(value)
