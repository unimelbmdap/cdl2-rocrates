"""Data models: Entity, Relationship (frozen dataclasses) and Pydantic user-facing models."""

from __future__ import annotations

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
