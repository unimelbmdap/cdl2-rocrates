"""Graph class — the central object for loading, querying, and visualising graphs."""

from __future__ import annotations

import functools
import warnings
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import networkx as nx

from crategraph.core import (
    analysis,
    filtering,
    presentation,
    transforms,
)
from crategraph.core._files import entity_raw_id, is_contextual_entity, resolve_entity_path
from crategraph.core.models import Entity, Relationship, _copy_properties
from crategraph.core.types import TypeRegistry

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    from crategraph.core.models import CoverageResult, FileInfo, ViewInfo
    from crategraph.core.records import Records
    from crategraph.core.views import EntityView, RelationshipView


@functools.cache
def _source_name(source: str) -> str:
    """Final path component of a crate source path, memoised.

    Module-level (not a method) so the cache never pins a Graph instance;
    unbounded because the key space is crate source paths, a handful per
    process.
    """
    return PurePosixPath(source).name


class Graph:
    """The central object for loading, querying, and visualising graphs.

    Stores entities and relationships in plain dicts and lists, with a
    lazily built per-endpoint adjacency index for traversal.  NetworkX
    graphs are built on demand where needed (``to_networkx()``, Cypher
    queries, community detection).

    Graphs are not thread-safe: mutating a graph (loading, ``_add_node``,
    ``_add_edge``) concurrently with reads is unsupported, as the lazy
    caches are built on first read.
    """

    def __init__(
        self,
        *,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.source = source
        self.metadata: dict[str, Any] = metadata if metadata is not None else {}
        self._entities: dict[str, Entity] = {}
        self._relationships: list[Relationship] = []
        # Lazily built from _entities on first access to `sources`;
        # None means "not built". Invalidated by _add_node.
        self._source_names: set[str] | None = None
        self._root: Graph = self  # reference to the root/full graph for expand()
        self._simplification_k: int | None = None
        self._derived_fields: dict[str, str | None] = {}
        self._relationship_derived_fields: dict[str, str | None] = {}
        # Lazily built (out_by_source, in_by_target) adjacency index over
        # _relationships, used by _related_ids. Invalidated on mutation.
        self._rel_adjacency: (
            tuple[dict[str, list[Relationship]], dict[str, list[Relationship]]] | None
        ) = None
        # Cached type registries — rebuilding these scans every entity /
        # relationship, so memoise them. Invalidated on mutation.
        self._entity_types_cache: TypeRegistry | None = None
        self._relationship_types_cache: TypeRegistry | None = None

    # --- Public read-only properties ---

    @property
    def types(self) -> TypeRegistry:
        """Registry of entity types present in this graph."""
        if self._entity_types_cache is None:
            all_types: set[str] = set()
            for e in self._entities.values():
                all_types.update(e.types)
            self._entity_types_cache = TypeRegistry(frozenset(all_types), label="entity type")
        return self._entity_types_cache

    @property
    def title(self) -> str:
        """Name or title of this RO-Crate.

        For multi-crate graphs (where ``metadata`` is keyed by crate
        directory and each value is a per-crate metadata dict), the
        per-crate names are joined with commas.
        """
        for key in ("name", "title"):
            value = self.metadata.get(key)
            if isinstance(value, str) and value:
                return value
        # Multi-crate shape only: every top-level value is a per-crate
        # metadata dict. A loaded single-crate always has at least one
        # non-dict (e.g. ``@context``, ``@type``, ``description``), so
        # this avoids picking ``name`` out of an unrelated nested object.
        if self.metadata and all(isinstance(v, dict) for v in self.metadata.values()):
            nested_titles = []
            for value in self.metadata.values():
                for key in ("name", "title"):
                    sub = value.get(key)
                    if isinstance(sub, str) and sub:
                        nested_titles.append(sub)
                        break
            if nested_titles:
                return ", ".join(nested_titles)
        return "Untitled RO-Crate"

    @property
    def relationship_types(self) -> TypeRegistry:
        """Registry of relationship types present in this graph."""
        if self._relationship_types_cache is None:
            self._relationship_types_cache = TypeRegistry(
                frozenset(r.type for r in self._relationships),
                label="relationship type",
            )
        return self._relationship_types_cache

    @property
    def entities(self) -> list[EntityView]:
        """All entities in the graph, as graph-aware :class:`EntityView`\\ s.

        Each view carries a live reference to this graph, so you can
        traverse straight from a result: ``crate.entities[0].related(...)``.
        Views are fresh per call and compare by value (``==``) and hash by
        id; they are not guaranteed to be the same object across calls. For
        the bare record use ``.entity``.
        """
        from crategraph.core.views import EntityView

        return [EntityView(e, self) for e in self._entities.values()]

    @property
    def relationships(self) -> list[Relationship]:
        """All relationships in the graph."""
        return list(self._relationships)

    def entity_view(self, entity_id: str) -> EntityView:
        """Alias of :meth:`get` — kept as a soft path for existing code.

        Both return a graph-aware :class:`EntityView` now, so
        ``crate.entity_view(id)`` and ``crate.get(id)`` are interchangeable.
        Not deprecated. Raises ``KeyError`` for an unknown id (same as
        :meth:`get`).
        """
        return self.get(entity_id)

    @property
    def files(self) -> list[EntityView]:
        """Data entities (files and directories) as graph-aware views.

        Convenience for filtering to entities where ``has_data`` is
        ``True``, sorted by ID. Returns :class:`EntityView`\\ s (use
        ``.entity`` for the bare record).
        """
        from crategraph.core.views import EntityView

        ordered = sorted(
            (e for e in self._entities.values() if e.has_data),
            key=lambda e: e.properties.get("raw_id", e.id),
        )
        return [EntityView(e, self) for e in ordered]

    def __len__(self) -> int:
        """Number of entities in the graph."""
        return len(self._entities)

    @property
    def sources(self) -> list[str]:
        """Distinct source directory names, sorted."""
        if self._source_names is None:
            self._source_names = {
                _source_name(entity.source)
                for entity in self._entities.values()
                if entity.source is not None
            }
        return sorted(self._source_names)

    @property
    def derived_fields(self) -> Mapping[str, str | None]:
        """Read-only registry of fields added by ``annotate_entities``.

        Maps field name -> short descriptor (callable ``__qualname__``,
        or ``None`` for an anonymous lambda). Distinguishes derived
        columns from native crate metadata for honest export.
        """
        return MappingProxyType(self._derived_fields)

    @property
    def relationship_derived_fields(self) -> Mapping[str, str | None]:
        """Read-only registry of fields added by ``annotate_relationships``.

        Kept separate from entity ``derived_fields`` so edge and node
        property names can overlap without muddying provenance.
        """
        return MappingProxyType(self._relationship_derived_fields)

    @property
    def default_index_path(self) -> Path:
        """Conventional location for this graph's index, derived from CWD.

        Single-source graphs use ``<cwd>/.crategraph/<source_id>.db``;
        multi-source graphs use ``<cwd>/.crategraph/corpus-<sha8>.db``
        where the hash is over the sorted source ids, so the same
        ``Crate(*paths)`` call always produces the same default path.

        ``build_semantic_index()`` and the search/records methods fall
        back to this when ``store_path`` isn't supplied. Add
        ``.crategraph/`` to your gitignore to keep indexes out of version
        control.

        Raises ``ValueError`` if the graph has no source — there's
        nothing to index.
        """
        srcs = self.sources
        if not srcs:
            msg = (
                "Cannot derive a default index path: this graph has no "
                "source. Pass an explicit `store_path` to build_semantic_index()."
            )
            raise ValueError(msg)
        if len(srcs) == 1:
            name = srcs[0]
        else:
            import hashlib

            digest = hashlib.sha256("|".join(srcs).encode()).hexdigest()[:8]
            name = f"corpus-{digest}"
        return Path.cwd() / ".crategraph" / f"{name}.db"

    def __repr__(self) -> str:
        n_ent = len(self._entities)
        n_rel = len(self._relationships)
        srcs = self.sources
        if len(srcs) > 1:
            source_part = f", sources=[{', '.join(repr(s) for s in srcs)}]"
        elif self.source:
            source_part = f", source={self.source!r}"
        else:
            source_part = ""
        return f"Graph({n_ent} entities, {n_rel} relationships{source_part})"

    def _repr_html_(self) -> str:
        """Compact HTML representation for Jupyter notebooks."""
        from collections import Counter
        from html import escape

        from crategraph.core._html import text_pre

        n_ent = len(self._entities)
        n_rel = len(self._relationships)
        source_part = f" ({escape(str(self.source))})" if self.source else ""

        line1 = f"Graph: {n_ent} entities, {n_rel} relationships{source_part}"

        # Sources line for multi-crate graphs.
        srcs = self.sources
        if len(srcs) > 1:
            line1 += f"\nSources: {', '.join(escape(s) for s in srcs)}"

        # Top entity types
        type_counts = Counter(e.type for e in self._entities.values())
        top_n = 4
        top_types = type_counts.most_common(top_n)
        remaining = len(type_counts) - top_n
        parts = [f"{escape(t)} ({c})" for t, c in top_types]
        if remaining > 0:
            parts.append(f"+{remaining} more")
        line2 = f"Types: {', '.join(parts)}" if parts else ""

        text = line1
        if line2:
            text += f"\n{line2}"

        return text_pre(text)

    def get(self, entity_id: str) -> EntityView:
        """Return a graph-aware :class:`EntityView` for a single entity by ID.

        Raises ``KeyError`` with a clear message if the ID doesn't exist.
        Use ``.entity`` on the result for the bare :class:`Entity` record.
        """
        from crategraph.core.views import EntityView

        try:
            entity = self._entities[entity_id]
        except KeyError:
            msg = f'No entity with id "{entity_id}" in this graph.'
            raise KeyError(msg) from None
        return EntityView(entity, self)

    # --- Public export methods ---

    def to_networkx(self, *, copy: bool = True) -> nx.MultiDiGraph:
        """Return a NetworkX ``MultiDiGraph`` view of this graph.

        The returned graph is rebuilt from ``self._entities`` and
        ``self._relationships`` so callers receive a regular NetworkX graph
        with one edge per :class:`Relationship`. Edge keys are assigned by
        ``MultiDiGraph`` so same-type parallel edges between the same
        endpoints survive.

        With ``copy=True`` (default), each node's ``entity`` attribute and
        each edge's ``relationship`` attribute are detached copies whose
        nested ``properties`` are safe to mutate without affecting this
        ``Graph``. With ``copy=False``, the original ``Entity`` /
        ``Relationship`` objects are attached directly; the caller must not
        mutate their nested ``properties``.
        """
        import dataclasses

        nxg = nx.MultiDiGraph()
        for entity in self._entities.values():
            attached = (
                dataclasses.replace(entity, properties=_copy_properties(entity.properties))
                if copy
                else entity
            )
            nxg.add_node(entity.id, entity=attached)
        for rel in self.relationships:
            attached = (
                dataclasses.replace(rel, properties=_copy_properties(rel.properties))
                if copy
                else rel
            )
            nxg.add_edge(rel.source, rel.target, relationship=attached)
        return nxg

    def entity_records(self, columns: Sequence[str] | None = None) -> Records:
        """Return one ``dict`` per entity with native Python values.

        Keys: ``id``, ``label``, ``type``, ``types`` first, then
        non-colliding properties sorted alphabetically, then any
        properties whose names collide with a promoted key emitted as
        ``prop_<key>``. ``label`` falls back through ``name`` →
        ``title`` → ``id``. ``type`` is the first entry of ``types``
        (or empty string if untyped). ``types`` is a list of strings.
        Property values are deep-copied so callers can mutate returned
        records without touching graph state.

        Pass *columns* (positional) to project to just those keys, in that
        order — naming them as they appear above. Every requested column is
        present in every record (``None`` where an entity lacks it), so the
        result keeps a stable schema. Selecting at the source avoids a
        post-hoc DataFrame projection just to view a few fields::

            graph.entity_records(["id", "label", "type"])

        Wrap with your DataFrame library of choice:

        ::

            import pandas as pd
            df = pd.DataFrame(graph.entity_records())

            # or polars / pyarrow:
            # pl.DataFrame(graph.entity_records())
            # pa.Table.from_pylist(graph.entity_records())
        """
        from crategraph.core import records

        return records.entity_records(self, columns)

    def relationship_records(self, columns: Sequence[str] | None = None) -> Records:
        """Return one ``dict`` per relationship with native Python values.

        Keys: ``source``, ``target``, ``type``, ``rel_id`` first, then
        non-colliding properties sorted alphabetically, then any
        properties whose names collide with a promoted key emitted as
        ``prop_<key>``. ``rel_id`` is ``None`` for inline (non-reified)
        relationships and a string for reified ones — the distinction
        is preserved here, unlike the CSV writer which collapses both
        to an empty string. Property values are deep-copied so callers
        can mutate returned records without touching graph state.

        Pass *columns* (positional) to project to just those keys (same
        rules as :meth:`entity_records`).

        Wrap with your DataFrame library of choice:

        ::

            import pandas as pd
            df = pd.DataFrame(graph.relationship_records())

            # or polars / pyarrow:
            # pl.DataFrame(graph.relationship_records())
            # pa.Table.from_pylist(graph.relationship_records())
        """
        from crategraph.core import records

        return records.relationship_records(self, columns)

    def entity_counts(self, field: str) -> Records:
        """Count entities by *field*, returning ``Records`` of ``{field, count}``.

        *field* names a column as it appears in :meth:`entity_records`
        (``id``/``label``/``type``/``types`` or a property; a property
        colliding with a promoted name is ``prop_<key>``), so the counts
        always agree with the records. List-valued columns explode —
        ``entity_counts("types")`` counts each type membership, so totals
        may exceed ``len(self)``. ``None``/absent values are skipped and
        rows are sorted count-descending.

        Counts the current view, so ``crate.select(...).entity_counts(...)``
        tallies only the subgraph. Derived columns work too —
        ``annotate_entities(...).entity_counts("...")``.
        """
        from crategraph.core import records

        return records.entity_counts(self, field)

    def relationship_counts(self, field: str) -> Records:
        """Count relationships by *field*, returning ``Records`` of ``{field, count}``.

        *field* names a column as it appears in
        :meth:`relationship_records` (``source``/``target``/``type``/
        ``rel_id`` or a property). Same semantics as :meth:`entity_counts`.
        """
        from crategraph.core import records

        return records.relationship_counts(self, field)

    def write(
        self,
        path: str,
        *,
        format: str,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> None:
        """Serialise this graph in *format* to *path*.

        Args:
            path: The destination path. Interpretation (file vs directory) is
                writer-specific.
            format: Required. Name of a registered writer format (e.g.
                ``"graphml"``, ``"csv"``).
            overwrite: If ``False`` (default), the writer raises
                ``FileExistsError`` when *path* already exists. Set ``True`` to
                allow overwriting.
            **kwargs: Forwarded to the concrete writer.
        """
        from crategraph.writers import get_writer

        writer_cls = get_writer(format)
        writer_cls().write(self, path, overwrite=overwrite, **kwargs)

    # --- Analysis methods (delegated to core/analysis.py) ---

    def summary(self) -> analysis.GraphSummary:
        """Return a structured summary of type/relationship counts."""
        return analysis.summary(self)

    def most_connected(
        self, *, n: int = 10, entity_types: list[str] | None = None
    ) -> list[tuple[EntityView, int]]:
        """Return the top *n* entities by number of connections, as views.

        Each result is ``(EntityView, degree)``; use ``.entity`` on a view
        for the bare record.
        """
        from crategraph.core.views import EntityView

        ranked = analysis.most_connected(self, n=n, entity_types=entity_types)
        return [(EntityView(entity, self), degree) for entity, degree in ranked]

    def profile(self) -> analysis.GraphProfile:
        """Return a structural profile with density, components, degree stats."""
        return analysis.profile(self)

    def coverage(
        self,
        *,
        inline_relations: bool | list[str] = False,
        min_occurrences: int = 5,
    ) -> list[CoverageResult]:
        """Analyse relationship coverage across entity types."""
        return analysis.coverage(
            self,
            inline_relations=inline_relations,
            min_occurrences=min_occurrences,
        )

    # --- Presentation methods (delegated to core/presentation.py) ---

    def layout(
        self,
        *,
        engine: str | None = None,
        gravity: float | None = None,
        iterations: int | None = None,
        layout_settings: dict[str, Any] | None = None,
        progress: bool = False,
    ) -> dict[str, tuple[float, float]]:
        """Compute 2D node positions for visualisation.

        See :func:`crategraph.core.presentation.layout` for the full
        parameter documentation.
        """
        return presentation.layout(
            self,
            engine=engine,
            gravity=gravity,
            iterations=iterations,
            layout_settings=layout_settings,
            progress=progress,
        )

    def visualise(
        self,
        *,
        renderer: str = "2d",
        colour_by: str = "type",
        size_by: str = "connections",
        edge_width: int | float | str | None = None,
        height: str = "100vh",
        width: str = "100%",
        filepath: str | None = None,
        collapse_edges: bool = False,
        progress: bool = True,
        engine: str | None = None,
        gravity: float | None = None,
        iterations: int | None = None,
        layout_settings: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Render the graph as a network visualisation."""
        return presentation.visualise(
            self,
            renderer=renderer,
            colour_by=colour_by,
            size_by=size_by,
            edge_width=edge_width,
            height=height,
            width=width,
            filepath=filepath,
            collapse_edges=collapse_edges,
            progress=progress,
            engine=engine,
            gravity=gravity,
            iterations=iterations,
            layout_settings=layout_settings,
            **kwargs,
        )

    def glimpse(self, *, filepath: str | None = None) -> Any:
        """Inline snapshot of the type-level graph structure."""
        return presentation.glimpse(self, filepath=filepath)

    def gallery(
        self,
        *,
        caption: str | None = "label",
        hover: str | Sequence[str] | None = None,
        columns: int = 4,
        limit: int | None = 48,
        filepath: str | None = None,
    ) -> Any:
        """Lay the graph's image-bearing entities out as a thumbnail gallery.

        Every image is embedded inline, so ``limit`` (default ``48``) bounds the
        output size and warns when more images are available; pass ``limit=None``
        to embed them all, or filter the graph first (e.g. ``where(...)``).
        """
        return presentation.gallery(
            self,
            caption=caption,
            hover=hover,
            columns=columns,
            limit=limit,
            filepath=filepath,
        )

    def inspect(self, entity: Entity | str | EntityView) -> FileInfo:
        """Inspect the data file associated with an entity."""
        return presentation.inspect(self, entity)

    def view(self, entity: Entity | str | EntityView) -> ViewInfo:
        """View the data file associated with an entity."""
        return presentation.view(self, entity)

    def text_records(
        self,
        *,
        store_path: str | Path | None = None,
        source_kind: str = "file",
        text_properties: Sequence[str] | None = None,
        include_properties: Sequence[str] | bool = False,
        filters: Mapping[str, Any] | None = None,
        restrict_to_view: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Yield one text record per source unit in the graph.

        Each record is a dict with keys ``source_id``, ``entity_id``,
        ``source_kind`` (``"file"`` or ``"properties"``),
        ``entity_types``, ``text``, plus any requested entity properties.
        Generator — peak memory is one record at a time.

        ``source_kind`` controls which text units are yielded:
        ``"file"`` (default), ``"properties"``, or ``"all"``. An explicit
        ``filters["source_kind"]`` overrides this convenience argument.

        ``include_properties`` optionally copies entity properties into
        each output record. Pass a sequence of property names, or ``True``
        to include all *public* entity properties (internal ``_``-prefixed
        loader flags such as ``_is_root`` are excluded; an explicit
        allowlist is honoured verbatim). Defaults to ``False`` so the
        record schema remains compact and stable.

        ``store_path`` switches between two read paths:

        - **Default (``store_path=None``)**: live extraction. Walks
          entities and pulls file content via the registered
          ``Inspector``. Slow on big corpora; always reflects current
          files on disk. Yields no ``token_count``.
        - **Cached (``store_path=...``)**: reads ``text_units`` from
          a previously-built index. Microseconds per record;
          reflects the corpus as of the last ``build_semantic_index``.
          Yields ``token_count`` (the indexer's tokenizer view).
          Requires the ``[index]`` extra.

        Filters: ``source_id``, ``entity_id``, ``entity_types``,
        ``source_kind`` (any-of within each key).

        ``restrict_to_view`` (default ``True``) intersects with the
        current graph view: a filtered subgraph (``crate.where(...)``)
        only yields records for its own entities, on either path. The
        live path always walks ``self.entities``; the cached path
        injects an ``entity_id`` filter intersected with the view so
        results are consistent. Pass ``False`` to read every row in
        the index regardless of view.

        See :func:`crategraph.core.text.text_records` for the live
        implementation.
        """
        merged_filters = self._merge_text_record_filters(filters, source_kind)

        if store_path is not None:
            return self._cached_text_records(
                store_path,
                merged_filters,
                include_properties=include_properties,
                restrict_to_view=restrict_to_view,
            )

        from crategraph.core.text import DEFAULT_TEXT_PROPERTIES, text_records

        # Distinguish ``None`` (use defaults) from ``[]`` (explicit empty —
        # caller wants to suppress property records entirely). Don't use
        # ``or`` here: an empty sequence is falsy.
        if text_properties is None:
            text_properties = DEFAULT_TEXT_PROPERTIES
        return text_records(
            self,
            text_properties=text_properties,
            include_properties=include_properties,
            filters=merged_filters,
        )

    @staticmethod
    def _merge_text_record_filters(
        filters: Mapping[str, Any] | None,
        source_kind: str,
    ) -> dict[str, Any] | None:
        """Apply the text-record source-kind default without clobbering filters."""
        if source_kind not in {"file", "properties", "all"}:
            msg = "source_kind must be 'file', 'properties', or 'all'."
            raise ValueError(msg)

        merged = dict(filters) if filters else {}
        if "source_kind" in merged:
            return merged
        if source_kind == "all":
            return merged or None
        merged["source_kind"] = [source_kind]
        return merged

    def chunk_records(
        self,
        query: str | None = None,
        *,
        k: int = 10,
        store_path: str | Path | None = None,
        filters: Mapping[str, Any] | None = None,
        restrict_to_view: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Yield one record per indexed chunk.

        Requires the ``[index]`` extra and a previously-built index.
        ``store_path`` defaults to :attr:`default_index_path`; raises
        ``FileNotFoundError`` if no index exists at the default.

        Two modes, switched by ``query``:

        - **Unranked iteration (``query=None``, default)**: yields every
          chunk in the index in stable order (by source_id, entity_id,
          source_kind, chunk_index). Streaming. For analytical use —
          inspecting what's there, debugging, custom pipelines.
        - **Ranked retrieval (``query="..."``)**: runs the index's
          embedding model on the query and yields the top ``k`` chunks
          by relevance, with a ``score`` field on each record (higher is
          better). For RAG-style use.

        Each record is a dict with keys ``source_id``, ``entity_id``,
        ``source_kind``, ``entity_types``, ``chunk_index``,
        ``char_start``, ``char_end``, ``token_count``, ``text`` (text
        reconstructed at query time from ``text_units`` via SUBSTR),
        plus ``score`` when ``query`` is provided.

        Filters: ``source_id``, ``entity_id``, ``entity_types``,
        ``source_kind``.

        ``restrict_to_view`` (default ``True``) intersects with the
        current graph view, so a filtered subgraph only yields chunks
        for its own entities. Pass ``False`` to read every chunk in
        the index regardless of view.
        """
        try:
            from crategraph.index.store import Store
        except ImportError:
            msg = (
                "chunk_records requires the [index] extra. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None

        resolved = self._resolve_index_path(store_path, must_exist=True)
        merged = self._apply_view_restriction(filters, restrict_to_view)
        if merged is None:
            return iter(())

        if query is not None:
            return self._ranked_chunk_records(resolved, query, k=k, filters=merged)

        def _iter() -> Iterator[dict[str, Any]]:
            with Store(resolved) as store:
                yield from store.iter_chunk_records(filters=merged)

        return _iter()

    def _ranked_chunk_records(
        self,
        store_path: Path,
        query: str,
        *,
        k: int,
        filters: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        """Embed *query* and yield the top *k* chunks as records, ranked by score."""
        try:
            from crategraph.index import Searcher
        except ImportError:
            msg = (
                "Ranked chunk_records requires the [index] extra. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None

        # Sanity-check that the index file looks like it belongs to
        # this graph's sources before running retrieval.
        self._warn_if_unrelated_index(store_path)

        searcher = Searcher(store_path)
        hits = searcher.search(query, k=k, filters=filters)

        def _iter() -> Iterator[dict[str, Any]]:
            for hit in hits:
                yield {
                    "source_id": hit.source_id,
                    "entity_id": hit.entity_id,
                    "entity_types": hit.entity_types,
                    "source_kind": hit.source_kind,
                    "chunk_index": hit.chunk_index,
                    "char_start": hit.char_start,
                    "char_end": hit.char_end,
                    "token_count": hit.token_count,
                    "text": hit.text,
                    "score": hit.score,
                }

        return _iter()

    def _cached_text_records(
        self,
        store_path: str | Path,
        filters: Mapping[str, Any] | None,
        *,
        include_properties: Sequence[str] | bool,
        restrict_to_view: bool,
    ) -> Iterator[dict[str, Any]]:
        """Stream text_units rows from a built index. Lazy-imports the index module."""
        try:
            from crategraph.index.store import Store
        except ImportError:
            msg = (
                "Cached text_records reads require the [index] extra. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None

        merged = self._apply_view_restriction(filters, restrict_to_view)
        if merged is None:
            return iter(())

        def _iter() -> Iterator[dict[str, Any]]:
            from crategraph.core.text import enrich_record_with_entity_properties

            with Store(store_path) as store:
                for record in store.iter_text_records(filters=merged):
                    entity = self._entities.get(record["entity_id"])
                    if entity is None:
                        yield record
                    else:
                        yield enrich_record_with_entity_properties(
                            record,
                            entity,
                            include_properties,
                        )

        return _iter()

    def _resolve_index_path(
        self,
        store_path: str | Path | None,
        *,
        must_exist: bool,
    ) -> Path:
        """Resolve store_path to a concrete Path, falling back to
        :attr:`default_index_path` when ``store_path`` is ``None``.

        With ``must_exist=True`` (read-side methods), raises a friendly
        ``FileNotFoundError`` when the default location has no index
        file yet. Build-side methods pass ``must_exist=False`` since
        they create the file.
        """
        if store_path is not None:
            return Path(store_path)
        default = self.default_index_path
        if must_exist and not default.exists():
            msg = (
                f"No index at default location {default}. "
                "Run `graph.build_semantic_index()` first, or pass an "
                "explicit `store_path=` to use a different location."
            )
            raise FileNotFoundError(msg)
        return default

    def _apply_view_restriction(
        self,
        filters: Mapping[str, Any] | None,
        restrict_to_view: bool,
    ) -> dict[str, Any] | None:
        """Build the filter dict for a cached read, optionally intersecting
        an ``entity_id`` filter with the current graph view.

        Returns ``None`` when the intersection of a user-supplied
        ``entity_id`` filter with the view is empty (caller should
        short-circuit to no results). An empty dict is distinct: it
        means "no constraints at all" and is passed through unchanged.
        """
        merged: dict[str, Any] = dict(filters) if filters else {}
        if not restrict_to_view:
            return merged
        if "entity_id" in merged:
            # User supplied entity_id — intersect with current view to
            # prevent bypass. Honours user intent on root graphs too.
            view_ids = set(self._entities.keys())
            user_ids = set(merged["entity_id"])
            intersected = list(user_ids & view_ids)
            if not intersected:
                return None
            merged["entity_id"] = intersected
        elif self._root is not self:
            # Derived view (filtered subgraph): inject entity_id filter
            # to honour the view's scope.
            #
            # On a top-level graph, *don't* inject — the filter would
            # constrain nothing (every entity is in scope) and could
            # exceed SQLite's bind-variable limit on large crates
            # (default 999, tens-of-thousands on recent builds; even
            # below that, it forces the slower over-fetch path for no
            # gain).
            merged["entity_id"] = list(self._entities.keys())
        return merged

    def build_semantic_index(
        self,
        store_path: str | Path | None = None,
        **kwargs: Any,
    ) -> Any:
        """Build a semantic search index over this graph.

        Requires the ``[index]`` extra::

            pip install crategraph[index]

        ``store_path`` defaults to :attr:`default_index_path` —
        ``<cwd>/.crategraph/<source_id_or_corpus_hash>.db``. Build is
        idempotent: re-running with the same config and unchanged
        sources is a no-op.

        See :class:`crategraph.index.Indexer` for full options. Common
        keyword arguments: ``model``, ``chunk_tokens``, ``chunk_overlap``,
        ``text_properties``, ``batch_size``, ``progress``.

        Returns an :class:`~crategraph.index.IndexerStats` describing
        what changed.
        """
        try:
            from crategraph.index import Indexer
        except ImportError:
            msg = (
                "Semantic indexing requires the [index] extra. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None
        resolved = self._resolve_index_path(store_path, must_exist=False)
        return Indexer(self, resolved, **kwargs).build()

    def _semantic_search_subgraph(
        self,
        query: str,
        *,
        k: int,
        store_path: str | Path | None,
        filters: Mapping[str, Any] | None,
        restrict_to_view: bool,
    ) -> Graph:
        """Roll ranked chunk hits up to a top-*k* entity subgraph.

        Oversamples chunks (5x) so dedup-to-entity yields enough unique
        candidates, picks the best score per entity, returns the top *k*.

        The subgraph is built from a base that depends on
        ``restrict_to_view``:

        - ``True`` (default) — build from ``self``. Hit ids are already
          intersected with ``self._entities`` upstream, so they're
          guaranteed safe; this preserves whatever relationship-level
          filtering the current view applied (e.g. ``crate.pattern(...)``
          or ``select(relationship_types=...)``).
        - ``False`` — build from ``self._root``. Hits may be outside
          ``self._entities``; ``_build_derived_graph`` filters node ids
          through ``self._entities`` and would silently drop them. The
          root carries the full set.
        """
        records = self.chunk_records(
            query,
            k=k * 5,
            store_path=store_path,
            filters=filters,
            restrict_to_view=restrict_to_view,
        )
        best: dict[str, float] = {}
        for record in records:
            eid = record["entity_id"]
            score = record["score"]
            if score > best.get(eid, float("-inf")):
                best[eid] = score
        top_ids = sorted(best, key=lambda eid: best[eid], reverse=True)[:k]
        base = self if restrict_to_view else self._root
        return base._subgraph(set(top_ids))

    def _warn_if_unrelated_index(self, store_path: str | Path) -> None:
        """Emit a UserWarning when this graph's sources don't overlap with
        the index's known sources — likely sign of the wrong index file.

        Stack level reaches the user's call site rather than the
        internal generator wrapper, so the warning location is useful.
        """
        import warnings

        try:
            from crategraph.index import Searcher
        except ImportError:
            return

        graph_sources = set(self.sources)
        if not graph_sources:
            return
        try:
            indexed = set(Searcher(store_path).known_source_ids())
        except (FileNotFoundError, ValueError):
            return
        if indexed and not (graph_sources & indexed):
            warnings.warn(
                f"Graph sources {sorted(graph_sources)} don't overlap "
                f"with index sources {sorted(indexed)}; "
                "this may be the wrong index file.",
                stacklevel=3,
            )

    # --- Transform methods ---

    def detect_communities(self, *, resolution: float = 1.0, seed: int | None = None) -> Graph:
        """Return a new graph with a ``"community"`` property on each entity.

        Uses the Louvain algorithm via :func:`analysis.detect_communities`.
        """
        return analysis.detect_communities_transform(
            self,
            resolution=resolution,
            seed=seed,
        )

    def merge_nodes(self, *, by: str) -> Graph:
        """Aggregate nodes by a property, returning a collapsed graph."""
        return transforms.merge_nodes(self, by=by)

    def convert_dates(
        self,
        *,
        start: str | Sequence[str] | None = None,
        end: str | Sequence[str] | None = None,
        parser: Callable[[str], Any] | None = None,
        report: bool = True,
    ) -> Graph:
        """Parse messy date strings into ``start_date``/``end_date``/``year`` columns.

        Returns a new graph where every entity with a parseable date field gains
        ``start_date``, ``end_date`` (ISO strings), ``year`` (int),
        ``date_precision``, ``date_circa`` and ``date_uncertain``. The new
        columns are recorded in :attr:`derived_fields`.

        Note the deliberate type split: the materialised ``start_date``/
        ``end_date`` columns are ISO strings (writer- and DataFrame-friendly),
        whereas the :class:`~crategraph.core.views.EntityView` accessors
        (``e.start_date``/``e.end_date``) return ``datetime.date`` objects for
        in-memory use.

        Args:
            start: Optional field name (or ordered list) to read the start/point
                date from. When given, only this field is consulted — the default
                content cascade is fully bypassed (no provenance fallback).
            end: Optional field name (or ordered list) for the end date.
            parser: Optional per-string parser (default the built-in
                conservative engine); swap in a more aggressive coercer.
            report: When ``True`` (default), print a coverage / temporal-gaps
                summary — how many entities with date fields parsed, with a
                sample of the unparseable ones.
        """
        return transforms.convert_dates(self, start=start, end=end, parser=parser, report=report)

    def annotate_entities(self, **fields: Callable[[EntityView], Any]) -> Graph:
        """Derive a property per entity from callables; returns a new Graph.

        Each keyword argument names a new property; its callable receives
        an :class:`EntityView` over the source graph and returns the value
        for that entity. Callables are independent — fields in one call
        do not see each other. Added field names are recorded in
        :attr:`derived_fields` so derived columns stay distinguishable
        from native crate metadata, and overlapping names overwrite
        existing properties on the returned graph.

        Chain :meth:`where` straight after to filter on the new fields.

        Args:
            **fields: ``name=callable`` pairs. Each callable takes an
                ``EntityView`` and returns the value to attach as
                ``name``. Use ``.related(rel)``, ``.has(rel)``,
                ``.get(key)``, ``.type``, ``.id``, etc. on the view.

        Examples::

            tagged = crate.annotate_entities(
                genre=lambda e: e.related("ldac:linguisticGenre").join("name"),
                has_genre=lambda e: e.has("ldac:linguisticGenre"),
                is_plain_text=lambda e: "File" in e.types and e.id.endswith("-plain.txt"),
            )
            reports = tagged.where(genre="Report", is_plain_text=True)
        """
        return transforms.annotate_entities(self, **fields)

    def annotate_relationships(
        self,
        **fields: Callable[[RelationshipView], Any],
    ) -> Graph:
        """Derive a property per relationship from callables; returns a new Graph.

        Each keyword argument names a new property; its callable receives
        a :class:`RelationshipView` over the source graph and returns the
        value for that relationship. Callables are independent — fields
        in one call do not see each other. Added field names are recorded
        in :attr:`relationship_derived_fields`, kept separate from entity
        :attr:`derived_fields` so edge and node property names can overlap
        without muddying provenance.

        Args:
            **fields: ``name=callable`` pairs. Each callable takes a
                ``RelationshipView`` and returns the value to attach as
                ``name``. Use ``.source``, ``.target`` (both
                ``EntityView``), ``.type``, ``.source_id``,
                ``.target_id``, ``.get(key)`` on the view.

        Examples::

            labelled = crate.annotate_relationships(
                source_type=lambda r: r.source.types[0],
                target_type=lambda r: r.target.types[0],
                is_authorship=lambda r: r.type == "author",
            )
            labelled.relationship_records()[0]  # includes the new fields
        """
        return transforms.annotate_relationships(self, **fields)

    def simplify(
        self,
        *,
        min_connections: int | None = None,
    ) -> Graph:
        """Remove peripheral nodes to reveal the structural backbone."""
        return transforms.simplify(self, min_connections=min_connections)

    def collapse_edges(self) -> Graph:
        """Collapse parallel edges between node pairs into single summary edges."""
        return transforms.collapse_edges(self)

    # --- Filtering methods (delegated to core/filtering.py) ---

    def select(
        self,
        *,
        entity_types: list[str] | None = None,
        relationship_types: list[str] | str | None = None,
        time_range: tuple[int, int] | None = None,
        min_connections: int | None = None,
        max_connections: int | None = None,
        source: str | None = None,
        id: str | None = None,
    ) -> Graph:
        """Filter by graph structure — type, time, source, connectivity."""
        return filtering.select(
            self,
            entity_types=entity_types,
            relationship_types=relationship_types,
            time_range=time_range,
            min_connections=min_connections,
            max_connections=max_connections,
            source=source,
            id=id,
        )

    def exclude(
        self,
        *,
        entity_types: list[str] | str | None = None,
        relationship_types: list[str] | str | None = None,
        drop_isolated: bool = True,
    ) -> Graph:
        """Filter out matching entities and relationships."""
        return filtering.exclude(
            self,
            entity_types=entity_types,
            relationship_types=relationship_types,
            drop_isolated=drop_isolated,
        )

    def drop(self, values: str | list[str], *, property: str | None = None) -> Graph:
        """Remove entities whose properties contain any of the given values."""
        return filtering.drop(self, values, property=property)

    def subtract(self, other: Graph) -> Graph:
        """Return a new Graph with all entities from *other* removed."""
        return filtering.subtract(self, other)

    def where(self, **kwargs: Any) -> Graph:
        """Filter by entity property values."""
        return filtering.where(self, **kwargs)

    def search(
        self,
        query: str,
        mode: str = "fuzzy",
        *,
        # Fuzzy-mode kwargs (ignored by other modes)
        properties: list[str] | None = None,
        threshold: int = 80,
        top_n: int = 10,
        # Index-backed mode kwargs (ignored by fuzzy)
        k: int = 10,
        store_path: str | Path | None = None,
        filters: Mapping[str, Any] | None = None,
        restrict_to_view: bool = True,
    ) -> Graph:
        """Search this graph and return a matching subgraph.

        Modes:

        - ``"fuzzy"`` (default): rapidfuzz match over entity properties.
          Uses ``properties``, ``threshold``, ``top_n``. No index required.
        - ``"semantic"``: embedding-backed retrieval via the index. Uses
          ``k``, ``store_path``, ``filters``, ``restrict_to_view``.
          Requires the ``[index]`` extra and a previously-built index;
          ``store_path`` defaults to :attr:`default_index_path`.

        Both modes return a :class:`Graph` (subgraph of matching
        entities) so they compose with the rest of the pipeline
        (``where``, ``expand``, etc.). For chunk-level retrieval with
        scores, use :meth:`chunk_records` (returns dicts) or
        :class:`crategraph.index.Searcher` (typed ``SearchHit`` objects).

        ``mode="keyword"`` and ``mode="hybrid"`` are reserved for a
        future FTS5-backed implementation.
        """
        if mode == "fuzzy":
            return filtering.search(
                self, query, properties=properties, threshold=threshold, top_n=top_n
            )
        if mode == "semantic":
            return self._semantic_search_subgraph(
                query,
                k=k,
                store_path=store_path,
                filters=filters,
                restrict_to_view=restrict_to_view,
            )
        msg = (
            f"Unknown search mode {mode!r}. "
            "Supported: 'fuzzy' (default), 'semantic'. "
            "'keyword' and 'hybrid' are forthcoming."
        )
        raise ValueError(msg)

    def expand(
        self,
        *,
        depth: int = 1,
        entity_types: list[str] | None = None,
        via: str | None = None,
    ) -> Graph:
        """Grow this selection outward to include connected neighbours."""
        return filtering.expand(self, depth=depth, entity_types=entity_types, via=via)

    def pattern(
        self,
        *,
        from_type: str | None = None,
        via: str | None = None,
        to_type: str | None = None,
    ) -> Graph:
        """Match relationships by source type, relationship type, and/or target type."""
        return filtering.pattern(self, from_type=from_type, via=via, to_type=to_type)

    def query(self, cypher: str) -> Graph:
        """Run a Cypher query and return a subgraph of matched entities."""
        return filtering.query(self, cypher)

    # --- Private graph helpers ---

    def _add_node(self, entity: Entity) -> None:
        """Add or replace an entity in the graph."""
        self._entities[entity.id] = entity
        self._entity_types_cache = None  # invalidate cached entity types
        self._source_names = None  # lazily rebuilt from _entities on next access

    def _add_edge(self, relationship: Relationship) -> None:
        """Add a relationship to the graph."""
        missing = [
            entity_id
            for entity_id in (relationship.source, relationship.target)
            if entity_id not in self._entities
        ]
        if missing:
            which = "endpoint" if len(missing) == 1 else "endpoints"
            missing_str = ", ".join(repr(entity_id) for entity_id in missing)
            warnings.warn(
                f"Skipped relationship {relationship.type!r} from "
                f"{relationship.source!r} to {relationship.target!r}: "
                f"missing {which} {missing_str}.",
                stacklevel=2,
            )
            return
        self._relationships.append(relationship)
        # invalidate caches derived from _relationships
        self._rel_adjacency = None
        self._relationship_types_cache = None

    def _display_name(self, entity_id: str) -> str:
        """Return the best display name for an entity ID."""
        entity = self._entities.get(entity_id)
        return entity.name if entity else entity_id

    def _neighbours(self, node_id: str) -> set[str]:
        """Return IDs of all nodes adjacent to *node_id* (in either direction)."""
        if node_id not in self._entities:
            return set()
        out_by_source, in_by_target = self._relationship_adjacency()
        return {r.target for r in out_by_source.get(node_id, [])} | {
            r.source for r in in_by_target.get(node_id, [])
        }

    def _coerce_entity(self, entity: Entity | str | EntityView) -> Entity:
        """Resolve an entity object, view, or ID string to a bare Entity."""
        from crategraph.core.views import EntityView

        if isinstance(entity, EntityView):
            return entity.entity
        if isinstance(entity, str):
            try:
                return self._entities[entity]
            except KeyError:
                msg = f'No entity with id "{entity}" in this graph.'
                raise KeyError(msg) from None
        return entity

    def _require_local_entity_file(self, entity: Entity, *, action: str) -> tuple[str, Path]:
        """Resolve and validate the local file path for an entity."""
        entity_id = entity_raw_id(entity)
        if is_contextual_entity(entity):
            msg = (
                f"Entity {entity.id!r} is a contextual entity "
                f"— {action}() works with data entities that point to local files."
            )
            raise ValueError(msg)

        crate_root = entity.source or self.source
        if crate_root is None:
            msg = f"Cannot resolve file path for {entity.id!r} — no crate source directory is set."
            raise ValueError(msg)

        file_path = resolve_entity_path(entity, fallback_source=self.source)
        if file_path is None:
            crate_root_resolved = Path(crate_root).resolve(strict=False)
            msg = (
                f"Entity ID {entity_id!r} resolves outside the crate directory "
                f"{str(crate_root_resolved)!r}."
            )
            raise ValueError(msg)

        if not file_path.is_file():
            msg = (
                f"Cannot find file {entity_id!r} in crate at {crate_root!r}. "
                f"Check the entity ID refers to a local file."
            )
            raise FileNotFoundError(msg)

        return entity_id, file_path

    def _build_derived_graph(
        self,
        *,
        node_ids: set[str],
        entities: dict[str, Entity] | None = None,
        relationships: list[Relationship] | None = None,
    ) -> Graph:
        """Build a derived graph while keeping internal state aligned."""
        derived = Graph.__new__(Graph)
        derived.source = self.source
        derived.metadata = dict(self.metadata)
        derived._entities = (
            entities
            if entities is not None
            else {nid: self._entities[nid] for nid in node_ids if nid in self._entities}
        )
        candidate_relationships = (
            relationships
            if relationships is not None
            else [r for r in self._relationships if r.source in node_ids and r.target in node_ids]
        )
        derived._relationships = [
            r
            for r in candidate_relationships
            if r.source in derived._entities and r.target in derived._entities
        ]
        derived._source_names = None  # lazily rebuilt from derived._entities
        derived._root = self._root
        derived._simplification_k = None
        derived._derived_fields = dict(self._derived_fields)
        derived._relationship_derived_fields = dict(self._relationship_derived_fields)
        # caches rebuilt lazily from the derived graph's own nodes/edges
        derived._rel_adjacency = None
        derived._entity_types_cache = None
        derived._relationship_types_cache = None
        return derived

    def _subgraph(self, node_ids: set[str]) -> Graph:
        """Return a new Graph containing only the specified nodes and their mutual edges."""
        return self._build_derived_graph(node_ids=node_ids)

    def _relationship_adjacency(
        self,
    ) -> tuple[dict[str, list[Relationship]], dict[str, list[Relationship]]]:
        """Lazily build and cache per-endpoint adjacency indexes.

        Returns ``(out_by_source, in_by_target)`` mapping each entity id
        to the relationships where it is the source / target. Buckets
        preserve ``_relationships`` (RO-Crate source) order. This turns
        ``_related_ids`` from an O(E) scan per call into O(degree),
        which matters when annotating relationship-following fields
        across every entity (previously O(N*E)). Invalidated by
        ``_add_edge``; derived graphs rebuild from their own edges.
        """
        if self._rel_adjacency is None:
            out_by_source: dict[str, list[Relationship]] = {}
            in_by_target: dict[str, list[Relationship]] = {}
            for r in self._relationships:
                out_by_source.setdefault(r.source, []).append(r)
                in_by_target.setdefault(r.target, []).append(r)
            self._rel_adjacency = (out_by_source, in_by_target)
        return self._rel_adjacency

    def _related_ids(
        self,
        entity_id: str,
        rel: str,
        direction: str = "out",
    ) -> list[str]:
        """Return ids of entities related to *entity_id* via *rel*.

        Validates *rel* against this graph's relationship types — an
        unknown type raises ``ValueError`` (parity with ``select`` /
        ``exclude``). ``direction``: ``"out"`` (this entity is the
        source), ``"in"`` (this entity is the target), or ``"any"``
        (out then in). Results are deduplicated by id, preserving
        ``_relationships`` (RO-Crate source) order, and restricted to
        ids present in this graph.
        """
        self.relationship_types.validate(rel)
        out_by_source, in_by_target = self._relationship_adjacency()
        out_ids = [r.target for r in out_by_source.get(entity_id, ()) if r.type == rel]
        in_ids = [r.source for r in in_by_target.get(entity_id, ()) if r.type == rel]
        if direction == "out":
            ordered = out_ids
        elif direction == "in":
            ordered = in_ids
        elif direction == "any":
            ordered = out_ids + in_ids
        else:
            msg = f"direction must be 'out', 'in', or 'any', got {direction!r}"
            raise ValueError(msg)

        seen: set[str] = set()
        result: list[str] = []
        for rid in ordered:
            if rid not in seen and rid in self._entities:
                seen.add(rid)
                result.append(rid)
        return result
