"""Data models: Entity, Relationship (frozen dataclasses) and Pydantic user-facing models."""

from __future__ import annotations

import copy as _copy_module
from dataclasses import dataclass, field
from html import escape as _escape_html
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel

# --- Internal models (frozen dataclasses) ---


def _copy_properties(value: Any, memo: dict[int, Any] | None = None) -> Any:
    """Copy a ``properties`` value with deepcopy-equivalent semantics.

    Specialises the two container types that dominate crate properties
    (plain dict and list) to avoid ``copy.deepcopy``'s generic dispatch,
    while preserving its observable behaviour exactly: nested structures
    are fully detached, aliased objects stay aliased in the copy (one
    ``memo`` per top-level call), self-referential structures terminate,
    and every other value type (tuples, container subclasses, rich
    objects) falls back to ``copy.deepcopy`` sharing the same memo.
    """
    # type() checks, not isinstance(): dict/list SUBCLASSES must take the
    # deepcopy fallback so their concrete type survives, exactly as
    # copy.deepcopy preserves it. Tuples also go to the fallback: a cycle
    # can pass through a tuple (tuple -> list -> same tuple) and deepcopy
    # preserves that object graph with an after-the-fact memo check that
    # is not worth replicating here; tuples are rare in crate properties.
    if value is None or type(value) in (str, int, float, bool):
        return value
    if memo is None:
        memo = {}
    key = id(value)
    if key in memo:
        return memo[key]
    if type(value) is dict:
        copied_dict: dict[Any, Any] = {}
        memo[key] = copied_dict  # register BEFORE recursing: cycle safety
        for k, v in value.items():
            copied_dict[_copy_properties(k, memo)] = _copy_properties(v, memo)
        return copied_dict
    if type(value) is list:
        copied_list: list[Any] = []
        memo[key] = copied_list  # register BEFORE recursing: cycle safety
        for item in value:
            copied_list.append(_copy_properties(item, memo))
        return copied_list
    return _copy_module.deepcopy(value, memo)


@dataclass(frozen=True)
class Entity:
    """An immutable node in the graph.

    ``types`` is stored as a tuple so the frozen contract extends to the
    type list.  ``properties`` is a plain dict for ergonomics — treat it
    as read-only; mutating it will change graph state in place.
    """

    id: str
    types: tuple[str, ...] = ()
    properties: dict[str, Any] = field(default_factory=dict)
    source: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.types, tuple):
            object.__setattr__(self, "types", tuple(self.types))

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
        types, per the RO-Crate specification.  The root Dataset entity
        is excluded (identified by the ``_is_root`` property flag set
        during loading).
        """
        if self.properties.get("_is_root"):
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

    ``properties`` is a plain dict for ergonomics — treat it as read-only;
    mutating it will change graph state in place.
    """

    source: str
    target: str
    type: str
    properties: dict[str, Any] = field(default_factory=dict)
    id: str | None = None

    def __repr__(self) -> str:
        return f"Relationship({self.source!r} --{self.type}--> {self.target!r})"


# --- Coverage analysis models ---


@dataclass(frozen=True)
class CoveragePattern:
    """A discovered ``(relationship_type, source_type, target_type)`` triple."""

    relationship_type: str
    source_type: str
    target_type: str
    occurrences: int
    reified: bool


@dataclass(frozen=True)
class CoverageResult:
    """Coverage measurement for one side of one pattern.

    If a relationship type connects some entities of a type, the unreached
    ones are likely data quality gaps rather than intentionally unlinked.
    """

    pattern: CoveragePattern
    side: str  # "source" or "target"
    entity_type: str
    reached: int
    total: int

    @property
    def fraction(self) -> float:
        """Fraction of entities reached (0.0-1.0)."""
        return self.reached / self.total if self.total > 0 else 0.0

    @property
    def unreached(self) -> int:
        """Number of entities not reached by this pattern."""
        return self.total - self.reached

    def __repr__(self) -> str:
        return (
            f"CoverageResult({self.pattern.relationship_type} "
            f"{self.side}: {self.reached}/{self.total} "
            f"{self.entity_type} ({self.fraction:.0%}))"
        )


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
    """Raw HTML — callers are responsible for escaping all data-sourced
    content before including it here. This field is rendered unescaped
    by ``_repr_html_``."""
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
