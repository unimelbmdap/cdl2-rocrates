"""Graph-aware, ephemeral views over the immutable models.

``EntityView`` wraps an :class:`~crategraph.core.models.Entity` and a
``Graph`` reference, exposing ``type``/``name`` with the same display
semantics as ``Entity.type``/``Entity.name`` (raw access is available
via ``e.types`` and ``e.get("name")``), plus one-hop traversal via
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
from html import escape
from typing import TYPE_CHECKING, Any

from crategraph.core._mapping import ReadOnlyMapping
from crategraph.core._temporal import entity_temporal, parse_fields
from crategraph.core.models import Entity, _derive_label

if TYPE_CHECKING:
    from datetime import date

    from crategraph.core._temporal import TemporalValue
    from crategraph.core.graph import Graph
    from crategraph.core.models import Relationship


class CardinalityError(ValueError):
    """Raised when a single value was required but several were found.

    Subclasses ``ValueError`` so existing ``except ValueError`` handlers
    still catch it. Raised by :meth:`Related.first` with ``strict=True``.
    """


class EntityView:
    """An entity made graph-aware for ``annotate_entities`` callables."""

    __slots__ = ("_entity", "_graph")

    def __init__(self, entity: Entity | EntityView, graph: Graph | None = None) -> None:
        # Accepts either a bare Entity or an EntityView for compatibility with
        # legacy callers such as ``EntityView(graph.get(id), graph)`` now that
        # ``Graph.get()`` itself returns a view — storage is always the bare
        # record, so an already-wrapped view is unwrapped rather than nested.
        if isinstance(entity, EntityView):
            entity = entity.entity
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
        """Display string joining all types (same semantics as ``Entity.type``)."""
        return self._entity.type

    @property
    def name(self) -> str:
        """Best display name: ``name`` property, falling back to ``id`` (as ``Entity.name``)."""
        return self._entity.name

    @property
    def label(self) -> str:
        """Human label via the shared ``name -> title -> id`` fallback, always a string."""
        return _derive_label(self._entity)

    @property
    def properties(self) -> Mapping[str, Any]:
        """Shallow read-only view (top-level mutation raises ``TypeError``)."""
        return ReadOnlyMapping(self._entity.properties)

    @property
    def has_data(self) -> bool:
        """Whether this entity is a data entity (file or directory).

        Verbatim delegation to ``Entity.has_data`` — ``True`` if the entity
        has ``File`` or ``Dataset`` in its types, per the RO-Crate
        specification, excluding the root Dataset entity.
        """
        return self._entity.has_data

    @property
    def source(self) -> str | None:
        """The crate/source this entity came from (verbatim delegation to ``Entity.source``)."""
        return self._entity.source

    def get(self, key: str, default: Any = None) -> Any:
        """Shorthand for ``properties.get(key, default)`` — preferred in lambdas."""
        return self._entity.properties.get(key, default)

    @property
    def graph(self) -> Graph | None:
        """The owning graph (``None`` for a test-constructed view)."""
        return self._graph

    @property
    def entity(self) -> Entity:
        """The wrapped bare :class:`~crategraph.core.models.Entity`.

        Escape hatch for interop with ``Entity``-expecting code,
        ``dataclasses.replace``/``asdict``/``fields`` workflows, and cheap
        pickling of a single record. The dataclass protocol works on this,
        not on the view itself.
        """
        return self._entity

    # --- Temporal accessors (delegate to the shared coercion engine) ---
    #
    # These read ``self._entity.properties`` only — no graph traversal — so they
    # work on a graphless test-constructed view too. They turn the notebook's
    # ``int(str(e.get("startDateISOString"))[:4])`` slicing into ``e.year``.

    @property
    def start_date(self) -> date | None:
        """Start of the entity's date span as a ``date`` (year-only -> Jan 1).

        The *default content policy*: the first range pair that parses
        (``*ISOString`` preferred, human ``startDate``/``endDate`` as fallback),
        else a curated content point field — provenance dates like
        ``recordAppendDate`` are deliberately not consulted. For a specific
        field use :meth:`parse_date`. Partial precisions are bracketed honestly
        — see :attr:`date_precision`.
        """
        return entity_temporal(self._entity.properties).start_date

    @property
    def end_date(self) -> date | None:
        """End of the entity's date span as a ``date`` (year-only -> Dec 31)."""
        return entity_temporal(self._entity.properties).end_date

    @property
    def year(self) -> int | None:
        """Start year of the entity's date span — the workhorse for annotation."""
        return entity_temporal(self._entity.properties).year

    @property
    def date_precision(self) -> str | None:
        """Coarsest honest precision: ``"decade"``/``"year"``/``"month"``/``"day"``."""
        return entity_temporal(self._entity.properties).precision

    @property
    def date_circa(self) -> bool:
        """Whether any contributing field/qualifier marks the date as approximate."""
        return entity_temporal(self._entity.properties).circa

    @property
    def date_uncertain(self) -> bool:
        """Whether any contributing field/qualifier marks the date as uncertain."""
        return entity_temporal(self._entity.properties).uncertain

    def parse_date(self, *fields: str) -> TemporalValue | None:
        """Parse the named date *fields* in order; return the first that parses.

        The explicit, field-specific counterpart to the :attr:`year` /
        :attr:`start_date` *default policy*: it reads **only** the fields you
        name (no cascade, no provenance guessing), in order, and returns the
        first :class:`~crategraph.core._temporal.TemporalValue` that parses
        (``None`` if all are missing/unparseable). Use it when you need a
        specific field, ranges, ``precision``, or ``circa``/``uncertain``::

            e.parse_date("startDateISOString")            # one field
            e.parse_date("startDateISOString", "startDate")  # ordered fallback

        Returns crategraph temporal metadata, not a ``datetime.date`` — see
        :class:`~crategraph.core._temporal.TemporalValue`.
        """
        return parse_fields(self._entity.properties, fields)

    def parse_year(self, *fields: str) -> int | None:
        """Year of the first of *fields* that parses, else ``None``.

        None-safe convenience over :meth:`parse_date` — the common annotation
        call: ``birth_year=lambda e: e.parse_year("startDateISOString")``.
        """
        result = parse_fields(self._entity.properties, fields)
        return result.year if result is not None else None

    def related(self, rel: str, direction: str = "out") -> Related:
        """Entities one hop from this one via *rel*.

        Validates *rel* against the graph (unknown type ->
        ``ValueError``, parity with ``select``). A graphless view
        (test constructor) skips validation and returns empty.
        """
        if self._graph is None:
            return Related(())
        ids = self._graph._related_ids(self._entity.id, rel, direction)
        return Related(tuple(EntityView(self._graph._entities[i], self._graph) for i in ids))

    def has(self, rel: str, direction: str = "out") -> bool:
        return bool(self.related(rel, direction))

    def __eq__(self, other: object) -> bool:
        """Value equality on the wrapped entity — the graph reference is not part of identity.

        Compares against another ``EntityView`` (unwraps both sides) or a
        bare ``Entity`` (unwraps this side only), so ``view == entity`` and
        ``entity == view`` both work: a frozen dataclass returns
        ``NotImplemented`` for a foreign class, and Python falls back to the
        reflected comparison, which lands here.
        """
        if isinstance(other, EntityView):
            return self._entity == other._entity
        if isinstance(other, Entity):
            return self._entity == other
        return NotImplemented

    def __hash__(self) -> int:
        """Hash by entity ``id``, consistent with value equality.

        Unlike a bare ``Entity`` (unhashable — its ``properties`` dict
        breaks the dataclass-generated ``__hash__``), ``EntityView`` is
        hashable and usable in sets/dict keys.
        """
        return hash(self._entity.id)

    def __repr__(self) -> str:
        e = self._entity
        return f"EntityView({e.type!r}, {e.name!r}, id={e.id!r})"

    def _repr_html_(self) -> str:
        """Compact HTML representation for Jupyter (mirrors ``Entity._repr_html_``)."""
        return f"<pre>{escape(repr(self))}</pre>"


