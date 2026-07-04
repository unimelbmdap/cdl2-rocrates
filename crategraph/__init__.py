"""crategraph — researcher-friendly graph exploration for RO-Crate data."""

from __future__ import annotations

from pathlib import Path

from crategraph.core._temporal import TemporalValue, parse_date, parse_year
from crategraph.core.corpus import Corpus
from crategraph.core.graph import Graph
from crategraph.core.models import Entity, Relationship
from crategraph.core.records import Records
from crategraph.core.views import CardinalityError, EntityView, Related, RelationshipView
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
        include_root: Whether to include the root Dataset entity as a
            node in the graph. Defaults to ``False`` — the root's
            properties are promoted to ``metadata`` and the node and its
            edges are excluded. Pass ``True`` to include it. The root
            is identified via the metadata descriptor's ``about``
            property per the RO-Crate spec (falls back to ``./``).
    """

    def __init__(
        self,
        *paths: str,
        inline_relations: bool | list[str] = True,
        include_root: bool = False,
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

        reader = ROCrateReader(
            inline_relations=inline_relations,
            include_root=include_root,
        )

        if multi:
            super().__init__(source=None, metadata={})
            for path in paths:
                loaded = reader.read(path)
                prefix = self._crate_dirname(path)
                self.metadata[prefix] = dict(loaded.metadata)
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

    def _restore_root(self) -> None:
        """Re-add the root Dataset entity from stored metadata.

        Reconstructs the root entity (or prefixed variants for multi-crate
        graphs) from ``self.metadata`` and adds it back into the graph.
        No-op if the root is already present.

        The root ``@id`` is read from ``metadata["_root_id"]`` (set by
        ``ROCrateReader`` during loading), falling back to ``"./"`` for
        crates that lack a metadata descriptor.

        This is intended for internal use by writers and other components
        that need a complete RO-Crate representation including the root
        Dataset node.
        """
        _meta_keys = {"@context", "_root_id"}

        # Multi-crate: metadata is nested under per-crate prefixes.
        if self.source is None and self.sources:
            for source_path in self.sources:
                prefix = source_path
                crate_meta = self.metadata.get(prefix, {})
                root_id = crate_meta.get("_root_id", "./")
                prefixed_root_id = f"{prefix}/{root_id}"
                if prefixed_root_id in self._entities:
                    continue
                props = {k: v for k, v in crate_meta.items() if k not in _meta_keys}
                props["raw_id"] = root_id
                props["_is_root"] = True
                self._add_node(
                    Entity(
                        id=prefixed_root_id,
                        types=["Dataset"],
                        properties=props,
                        source=source_path,
                    )
                )
            return

        # Single-crate.
        root_id = self.metadata.get("_root_id", "./")
        if root_id in self._entities:
            return
        props = {k: v for k, v in self.metadata.items() if k not in _meta_keys}
        props["_is_root"] = True
        self._add_node(
            Entity(
                id=root_id,
                types=["Dataset"],
                properties=props,
                source=self.source,
            )
        )

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


__all__ = [
    "CardinalityError",
    "Corpus",
    "Crate",
    "Entity",
    "EntityView",
    "Graph",
    "Records",
    "Related",
    "Relationship",
    "RelationshipView",
    "TemporalValue",
    "parse_date",
    "parse_year",
]
