"""Locate the raw ``ro-crate-metadata.json`` files a graph was loaded from."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.graph import Graph

_METADATA_NAME = "ro-crate-metadata.json"


def _crate_metadata(metadata: dict) -> list[dict]:
    """The metadata dicts ``ROCrateReader`` produced for each loaded crate.

    A single crate keeps its marker at the top level; a multi-crate graph keeps
    one marked dict per crate prefix. Only marked dicts are trusted, so a crate's
    own dict-valued properties are never mistaken for another crate.
    """
    if metadata.get("_source_format") == "ro-crate":
        return [metadata]
    return [
        value
        for value in metadata.values()
        if isinstance(value, dict) and value.get("_source_format") == "ro-crate"
    ]


def _loaded_from_rocrate(graph: Graph) -> bool:
    """True when ``ROCrateReader`` left its ``_source_format`` marker."""
    return bool(_crate_metadata(graph.metadata))


def _recorded_paths(metadata: dict) -> list[Path]:
    """Metadata file paths recorded by ``ROCrateReader`` for each loaded crate."""
    return [
        Path(m["_source_path"])
        for m in _crate_metadata(metadata)
        if isinstance(m.get("_source_path"), str)
    ]


def crate_metadata_paths(graph: Graph) -> list[Path]:
    """Return resolved paths to the crate metadata files behind *graph*.

    Candidates are the metadata paths ``ROCrateReader`` records in
    ``graph.metadata``, which survive filters and transforms, so no source
    crate is ever dropped; graphs without recorded paths fall back to the full
    original graph's sources. Raises ``ValueError`` for graphs not loaded from
    an RO-Crate or without any source, and ``FileNotFoundError`` for a missing
    file.
    """
    if not _loaded_from_rocrate(graph):
        msg = (
            "Cannot validate: this graph was not loaded from an RO-Crate. "
            "crate.validate only works on graphs loaded with Crate(...) or "
            "ROCrateReader."
        )
        raise ValueError(msg)

    # Paths recorded by ROCrateReader travel with ``metadata`` through filters
    # and transforms, so prefer them; transforms rebase ``_root`` and would
    # otherwise lose crates whose entities were all filtered out. A recorded
    # path names the metadata file itself (possibly a symlink); only legacy
    # source candidates may be directories.
    candidates = _recorded_paths(graph.metadata)
    if not candidates:
        full = graph._root
        if full.source:
            legacy = [full.source]
        else:
            legacy = sorted({e.source for e in full._entities.values() if e.source is not None})
        for source in legacy:
            path = Path(source)
            candidates.append(path if path.name == _METADATA_NAME else path / _METADATA_NAME)
    if not candidates:
        msg = "This graph has no RO-Crate source to validate."
        raise ValueError(msg)

    paths: set[Path] = set()
    for candidate in candidates:
        path = candidate.resolve()
        if not path.is_file():
            msg = f"RO-Crate metadata file not found: {path}"
            raise FileNotFoundError(msg)
        paths.add(path)
    return sorted(paths)