class RelationshipView:
    """A relationship made graph-aware for ``annotate_relationships`` callables."""

    __slots__ = ("_graph", "_relationship")

    def __init__(
        self,
        relationship: Relationship,
        graph: Graph | None = None,
    ) -> None:
        self._relationship = relationship
        self._graph = graph

    @property
    def id(self) -> str | None:
        return self._relationship.id

    @property
    def type(self) -> str:
        return self._relationship.type

    @property
    def source_id(self) -> str:
        return self._relationship.source

    @property
    def target_id(self) -> str:
        return self._relationship.target

    @property
    def properties(self) -> Mapping[str, Any]:
        """Shallow read-only view (top-level mutation raises ``TypeError``)."""
        return ReadOnlyMapping(self._relationship.properties)

    def get(self, key: str, default: Any = None) -> Any:
        """Shorthand for ``properties.get(key, default)`` — preferred in lambdas."""
        return self._relationship.properties.get(key, default)

    @property
    def source(self) -> EntityView:
        if self._graph is None:
            msg = "RelationshipView.source requires a graph."
            raise ValueError(msg)
        return EntityView(self._graph._entities[self._relationship.source], self._graph)

    @property
    def target(self) -> EntityView:
        if self._graph is None:
            msg = "RelationshipView.target requires a graph."
            raise ValueError(msg)
        return EntityView(self._graph._entities[self._relationship.target], self._graph)

    @property
    def graph(self) -> Graph | None:
        """The owning graph (``None`` for a test-constructed view)."""
        return self._graph

    def __repr__(self) -> str:
        return (
            f"RelationshipView(source={self._relationship.source!r}, "
            f"type={self._relationship.type!r}, "
            f"target={self._relationship.target!r})"
        )


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

    def list(
        self,
        key: str | Callable[[EntityView], Any] | None = None,
        *,
        unique: bool = False,
        sort: bool = False,
    ) -> list:
        """Project to a list. ``key=None`` -> the views themselves.

        ``unique`` is order-preserving by equality (works for
        unhashable list/dict values). ``sort`` never raises: natural
        order, falling back to ``str(value)`` keys for mixed /
        non-comparable values.
        """
        if key is None:
            values: list = [*self._views]
        else:
            values = [val for val in self._project(key)]
        if unique:
            deduped: list = []
            for val in values:
                if val not in deduped:
                    deduped.append(val)
            values = deduped
        if sort:
            try:
                values = sorted(values)
            except TypeError:
                values = sorted(values, key=lambda v: str(v))
        return values
