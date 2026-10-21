"""Raw JSON-LD document model for an RO-Crate metadata file.

Used for both the crate being validated and the MASP profile (itself an
RO-Crate). It reads the file as written, without touching the ``Graph``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from crategraph.validators.masp.context import (
    TermExpander,
    normalise_iri,
    resolve_context,
)

DESCRIPTOR_ID = "ro-crate-metadata.json"


def is_reference(value: Any) -> bool:
    """True for a JSON-LD node reference (a dict with ``@id``)."""
    return isinstance(value, dict) and "@id" in value


def literal_of(value: Any) -> Any:
    """Unwrap a ``{"@value": v}`` object; return anything else unchanged."""
    if isinstance(value, dict) and "@value" in value:
        return value["@value"]
    return value


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else [value]


@dataclass(frozen=True)
class Node:
    id: str
    types: tuple[str, ...]
    properties: dict[str, list[Any]]


class CrateDocument:
    """A loaded ``ro-crate-metadata.json`` with expansion-aware lookups."""

    def __init__(
        self,
        source: str,
        nodes: dict[str, Node],
        duplicate_ids: tuple[str, ...],
        unresolved_contexts: tuple[str, ...],
        expander: TermExpander,
    ) -> None:
        self.source = source
        self.nodes = nodes
        self.duplicate_ids = duplicate_ids
        self.unresolved_contexts = unresolved_contexts
        self.expander = expander
        self._expansions: dict[str, str | None] = {}

    @classmethod
    def from_json(cls, data: dict, *, source: str, fetch_contexts: bool = False) -> CrateDocument:
        graph = data.get("@graph") if isinstance(data, dict) else None
        if not isinstance(graph, list):
            raise ValueError(f"{source}: missing @graph array")

        resolution = resolve_context(data.get("@context", []), fetch=fetch_contexts)
        expander = TermExpander(resolution.context)

        merged: dict[str, tuple[list[str], dict[str, list[Any]]]] = {}
        duplicates: list[str] = []
        for item in graph:
            if not isinstance(item, dict) or not isinstance(item.get("@id"), str):
                continue
            node_id = item["@id"]
            if node_id in merged:
                if node_id not in duplicates:
                    duplicates.append(node_id)
            else:
                merged[node_id] = ([], {})
            types, props = merged[node_id]
            raw_type = item.get("@type")
            if raw_type is not None:
                for t in _as_list(raw_type):
                    if isinstance(t, str) and t not in types:
                        types.append(t)
            for key, value in item.items():
                if key in ("@id", "@type"):
                    continue
                props.setdefault(key, []).extend(_as_list(value))

        nodes = {
            nid: Node(id=nid, types=tuple(types), properties=props)
            for nid, (types, props) in merged.items()
        }
        return cls(
            source=source,
            nodes=nodes,
            duplicate_ids=tuple(duplicates),
            unresolved_contexts=resolution.unresolved,
            expander=expander,
        )

    @classmethod
    def load(cls, path: Path, *, fetch_contexts: bool = False) -> CrateDocument:
        path = Path(path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}: invalid JSON ({exc})") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path}: top level is not a JSON object")
        try:
            return cls.from_json(data, source=str(path), fetch_contexts=fetch_contexts)
        except ValueError as exc:
            if str(path) in str(exc):
                raise
            raise ValueError(f"{path}: {exc}") from exc

    def get(self, node_id: str) -> Node | None:
        return self.nodes.get(node_id)

    def descriptor(self) -> Node | None:
        return self.nodes.get(DESCRIPTOR_ID)

    def root(self) -> Node | None:
        descriptor = self.descriptor()
        if descriptor is None:
            return None
        for key in descriptor.properties:
            if key == "about" or self._iri_of(key) == "http://schema.org/about":
                for value in descriptor.properties[key]:
                    if is_reference(value):
                        return self.nodes.get(value["@id"])
        return None

    def _iri_of(self, key: str) -> str | None:
        if key not in self._expansions:
            expanded = self.expander.expand(key)
            self._expansions[key] = None if expanded is None else normalise_iri(expanded)
        return self._expansions[key]

    def type_iris(self, node: Node) -> frozenset[str]:
        return frozenset(self._iri_of(t) or t for t in node.types)

    def values_for(self, node: Node, name: str, iri: str | None) -> list[Any] | None:
        if name == "@id":
            return [node.id]
        if iri is None:
            values = node.properties.get(name)
            return list(values) if values is not None else None
        found = False
        out: list[Any] = []
        for key, values in node.properties.items():
            if self._iri_of(key) == iri:
                found = True
                out.extend(values)
        return out if found else None
