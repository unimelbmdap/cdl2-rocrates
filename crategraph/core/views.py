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

from collections.abc import Callable, Mapping
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


class Related:
    """The collection ``EntityView.related`` returns.

    A sequence of ``EntityView`` in ``_relationships`` (RO-Crate
    source) order. Protocols: iterable, sized, truthy. Reducers:
    ``first``, ``join``, ``list``. ``key`` is ``None`` (the view /
    its label), a ``str`` (that property), or a callable applied to
    each view; absent/``None`` projected values are skipped.
    """

    __slots__ = ("_views",)

    def __init__(self, views: list[EntityView] | tuple[EntityView, ...]) -> None:
        self._views: tuple[EntityView, ...] = tuple(views)

    def __iter__(self):
        return iter(self._views)

    def __len__(self) -> int:
        return len(self._views)

    def __bool__(self) -> bool:
        return bool(self._views)

    def _project(self, key: str | Callable[[EntityView], Any]):
        """Yield present, non-None projected values in order."""
        for view in self._views:
            val = key(view) if callable(key) else view._entity.properties.get(key)
            if val is not None:
                yield val

    def first(
        self,
        key: str | Callable[[EntityView], Any] | None = None,
        *,
        default: Any = None,
        strict: bool = False,
    ) -> Any:
        # CardinalityError is defined at the top of this module.
        if strict and len(self._views) > 1:
            msg = (
                f"first(strict=True) expected at most one related entity, "
                f"found {len(self._views)}: {[v.id for v in self._views]!r}"
            )
            raise CardinalityError(msg)
        if key is None:
            return self._views[0] if self._views else default
        for val in self._project(key):
            return val
        return default

    def join(
        self,
        key: str | Callable[[EntityView], Any] | None = None,
        *,
        sep: str = ", ",
        unique: bool = True,
        sort: bool = True,
        default: Any = None,
    ) -> Any:
        """Project, ``str()``-coerce, optionally dedup+sort, join to one scalar.

        ``key=None`` uses each related entity's ``label``. Returns
        ``default`` when nothing contributes. Dedup is order-preserving
        by equality; values are strings here so ``sort`` is safe.
        """
        if key is None:
            values = [view.label for view in self._views]
        else:
            values = [str(val) for val in self._project(key)]
        if unique:
            deduped: list[str] = []
            for val in values:
                if val not in deduped:
                    deduped.append(val)
            values = deduped
        if sort:
            values = sorted(values)
        if not values:
            return default
        return sep.join(values)
