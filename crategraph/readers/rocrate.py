"""RO-Crate (JSON-LD) reader — built-in.

Parses ``ro-crate-metadata.json`` directly as JSON (no RDFLib dependency).
Designed to handle messy, non-RDF-compliant crates gracefully — warnings
are collected but never block loading.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader
from crategraph.core.models import Entity, Relationship

_METADATA_FILENAME = "ro-crate-metadata.json"


class ROCrateReader(Reader):
    """Read an RO-Crate directory into a Graph."""

    def __init__(
        self,
        *,
        inline_relations: bool | list[str] = True,
        include_root: bool = True,
    ) -> None:
        if not isinstance(inline_relations, (bool, list)):
            msg = (
                f"inline_relations must be bool or list[str], "
                f"got {type(inline_relations).__name__}"
            )
            raise TypeError(msg)
        if isinstance(inline_relations, list) and not all(
            isinstance(item, str) for item in inline_relations
        ):
            msg = "inline_relations list must contain only strings"
            raise TypeError(msg)
        self._inline_relations = inline_relations
        self._include_root = include_root

    def can_read(self, path: str) -> bool:
        """Return True if *path* is or contains ``ro-crate-metadata.json``."""
        p = Path(path)
        if p.is_file() and p.name == _METADATA_FILENAME:
            return True
        return p.is_dir() and (p / _METADATA_FILENAME).is_file()

    def read(self, path: str) -> Graph:
        """Read the RO-Crate at *path* and return a populated Graph."""
        metadata_path = self._resolve_path(path)
        with metadata_path.open(encoding="utf-8") as f:
            data = json.load(f)

        graph = Graph(
            source=str(metadata_path.parent),
            metadata=self._extract_metadata(data),
        )

        items = data.get("@graph", [])
        root_id = self._detect_root_id(items)

        # Promote root Dataset properties to graph.metadata (always).
        for item in items:
            if item.get("@id") == root_id:
                graph.metadata.update(self._extract_properties(item))
                break

        # Store root ID after promotion so it can't be overwritten.
        graph.metadata["_root_id"] = root_id

        # First pass: create all entities.
        for item in items:
            if not self._include_root and item.get("@id") == root_id:
                continue
            entity = self._parse_entity(item, source=str(metadata_path.parent))
            if entity is not None:
                if item.get("@id") == root_id:
                    entity = Entity(
                        id=entity.id,
                        types=entity.types,
                        properties={**entity.properties, "_is_root": True},
                        source=entity.source,
                    )
                graph._add_node(entity)

        # Second pass: extract relationships (reified + inline @id refs).
        for item in items:
            if not self._include_root and item.get("@id") == root_id:
                continue
            for rel in self._extract_relationships(item, graph):
                if not self._include_root and (rel.source == root_id or rel.target == root_id):
                    continue
                graph._add_edge(rel)

        return graph

    def _detect_root_id(self, items: list[dict[str, Any]]) -> str:
        """Detect the root Dataset ``@id`` from the metadata descriptor.

        Per the RO-Crate spec, the root Dataset is referenced by the
        ``about`` property of the ``ro-crate-metadata.json`` entity.
        Falls back to ``"./"`` if not found.
        """
        for item in items:
            if item.get("@id") == "ro-crate-metadata.json":
                about = item.get("about")
                if isinstance(about, dict) and "@id" in about:
                    return about["@id"]
                if isinstance(about, str):
                    return about
                if isinstance(about, list) and about:
                    first = about[0]
                    if isinstance(first, dict) and "@id" in first:
                        return first["@id"]
                    if isinstance(first, str):
                        return first
                break
        return "./"

    # --- Path resolution ---

    def _resolve_path(self, path: str) -> Path:
        p = Path(path)
        if p.is_file() and p.name == _METADATA_FILENAME:
            return p
        if p.is_dir():
            candidate = p / _METADATA_FILENAME
            if candidate.is_file():
                return candidate
        msg = f"Cannot find {_METADATA_FILENAME} at '{path}'."
        raise FileNotFoundError(msg)

    # --- Metadata extraction ---

    def _extract_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        meta: dict[str, Any] = {}
        if "@context" in data:
            meta["@context"] = data["@context"]
        return meta

    # --- Entity parsing ---

    def _parse_entity(self, item: dict[str, Any], *, source: str) -> Entity | None:
        entity_id = item.get("@id")
        if entity_id is None:
            warnings.warn("Skipped item with no @id.", stacklevel=2)
            return None

        raw_type = item.get("@type", "")
        entity_types = self._normalise_types(raw_type)

        # Skip reified Relationship items — they're handled as edges.
        if self._is_reified_relationship(raw_type):
            return None

        # Build properties dict — everything except @id and @type.
        properties = self._extract_properties(item)

        return Entity(id=entity_id, types=entity_types, properties=properties, source=source)

    def _normalise_types(self, raw_type: str | list[str]) -> list[str]:
        """Normalise @type to a list of type strings.

        Leading/trailing whitespace is stripped from each type.
        ``"Relationship"`` is filtered out of multi-type lists.
        Empty results become ``["Unknown"]``.
        """
        if isinstance(raw_type, list):
            cleaned = [t.strip() for t in raw_type if isinstance(t, str) and t.strip()]
            # For multi-type, filter out "Relationship" to get the meaningful sub-type.
            non_rel = [t for t in cleaned if t != "Relationship"]
            if non_rel:
                return non_rel
            if cleaned:
                return cleaned
            return ["Unknown"]
        if isinstance(raw_type, str):
            stripped = raw_type.strip()
            return [stripped] if stripped else ["Unknown"]
        return "Unknown"

    def _is_reified_relationship(self, raw_type: str | list[str]) -> bool:
        if isinstance(raw_type, list):
            return "Relationship" in raw_type
        return raw_type == "Relationship"

    def _extract_properties(self, item: dict[str, Any]) -> dict[str, Any]:
        skip = {"@id", "@type"}
        props: dict[str, Any] = {}
        for key, value in item.items():
            if key in skip:
                continue
            # Flatten single @id references to just the ID string.
            props[key] = self._simplify_value(value)
        return props

    def _simplify_value(self, value: Any) -> Any:
        """Simplify JSON-LD @id references to plain strings."""
        if isinstance(value, dict) and "@id" in value and len(value) == 1:
            return value["@id"]
        if isinstance(value, list):
            return [self._simplify_value(v) for v in value]
        return value

    # --- Relationship extraction ---

    def _extract_relationships(self, item: dict[str, Any], graph: Graph) -> list[Relationship]:
        raw_type = item.get("@type", "")
        relationships: list[Relationship] = []

        # Reified relationships: @type includes "Relationship".
        if self._is_reified_relationship(raw_type):
            rel = self._parse_reified_relationship(item, raw_type)
            if rel is not None:
                relationships.append(rel)
            return relationships

        # Inline @id references: any property whose value is {"@id": "..."}.
        entity_id = item.get("@id")
        if entity_id is None:
            return relationships

        # Skip inline loop entirely when disabled.
        if self._inline_relations is False:
            return relationships

        for key, value in item.items():
            if key in {"@id", "@type", "source", "target"}:
                continue
            if isinstance(self._inline_relations, list) and key not in self._inline_relations:
                continue
            for target_id in self._extract_id_refs(value):
                if graph._backend.has_node(target_id):
                    relationships.append(
                        Relationship(source=entity_id, target=target_id, type=key)
                    )

        return relationships

    def _parse_reified_relationship(
        self, item: dict[str, Any], raw_type: str | list[str]
    ) -> Relationship | None:
        source_ref = item.get("source")
        target_ref = item.get("target")

        source_id = self._ref_to_id(source_ref)
        target_id = self._ref_to_id(target_ref)

        if source_id is None or target_id is None:
            rel_id = item.get("@id", "<unknown>")
            warnings.warn(
                f"Skipped relationship {rel_id}: missing source or target.",
                stacklevel=2,
            )
            return None

        rel_type = ", ".join(self._normalise_types(raw_type))
        properties = {
            k: self._simplify_value(v)
            for k, v in item.items()
            if k not in {"@id", "@type", "source", "target"}
        }

        return Relationship(
            source=source_id,
            target=target_id,
            type=rel_type,
            properties=properties,
            id=item.get("@id"),
        )

    def _ref_to_id(self, ref: Any) -> str | None:
        if isinstance(ref, dict) and "@id" in ref:
            return ref["@id"]
        if isinstance(ref, str):
            return ref
        return None

    def _extract_id_refs(self, value: Any) -> list[str]:
        """Extract @id strings from a value (single ref or list of refs)."""
        refs: list[str] = []
        if isinstance(value, dict) and "@id" in value and len(value) == 1:
            refs.append(value["@id"])
        elif isinstance(value, list):
            for v in value:
                if isinstance(v, dict) and "@id" in v and len(v) == 1:
                    refs.append(v["@id"])
        return refs
