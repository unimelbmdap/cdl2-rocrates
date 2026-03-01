"""crategraph — researcher-friendly graph exploration for RO-Crate data."""

from __future__ import annotations

from pathlib import Path

from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.readers.rocrate import ROCrateReader


class Crate(Graph):
    """Convenience entry point for loading RO-Crate data.

    Usage::

        from crategraph import Crate

        # Single crate
        crate = Crate("path/to/crate/")

        # Multiple crates — IDs prefixed by directory name
        crate = Crate("data/iaea-crate/", "data/nla-crate/")

    Args:
        *paths: One or more paths to RO-Crate directories or
            ``ro-crate-metadata.json`` files.
        inline_relations: Controls which inline ``@id`` references become edges.
            ``True`` (default) — all inline refs become edges.
            ``False`` — only reified Relationship entities become edges.
            ``list[str]`` — only these property names become edges.
    """

    def __init__(
        self,
        *paths: str,
        inline_relations: bool | list[str] = True,
    ) -> None:
        if not paths:
            msg = "Crate requires at least one path."
            raise TypeError(msg)

        multi = len(paths) > 1

        # Validate directory name uniqueness for multi-crate loading.
        if multi:
            dirnames: list[str] = []
            for p in paths:
                dirname = self._crate_dirname(p)
                if dirname in dirnames:
                    msg = (
                        f"Cannot load multiple crates with the same directory name "
                        f'"{dirname}". Rename one of the directories to make them distinct.'
                    )
                    raise ValueError(msg)
                dirnames.append(dirname)

        reader = ROCrateReader(inline_relations=inline_relations)

        if multi:
            super().__init__(source=None, metadata={})
            for path in paths:
                loaded = reader.read(path)
                prefix = self._crate_dirname(path)
                self._ingest_prefixed(loaded, prefix)
        else:
            loaded = reader.read(paths[0])
            super().__init__(source=loaded.source, metadata=loaded.metadata)
            for entity in loaded.entities:
                self._add_node(entity)
            for rel in loaded.relationships:
                self._add_edge(rel)

    @staticmethod
    def _crate_dirname(path: str) -> str:
        """Extract the directory name from a crate path."""
        p = Path(path)
        if p.is_file():
            return p.parent.name
        return p.name

    def _ingest_prefixed(self, loaded: Graph, prefix: str) -> None:
        """Add entities and relationships from *loaded* with prefixed IDs."""
        # Build ID mapping: raw_id -> prefixed_id
        id_map: dict[str, str] = {}
        for entity in loaded.entities:
            prefixed_id = f"{prefix}/{entity.id}"
            id_map[entity.id] = prefixed_id
            new_props = dict(entity.properties)
            new_props["raw_id"] = entity.id
            self._add_node(
                Entity(
                    id=prefixed_id,
                    types=list(entity.types),
                    properties=new_props,
                    source=entity.source,
                )
            )

        for rel in loaded.relationships:
            new_source = id_map.get(rel.source, f"{prefix}/{rel.source}")
            new_target = id_map.get(rel.target, f"{prefix}/{rel.target}")
            new_id = f"{prefix}/{rel.id}" if rel.id is not None else None
            self._add_edge(
                Relationship(
                    source=new_source,
                    target=new_target,
                    type=rel.type,
                    properties=dict(rel.properties),
                    id=new_id,
                )
            )


__all__ = ["Crate", "Graph"]
