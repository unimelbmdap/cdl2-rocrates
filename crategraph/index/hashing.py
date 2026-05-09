"""Per-source content hashing for incremental rebuild detection.

The hash captures everything the indexer's output depends on:

- the configured text-property allowlist
- each entity's id, types, and formatted text (built from those properties)
- for ``has_data`` entities: the referenced file's mtime + size

mtime + size is cheaper than reading file contents and catches the
overwhelming majority of real changes. It does not catch in-place edits
that preserve mtime — but those are rare and users can force a full
rebuild by deleting the index file.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import TYPE_CHECKING

from crategraph.core.text import _format_property_text, _source_id_for

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity
    from crategraph.index.models import IndexerConfig


def entities_by_source(graph: Graph) -> dict[str, list[Entity]]:
    """Group a graph's entities by source id, skipping root nodes."""
    by_source: dict[str, list[Entity]] = {}
    for entity in graph.entities:
        if entity.properties.get("_is_root"):
            continue
        sid = _source_id_for(entity, graph)
        by_source.setdefault(sid, []).append(entity)
    return by_source


def source_path(graph: Graph, entities: Iterable[Entity]) -> str | None:
    """Pick a representative source path for a group of entities."""
    for entity in entities:
        if entity.source:
            return entity.source
    return graph.source


def compute_source_hash(
    graph: Graph,
    entities: Iterable[Entity],
    config: IndexerConfig,
) -> str:
    """Return a stable hex digest of *entities* under the given config."""
    sorted_entities = sorted(entities, key=lambda e: e.id)
    h = hashlib.sha256()
    h.update(b"text_properties:")
    h.update(json.dumps(list(config.text_properties)).encode())
    h.update(b"\n")

    for entity in sorted_entities:
        h.update(entity.id.encode())
        h.update(b"|")
        h.update(json.dumps(list(entity.types), sort_keys=True).encode())
        h.update(b"|")
        h.update(_format_property_text(entity, config.text_properties).encode())
        h.update(b"|")
        if entity.has_data:
            h.update(_file_meta(graph, entity).encode())
        h.update(b"\n")

    return h.hexdigest()


def _file_meta(graph: Graph, entity: Entity) -> str:
    """Cheap fingerprint of an entity's referenced file."""
    try:
        _, file_path = graph._require_local_entity_file(entity, action="hash")
    except (FileNotFoundError, ValueError):
        return "missing"
    try:
        stat = file_path.stat()
    except OSError:
        return "missing"
    return f"{stat.st_mtime_ns}:{stat.st_size}"
