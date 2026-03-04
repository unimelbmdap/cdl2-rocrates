"""CSV graph reader — loads tabular CSV data into a Graph.

Designed for OHRM-style relational databases exported as CSV files,
but configurable for any tabular schema with node/edge/metadata tables.

Requires ``pandas`` — install via ``pip install crategraph[ohrm]``.
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core.graph import Graph
from crategraph.core.interfaces import Reader
from crategraph.core.models import Entity, Relationship

if TYPE_CHECKING:
    import pandas as pd


def _require_pandas() -> Any:
    """Import and return pandas, raising a helpful error if unavailable."""
    try:
        import pandas as pd
    except ImportError:
        msg = (
            "pandas is required for the CSV reader. Install it with: pip install crategraph[ohrm]"
        )
        raise ImportError(msg) from None
    return pd


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


def _is_nan(value: Any) -> bool:
    """Return True if *value* is NaN or None."""
    if value is None:
        return True
    return isinstance(value, float) and math.isnan(value)


def _split_etype(etype: str) -> list[str]:
    """Split an entity type string on dashes, strip, and replace spaces with underscores.

    Returns ``["Unknown"]`` if the result would be empty.
    """
    parts = [part.strip().replace(" ", "_") for part in etype.split("-") if part.strip()]
    return parts if parts else ["Unknown"]


# --- Definition dataclasses ---


@dataclass(frozen=True)
class NodeDef:
    """Definition of a CSV table that contains node (entity) data."""

    table_name: str
    id_col: str
    fixed_types: list[str] | None = None
    type_col: str | None = None


@dataclass(frozen=True)
class EdgeDef:
    """Definition of a CSV table that contains edge (relationship) data."""

    table_name: str
    source_col: str
    target_col: str
    type_col: str | None = None


@dataclass(frozen=True)
class LinkedMetadataDef:
    """Definition of a CSV table containing metadata to nest on parent entities."""

    table_name: str
    parent_id_col: str
    property_name: str


@dataclass(frozen=True)
class FileEntityDef:
    """Definition of a CSV table containing file entity references."""

    table_name: str
    parent_id_col: str
    file_path_col: str
    relationship_type: str


class CsvGraphReader(Reader):
    """Read a directory of CSV files into a Graph.

    Requires one or more definition objects describing the schema of each
    CSV table — which columns are IDs, which are edges, etc.
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

    def can_read(self, path: str) -> bool:
        """Return True if *path* is a directory containing at least one CSV matching a table."""
        p = Path(path)
        if not p.is_dir():
            return False
        expected = self._all_table_names()
        if not expected:
            return False
        csv_map = self._discover_csvs(p)
        return bool(expected & set(csv_map.keys()))

    def read(self, path: str) -> Graph:
        """Read CSV files at *path* and return a populated Graph."""
        _require_pandas()
        graph = Graph(source=path)
        csv_map = self._discover_csvs(Path(path))

        # Phase 1: Load nodes from each configured node table.
        for node_def in self._node_tables:
            self._load_nodes(node_def, csv_map, graph)

        # Phase 2: Load edges from each configured edge table.
        for edge_def in self._edge_tables:
            self._load_edges(edge_def, csv_map, graph)

        # Phase 3: Attach linked metadata to existing entities.
        for lmd in self._linked_metadata_tables:
            grouped = self._collect_linked_metadata(lmd, csv_map)
            self._attach_linked_metadata(lmd, grouped, graph)

        # Phase 4: Load file entities and their relationships.
        for fed in self._file_entity_tables:
            self._load_file_entities(fed, csv_map, graph)

        return graph

    def _load_nodes(self, node_def: NodeDef, csv_map: dict[str, Path], graph: Graph) -> None:
        """Load entities from a single node table CSV."""
        df = self._load_csv(node_def.table_name, csv_map)
        if df is None:
            return

        # Drop rows where the ID column is NaN.
        df = df.dropna(subset=[node_def.id_col])

        skip_cols = {node_def.id_col}
        if node_def.type_col is not None:
            skip_cols.add(node_def.type_col)

        for _, row in df.iterrows():
            entity_id = _clean_str(row[node_def.id_col])

            # Resolve types.
            if node_def.type_col is not None and not _is_nan(row.get(node_def.type_col)):
                types = _split_etype(str(row[node_def.type_col]))
            elif node_def.fixed_types is not None:
                types = list(node_def.fixed_types)
            else:
                types = ["Unknown"]

            # Build properties — all columns except id and type, NaN dropped.
            properties: dict[str, Any] = {}
            for col in df.columns:
                if col in skip_cols:
                    continue
                value = row[col]
                if not _is_nan(value):
                    properties[col] = value
            properties["source_table"] = node_def.table_name

            entity = Entity(
                id=entity_id,
                types=types,
                properties=properties,
                source=str(graph.source),
            )
            graph._add_node(entity)

    def _load_edges(self, edge_def: EdgeDef, csv_map: dict[str, Path], graph: Graph) -> None:
        """Load relationships from a single edge table CSV."""
        df = self._load_csv(edge_def.table_name, csv_map)
        if df is None:
            return

        # Drop rows where source or target is NaN.
        df = df.dropna(subset=[edge_def.source_col, edge_def.target_col])

        skip_cols = {edge_def.source_col, edge_def.target_col}
        if edge_def.type_col is not None:
            skip_cols.add(edge_def.type_col)

        for _, row in df.iterrows():
            source = _clean_str(row[edge_def.source_col])
            target = _clean_str(row[edge_def.target_col])

            # Resolve relationship type.
            if (
                edge_def.type_col is not None
                and not _is_nan(row.get(edge_def.type_col))
                and str(row[edge_def.type_col]).strip()
            ):
                rel_type = str(row[edge_def.type_col]).strip()
            else:
                rel_type = edge_def.table_name

            # Build properties — all columns except source, target, NaN dropped.
            properties: dict[str, Any] = {}
            for col in df.columns:
                if col in skip_cols:
                    continue
                value = row[col]
                if not _is_nan(value):
                    properties[col] = value
            properties["source_table"] = edge_def.table_name

            relationship = Relationship(
                source=source,
                target=target,
                type=rel_type,
                properties=properties,
            )
            graph._add_edge(relationship)

    def _collect_linked_metadata(
        self, lmd: LinkedMetadataDef, csv_map: dict[str, Path]
    ) -> dict[str, list[dict[str, Any]]]:
        """Load a linked metadata CSV and group rows by parent ID.

        Returns a dict mapping parent_id to a list of property dicts
        (excluding the parent_id column and NaN values).
        """
        df = self._load_csv(lmd.table_name, csv_map)
        if df is None:
            return {}

        grouped: dict[str, list[dict[str, Any]]] = {}
        for _, row in df.iterrows():
            parent_id = _clean_str(row[lmd.parent_id_col])
            props: dict[str, Any] = {}
            for col in df.columns:
                if col == lmd.parent_id_col:
                    continue
                value = row[col]
                if not _is_nan(value):
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

    def _load_file_entities(
        self, fed: FileEntityDef, csv_map: dict[str, Path], graph: Graph
    ) -> None:
        """Load file entities and create relationships to their parent entities."""
        df = self._load_csv(fed.table_name, csv_map)
        if df is None:
            return

        # Drop rows where the file path is NaN.
        df = df.dropna(subset=[fed.file_path_col])

        skip_cols = {fed.parent_id_col, fed.file_path_col}

        for _, row in df.iterrows():
            file_path = str(row[fed.file_path_col]).strip()
            parent_id = _clean_str(row[fed.parent_id_col])

            # Build properties for the file entity.
            properties: dict[str, Any] = {}
            for col in df.columns:
                if col in skip_cols:
                    continue
                value = row[col]
                if not _is_nan(value):
                    properties[col] = value
            properties["source_table"] = fed.table_name

            # Create the file entity.
            file_entity = Entity(
                id=file_path,
                types=["File"],
                properties=properties,
                source=str(graph.source),
            )
            graph._add_node(file_entity)

            # Create the relationship from parent to file.
            relationship = Relationship(
                source=parent_id,
                target=file_path,
                type=fed.relationship_type,
            )
            graph._add_edge(relationship)

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

    def _discover_csvs(self, root: Path) -> dict[str, Path]:
        """Map upper-cased CSV stem names to their Paths, searching recursively."""
        csv_map: dict[str, Path] = {}
        for csv_file in root.rglob("*.csv"):
            csv_map[csv_file.stem.upper()] = csv_file
        return csv_map

    def _load_csv(self, table_name: str, csv_map: dict[str, Path]) -> pd.DataFrame | None:
        """Load a CSV file by table name, returning a DataFrame or None if missing.

        Tries UTF-8 encoding first, falling back to Latin-1.
        """
        pd = _require_pandas()
        key = table_name.upper()
        if key not in csv_map:
            warnings.warn(
                f"CSV file for table '{table_name}' not found — skipping.",
                stacklevel=2,
            )
            return None
        csv_path = csv_map[key]
        try:
            return pd.read_csv(csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            return pd.read_csv(csv_path, encoding="latin-1")
