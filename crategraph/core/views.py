"""Graph-aware, ephemeral views over the immutable models.

``EntityView`` wraps an :class:`~crategraph.core.models.Entity` and a
``Graph`` reference, exposing a *record-style* surface (matching
``entity_records``/``_derive_label``, deliberately NOT
``Entity.type``/``Entity.name``) plus one-hop traversal via
``related``/``has``. ``Related`` is the collection ``related`` returns.
``CardinalityError`` is colocated here because it is raised by
``Related.first(strict=True)`` and the codebase has no
exceptions-module convention (bare builtins inline).

Dependency direction is one-way: this module imports ``Graph`` only
under ``TYPE_CHECKING``; it receives a ``Graph`` instance and reads
adjacency through the narrow ``Graph._related_ids`` primitive.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity


class CardinalityError(ValueError):
    """Raised when a single value was required but several were found.

    Subclasses ``ValueError`` so existing ``except ValueError`` handlers
    still catch it. Raised by :meth:`Related.first` with ``strict=True``.
    """


class EntityView:
    """An entity made graph-aware for ``annotate_entities`` callables."""

    __slots__ = ("_entity", "_graph")

    def __init__(self, entity: Entity, graph: Graph | None = None) -> None:
        self._entity = entity
        self._graph = graph

    @property
    def id(self) -> str:
        return self._entity.id

    @property
    def types(self) -> tuple[str, ...]:
        return self._entity.types

    @property
    def type(self) -> str:
        """First type or ``""`` (record-style; not ``Entity.type``)."""
        return self._entity.types[0] if self._entity.types else ""

    @property
    def name(self) -> Any:
        """Raw ``properties['name']`` — may be ``None``."""
        return self._entity.properties.get("name")

    @property
    def label(self) -> str:
        """Human label via the shared ``name -> title -> id`` fallback."""
        from crategraph.core.records import _derive_label

        return _derive_label(self._entity)

    @property
    def properties(self) -> Mapping[str, Any]:
        """Shallow read-only view (top-level mutation raises ``TypeError``)."""
        return MappingProxyType(self._entity.properties)

    @property
    def graph(self) -> Graph | None:
        """The owning graph (``None`` for a test-constructed view)."""
        return self._graph

    def __repr__(self) -> str:
        return f"EntityView(id={self._entity.id!r})"
