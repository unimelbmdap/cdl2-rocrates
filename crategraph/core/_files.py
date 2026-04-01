"""Internal helpers for resolving local file paths from entities."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.models import Entity


def entity_raw_id(entity: Entity) -> str:
    """Return the underlying file/reference ID for an entity."""
    return str(entity.properties.get("raw_id", entity.id))


def is_contextual_entity(entity: Entity) -> bool:
    """Return True when an entity refers to context, not a local data file."""
    entity_id = entity_raw_id(entity)
    return (
        entity_id.startswith("#")
        or entity_id.startswith("http")
        or entity_id == "./"
        or bool(entity.properties.get("_is_root"))
    )


def resolve_entity_path(
    entity: Entity,
    *,
    fallback_source: str | None = None,
) -> Path | None:
    """Resolve an entity to a crate-local path, or None if that is unsafe/impossible."""
    if is_contextual_entity(entity):
        return None

    crate_root = entity.source or fallback_source
    if crate_root is None:
        return None

    crate_root_path = Path(crate_root)
    file_path = crate_root_path / entity_raw_id(entity)
    crate_root_resolved = crate_root_path.resolve(strict=False)

    try:
        file_path_resolved = file_path.resolve(strict=False)
        file_path_resolved.relative_to(crate_root_resolved)
    except ValueError:
        return None

    return file_path_resolved
