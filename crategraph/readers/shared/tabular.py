"""Shared definitions and base class for tabular graph readers.

Provides definition dataclasses (NodeDef, EdgeDef, etc.) and
TabularGraphReader — an abstract Reader that builds a Graph from
tabular data. Subclasses implement _load_table() to supply rows
as list[dict].
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader
from crategraph.core.models import Entity, Relationship


def _clean_str(value: Any) -> str:
    """Convert a value to a clean string, stripping trailing '.0' from integer-like floats.

    Pandas ``iterrows()`` upcasts mixed-type rows to float64, so an
    integer ID like ``1`` becomes ``1.0``.  This helper normalises that
    back to ``"1"``.
    """
    s = str(value).strip()
    if isinstance(value, float) and math.isfinite(value) and value == int(value):
        s = str(int(value))
    return s


def _split_etype(etype: str) -> list[str]:
    """Split an entity type string on dashes, strip, and replace spaces with underscores.

    Returns ``["Unknown"]`` if the result would be empty.
    """
    parts = [part.strip().replace(" ", "_") for part in etype.split("-") if part.strip()]
    return parts if parts else ["Unknown"]


# --- Definition dataclasses ---


@dataclass(frozen=True)
class NodeDef:
    """Definition of a table that contains node (entity) data."""

    table_name: str
    id_col: str
    fixed_types: list[str] | None = None
    type_col: str | None = None


@dataclass(frozen=True)
class EdgeDef:
    """Definition of a table that contains edge (relationship) data."""

    table_name: str
    source_col: str
    target_col: str
    type_col: str | None = None


@dataclass(frozen=True)
class LinkedMetadataDef:
    """Definition of a table containing metadata to nest on parent entities."""

    table_name: str
    parent_id_col: str
    property_name: str


@dataclass(frozen=True)
class FileEntityDef:
    """Definition of a table containing file entity references."""

    table_name: str
    parent_id_col: str
    file_path_col: str
    relationship_type: str


# --- Base class ---


class TabularGraphReader(Reader, ABC):
    """Abstract reader that builds a Graph from tabular data.

    Subclasses must implement ``_load_table`` to supply rows as
    ``list[dict[str, Any]]`` (with ``None`` for missing values)
    and ``can_read`` for format-specific path detection.
    """

    def __init__(
        self,
        *,
        node_tables: list[NodeDef] | None = None,
        edge_tables: list[EdgeDef] | None = None,
        linked_metadata_tables: list[LinkedMetadataDef] | None = None,
        file_entity_tables: list[FileEntityDef] | None = None,
    ) -> None:
        self._node_tables = node_tables or []
        self._edge_tables = edge_tables or []
        self._linked_metadata_tables = linked_metadata_tables or []
        self._file_entity_tables = file_entity_tables or []

    @abstractmethod
    def _load_table(self, table_name: str) -> list[dict[str, Any]] | None:
        """Load a table by name, returning rows as dicts or None if missing.

        Implementations must normalise missing/null values to ``None``.
        """

    def _all_table_names(self) -> set[str]:
        """Return the upper-cased set of all configured table names."""
        names: set[str] = set()
        for nd in self._node_tables:
            names.add(nd.table_name.upper())
        for ed in self._edge_tables:
            names.add(ed.table_name.upper())
        for lmd in self._linked_metadata_tables:
            names.add(lmd.table_name.upper())
        for fed in self._file_entity_tables:
            names.add(fed.table_name.upper())
        return names

    def read(self, path: str) -> Graph:
        """Read tabular data at *path* and return a populated Graph.

        Subclasses should prepare their data source (e.g. discover CSV files,
        load SQL into memory) by overriding ``read``, doing setup, then
        calling ``super().read(path)``.
        """
        graph = Graph(source=path)

        for node_def in self._node_tables:
            self._process_nodes(node_def, graph)

        for edge_def in self._edge_tables:
            self._process_edges(edge_def, graph)

        for lmd in self._linked_metadata_tables:
            grouped = self._collect_linked_metadata(lmd)
            self._attach_linked_metadata(lmd, grouped, graph)

        for fed in self._file_entity_tables:
            self._process_file_entities(fed, graph)

        return graph

    # --- Internal graph-building methods ---

    def _process_nodes(self, node_def: NodeDef, graph: Graph) -> None:
        """Load and process entities from a single node table."""
        rows = self._load_table(node_def.table_name)
        if rows is None:
            return

        skip_cols = {node_def.id_col}
        if node_def.type_col is not None:
            skip_cols.add(node_def.type_col)

        for row in rows:
            raw_id = row.get(node_def.id_col)
            if raw_id is None:
                continue
            entity_id = _clean_str(raw_id)

            # Resolve types.
            type_val = row.get(node_def.type_col) if node_def.type_col else None
            if type_val is not None:
                types = _split_etype(str(type_val))
            elif node_def.fixed_types is not None:
                types = list(node_def.fixed_types)
            else:
                types = ["Unknown"]

            # Build properties — all columns except id and type, None dropped.
            properties: dict[str, Any] = {}
            for col, value in row.items():
                if col in skip_cols or value is None:
                    continue
                properties[col] = value
            properties["source_table"] = node_def.table_name

            entity = Entity(
                id=entity_id,
                types=types,
                properties=properties,
                source=str(graph.source),
            )
            graph._add_node(entity)

    def _process_edges(self, edge_def: EdgeDef, graph: Graph) -> None:
        """Load and process relationships from a single edge table."""
        rows = self._load_table(edge_def.table_name)
        if rows is None:
            return

        skip_cols = {edge_def.source_col, edge_def.target_col}
        if edge_def.type_col is not None:
            skip_cols.add(edge_def.type_col)

        for row in rows:
            raw_source = row.get(edge_def.source_col)
            raw_target = row.get(edge_def.target_col)
            if raw_source is None or raw_target is None:
                continue

            source = _clean_str(raw_source)
            target = _clean_str(raw_target)

            # Resolve relationship type.
            type_val = row.get(edge_def.type_col) if edge_def.type_col else None
            if type_val is not None and str(type_val).strip():
                rel_type = str(type_val).strip()
            else:
                rel_type = edge_def.table_name

            # Build properties.
            properties: dict[str, Any] = {}
            for col, value in row.items():
                if col in skip_cols or value is None:
                    continue
                properties[col] = value
            properties["source_table"] = edge_def.table_name

            relationship = Relationship(
                source=source,
                target=target,
                type=rel_type,
                properties=properties,
            )
            graph._add_edge(relationship)

    def _collect_linked_metadata(self, lmd: LinkedMetadataDef) -> dict[str, list[dict[str, Any]]]:
        """Load a linked metadata table and group rows by parent ID."""
        rows = self._load_table(lmd.table_name)
        if rows is None:
            return {}

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            parent_id = _clean_str(row[lmd.parent_id_col])
            props: dict[str, Any] = {}
            for col, value in row.items():
                if col == lmd.parent_id_col or value is None:
                    continue
                props[col] = value
            grouped.setdefault(parent_id, []).append(props)
        return grouped

    def _attach_linked_metadata(
        self,
        lmd: LinkedMetadataDef,
        grouped: dict[str, list[dict[str, Any]]],
        graph: Graph,
    ) -> None:
        """Attach collected linked metadata to existing entities in the graph."""
        for parent_id, metadata_list in grouped.items():
            if parent_id not in graph._entities:
                continue
            existing = graph._entities[parent_id]
            new_props = dict(existing.properties)
            new_props[lmd.property_name] = metadata_list
            updated = Entity(
                id=existing.id,
                types=list(existing.types),
                properties=new_props,
                source=existing.source,
            )
            graph._add_node(updated)

    def _process_file_entities(self, fed: FileEntityDef, graph: Graph) -> None:
        """Load file entities and create relationships to their parent entities."""
        rows = self._load_table(fed.table_name)
        if rows is None:
            return

        skip_cols = {fed.parent_id_col, fed.file_path_col}

        for row in rows:
            file_path = row.get(fed.file_path_col)
            if file_path is None:
                continue
            file_path = str(file_path).strip()
            parent_id = _clean_str(row[fed.parent_id_col])

            properties: dict[str, Any] = {}
            for col, value in row.items():
                if col in skip_cols or value is None:
                    continue
                properties[col] = value
            properties["source_table"] = fed.table_name

            file_entity = Entity(
                id=file_path,
                types=["File"],
                properties=properties,
                source=str(graph.source),
            )
            graph._add_node(file_entity)

            relationship = Relationship(
                source=parent_id,
                target=file_path,
                type=fed.relationship_type,
            )
            graph._add_edge(relationship)
