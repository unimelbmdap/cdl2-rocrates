"""Locate the raw ``ro-crate-metadata.json`` files a graph was loaded from."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.graph import Graph

_METADATA_NAME = "ro-crate-metadata.json"


def _loaded_from_rocrate(graph: Graph) -> bool:
    """True when ``ROCrateReader`` left its ``_source_format`` marker."""
    metadata = graph.metadata
    if metadata.get("_source_format") == "ro-crate":
        return True
    return any(
        isinstance(v, dict) and v.get("_source_format") == "ro-crate" for v in metadata.values()
    )


def crate_metadata_paths(graph: Graph) -> list[Path]:
    """Return resolved paths to the crate metadata files behind *graph*.

    Candidates come from the full original graph, so filtering never drops a
    crate. Raises ``ValueError`` for graphs not loaded from an RO-Crate or
    without any source, and ``FileNotFoundError`` for a missing file.
    """
    if not _loaded_from_rocrate(graph):
        msg = (
            "Cannot validate: this graph was not loaded from an RO-Crate. "
            "crate.validate only works on graphs loaded with Crate(...) or "
            "ROCrateReader."
        )
        raise ValueError(msg)

    full = graph._root
    if full.source:
        candidates = [full.source]
    else:
        candidates = sorted({e.source for e in full._entities.values() if e.source is not None})
    if not candidates:
        msg = "This graph has no RO-Crate source to validate."
        raise ValueError(msg)

    paths: list[Path] = []
    for candidate in candidates:
        path = Path(candidate)
        if path.name != _METADATA_NAME:
            path = path / _METADATA_NAME
        path = path.resolve()
        if not path.is_file():
            msg = f"RO-Crate metadata file not found: {path}"
            raise FileNotFoundError(msg)
        paths.append(path)
    return sorted(paths)
