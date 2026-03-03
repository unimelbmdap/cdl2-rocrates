"""Data models: Entity, Relationship (frozen dataclasses) and Pydantic user-facing models."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from html import escape as _escape_html
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

# --- Internal models (frozen dataclasses) ---


@dataclass(frozen=True)
class Entity:
    """An immutable node in the graph."""

    id: str
    types: list[str] = field(default_factory=list)
    properties: dict[str, Any] = field(default_factory=dict)
    source: str | None = None

    @property
    def type(self) -> str:
        """Display string joining all types (e.g. ``'PublishedResource, Report'``)."""
        return ", ".join(self.types) if self.types else "Unknown"

    @property
    def name(self) -> str:
        """Best display name: ``name`` property, falling back to ``id``."""
        return str(self.properties.get("name", self.id))

    @property
    def has_data(self) -> bool:
        """Whether this entity is a data entity (file or directory).

        Returns ``True`` if the entity has ``File`` or ``Dataset`` in its
        types, per the RO-Crate specification.  The root dataset (``./``)
        is excluded.
        """
        raw_id = self.properties.get("raw_id", self.id)
        if raw_id == "./":
            return False
        return "File" in self.types or "Dataset" in self.types

    def __repr__(self) -> str:
        return f"Entity({self.type!r}, {self.name!r}, id={self.id!r})"

    def _repr_html_(self) -> str:
        """Compact HTML representation for Jupyter notebooks."""
        return f"<pre>{_escape_html(repr(self))}</pre>"


@dataclass(frozen=True)
class Relationship:
    """An immutable directed edge in the graph.

    Relationships with an ``id`` were reified nodes in the source format
    (e.g. ``@type: Relationship`` items in an RO-Crate).  Inline references
    (e.g. ``preparedBy: {"@id": "..."}``)) have ``id=None``.
    """

    source: str
    target: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def __repr__(self) -> str:
        return f"Relationship({self.source!r} --{self.type}--> {self.target!r})"


# --- User-facing models (Pydantic) ---


class SelectOptions(BaseModel):
    """Parameters for structural filtering via ``Graph.select()``."""

    entity_types: list[str] | None = None
    relationship_types: list[str] | None = None
    time_range: tuple[int, int] | None = None
    min_connections: int | None = None
    max_connections: int | None = None
    source: str | None = None
    id: str | None = None


class ValidationIssue(BaseModel):
    """A single issue found during validation."""

    severity: Literal["error", "warning", "info"]
    entity_id: str | None = None
    message: str


class ValidationReport(BaseModel):
    """Result of running a validator against a graph."""

    issues: list[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        """A report is valid when it contains no error-level issues."""
        return not any(i.severity == "error" for i in self.issues)


# --- Inspector result model ---


@dataclass(frozen=True)
class FileInfo:
    """Result of inspecting a data file."""

    path: str
    content: str
    title: str | None
    size_bytes: int
    media_type: str | None

    def __repr__(self) -> str:
        name = Path(self.path).name
        return f"FileInfo({name!r}, {self.size_bytes} bytes)"

    def _repr_html_(self) -> str:
        name = _escape_html(Path(self.path).name)
        parts = [f"<b>{name}</b>"]
        if self.media_type:
            parts.append(f" ({_escape_html(self.media_type)})")
        parts.append(f" — {self.size_bytes:,} bytes")
        header = "".join(parts)
        content = _escape_html(self.content[:2000])
        return (
            f"<div style='font-family:monospace; font-size:13px'>"
            f"<div style='margin-bottom:4px'>{header}</div>"
            f"<pre style='white-space:pre-wrap; max-height:400px; "
            f"overflow-y:auto; padding:8px; background:#f5f5f5; "
            f"border-radius:4px'>{content}</pre>"
            f"</div>"
        )


# --- Viewer result model ---


@dataclass(frozen=True)
class ViewInfo:
    """Result of viewing a data file — rich HTML preview."""

    path: str
    html: str
    title: str | None
    size_bytes: int
    media_type: str | None

    def __repr__(self) -> str:
        name = Path(self.path).name
        return f"ViewInfo({name!r}, {self.size_bytes} bytes)"

    def _repr_html_(self) -> str:
        name = _escape_html(Path(self.path).name)
        parts = [f"<b>{name}</b>"]
        if self.media_type:
            parts.append(f" ({_escape_html(self.media_type)})")
        parts.append(f" — {self.size_bytes:,} bytes")
        header = "".join(parts)
        return (
            f"<div style='font-family:monospace; font-size:13px'>"
            f"<div style='margin-bottom:4px'>{header}</div>"
            f"<div style='max-height:500px; overflow-y:auto'>{self.html}</div>"
            f"</div>"
        )


# --- File tree model ---


class FileTree:
    """Tree view of data entities in a crate.

    Iterable over the underlying ``Entity`` objects.  Displays as an
    indented file tree in Jupyter notebooks and in ``repr()``.
    """

    __slots__ = ("_entities",)

    def __init__(self, entities: list[Entity]) -> None:
        self._entities = entities

    def __iter__(self) -> Iterator[Entity]:
        return iter(self._entities)

    def __len__(self) -> int:
        return len(self._entities)

    def __getitem__(self, index: int) -> Entity:
        return self._entities[index]

    def __bool__(self) -> bool:
        return len(self._entities) > 0

    # --- Tree building helper ---

    @staticmethod
    def _build_tree(entities: list[Entity]) -> dict[str, Any]:
        """Build a nested dict representing the directory tree."""
        tree: dict[str, Any] = {}
        for entity in entities:
            raw_id = entity.properties.get("raw_id", entity.id)
            parts = raw_id.rstrip("/").split("/")
            node = tree
            for part in parts[:-1]:
                node = node.setdefault(part + "/", {})
            # Leaf node: store the entity.
            node[parts[-1]] = entity
        return tree

    def _format_label(self, entity: Entity) -> str:
        """Format label for a single entity."""
        raw_id = entity.properties.get("raw_id", entity.id)
        name = raw_id.rstrip("/").rsplit("/", 1)[-1]
        media_type = entity.properties.get("encodingFormat")
        is_web = raw_id.startswith("http://") or raw_id.startswith("https://")
        if is_web:
            name = raw_id
        parts = [name]
        if media_type:
            parts.append(f"({media_type})")
        if is_web:
            parts.append("[web]")
        return " ".join(parts)

    def _render_tree(self, tree: dict[str, Any], prefix: str = "") -> list[str]:
        """Render tree dict as lines with box-drawing connectors."""
        lines: list[str] = []
        items = list(tree.items())
        for i, (key, value) in enumerate(items):
            is_last = i == len(items) - 1
            connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
            child_prefix = prefix + ("    " if is_last else "\u2502   ")
            if isinstance(value, Entity):
                lines.append(f"{prefix}{connector}{self._format_label(value)}")
            else:
                # Directory node.
                lines.append(f"{prefix}{connector}{key}")
                lines.extend(self._render_tree(value, child_prefix))
        return lines

    def __repr__(self) -> str:
        n = len(self._entities)
        label = "file" if n == 1 else "files"
        header = f"FileTree ({n} {label})"
        if not self._entities:
            return header
        tree = self._build_tree(self._entities)
        lines = self._render_tree(tree)
        return header + "\n" + "\n".join(lines)

    def _repr_html_(self) -> str:
        return (
            f"<pre style='font-family:monospace; font-size:13px'>{_escape_html(repr(self))}</pre>"
        )
