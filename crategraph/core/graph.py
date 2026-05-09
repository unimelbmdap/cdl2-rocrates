"""Graph class — the central object for loading, querying, and visualising graphs."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx

from crategraph.core import (
    analysis,
    filtering,
    presentation,
    transforms,
)
from crategraph.core._files import entity_raw_id, is_contextual_entity, resolve_entity_path
from crategraph.core.models import Entity, Relationship
from crategraph.core.types import TypeRegistry

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from crategraph.core.models import CoverageResult, FileInfo, ViewInfo


class Graph:
    """The central object for loading, querying, and visualising graphs.

    Uses a NetworkX ``MultiDiGraph`` internally for graph storage and
    traversal.  ``MultiDiGraph`` supports directed edges and multiple
    edges between the same node pair, both required by the data model.
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
        self._source_names: set[str] = set()
        self._graph: nx.MultiDiGraph = nx.MultiDiGraph()
        self._root: Graph = self  # reference to the root/full graph for expand()
        self._simplification_k: int | None = None

    # --- Public read-only properties ---

    @property
    def types(self) -> TypeRegistry:
        """Registry of entity types present in this graph."""
        all_types: set[str] = set()
        for e in self._entities.values():
            all_types.update(e.types)
        return TypeRegistry(frozenset(all_types), label="entity type")

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
        return TypeRegistry(
            frozenset(r.type for r in self._relationships),
            label="relationship type",
        )

    @property
    def entities(self) -> list[Entity]:
        """All entities in the graph."""
        return list(self._entities.values())

    @property
    def relationships(self) -> list[Relationship]:
        """All relationships in the graph."""
        return list(self._relationships)

    @property
    def files(self) -> list[Entity]:
        """Data entities (files and directories) in the graph.

        Convenience for filtering to entities where ``has_data`` is
        ``True``, sorted by ID.
        """
        return sorted(
            (e for e in self._entities.values() if e.has_data),
            key=lambda e: e.properties.get("raw_id", e.id),
        )

    def __len__(self) -> int:
        """Number of entities in the graph."""
        return len(self._entities)

    @property
    def sources(self) -> list[str]:
        """Distinct source directory names, sorted."""
        return sorted(self._source_names)

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

    def get(self, entity_id: str) -> Entity:
        """Return a single ``Entity`` by its ID.

        Raises ``KeyError`` with a clear message if the ID doesn't exist.
        """
        try:
            return self._entities[entity_id]
        except KeyError:
            msg = f'No entity with id "{entity_id}" in this graph.'
            raise KeyError(msg) from None

    # --- Public export methods ---

    def to_networkx(self, *, copy: bool = True) -> nx.MultiDiGraph:
        """Return a NetworkX ``MultiDiGraph`` view of this graph.

        The returned graph is rebuilt from ``self.entities`` and
        ``self.relationships`` so callers receive a regular NetworkX graph
        with one edge per :class:`Relationship`. Edge keys are assigned by
        ``MultiDiGraph`` so same-type parallel edges between the same
        endpoints survive.

        With ``copy=True`` (default), each node's ``entity`` attribute and
        each edge's ``relationship`` attribute are deep copies, so the
        caller can mutate nested ``Entity.properties`` or
        ``Relationship.properties`` dicts without affecting this ``Graph``.
        With ``copy=False``, the original ``Entity`` / ``Relationship``
        objects are attached directly; the caller must not mutate their
        nested ``properties``.
        """
        import copy as _copy

        nxg = nx.MultiDiGraph()
        for entity in self.entities:
            attached = _copy.deepcopy(entity) if copy else entity
            nxg.add_node(entity.id, entity=attached)
        for rel in self.relationships:
            attached = _copy.deepcopy(rel) if copy else rel
            nxg.add_edge(rel.source, rel.target, relationship=attached)
        return nxg

    def entity_records(self) -> list[dict[str, Any]]:
        """Return one ``dict`` per entity with native Python values.

        Keys: ``id``, ``label``, ``type``, ``types`` first, then
        non-colliding properties sorted alphabetically, then any
        properties whose names collide with a promoted key emitted as
        ``prop_<key>``. ``label`` falls back through ``name`` →
        ``title`` → ``id``. ``type`` is the first entry of ``types``
        (or empty string if untyped). ``types`` is a list of strings.
        Property values are deep-copied so callers can mutate returned
        records without touching graph state.

        Wrap with your DataFrame library of choice:

        ::

            import pandas as pd
            df = pd.DataFrame(graph.entity_records())

            # or polars / pyarrow:
            # pl.DataFrame(graph.entity_records())
            # pa.Table.from_pylist(graph.entity_records())
        """
        from crategraph.core import records

        return records.entity_records(self)

    def relationship_records(self) -> list[dict[str, Any]]:
        """Return one ``dict`` per relationship with native Python values.

        Keys: ``source``, ``target``, ``type``, ``rel_id`` first, then
        non-colliding properties sorted alphabetically, then any
        properties whose names collide with a promoted key emitted as
        ``prop_<key>``. ``rel_id`` is ``None`` for inline (non-reified)
        relationships and a string for reified ones — the distinction
        is preserved here, unlike the CSV writer which collapses both
        to an empty string. Property values are deep-copied so callers
        can mutate returned records without touching graph state.

        Wrap with your DataFrame library of choice:

        ::

            import pandas as pd
            df = pd.DataFrame(graph.relationship_records())

            # or polars / pyarrow:
            # pl.DataFrame(graph.relationship_records())
            # pa.Table.from_pylist(graph.relationship_records())
        """
        from crategraph.core import records

        return records.relationship_records(self)

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
    ) -> list[tuple[Entity, int]]:
        """Return the top *n* entities by number of connections."""
        return analysis.most_connected(self, n=n, entity_types=entity_types)

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

    def layout(self) -> dict[str, tuple[float, float]]:
        """Compute 2D node positions for visualisation."""
        return presentation.layout(self)

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
            **kwargs,
        )

    def glimpse(self, *, filepath: str | None = None) -> Any:
        """Inline snapshot of the type-level graph structure."""
        return presentation.glimpse(self, filepath=filepath)

    def inspect(self, entity: Entity | str) -> FileInfo:
        """Inspect the data file associated with an entity."""
        return presentation.inspect(self, entity)

    def view(self, entity: Entity | str) -> ViewInfo:
        """View the data file associated with an entity."""
        return presentation.view(self, entity)

    def text_records(
        self,
        *,
        store_path: str | Path | None = None,
        text_properties: Sequence[str] | None = None,
        filters: Mapping[str, Any] | None = None,
        restrict_to_view: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Yield one text record per source unit in the graph.

        Each record is a dict with keys ``source_id``, ``entity_id``,
        ``source_kind`` (``"file"`` or ``"properties"``),
        ``entity_types``, ``text``. Generator — peak memory is one
        record at a time.

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
        if store_path is not None:
            return self._cached_text_records(
                store_path, filters, restrict_to_view=restrict_to_view
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
            filters=dict(filters) if filters else None,
        )

    def chunk_records(
        self,
        *,
        store_path: str | Path | None = None,
        filters: Mapping[str, Any] | None = None,
        restrict_to_view: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Yield one record per indexed chunk.

        Requires the ``[index]`` extra and a previously-built index.
        ``store_path`` defaults to :attr:`default_index_path`; raises
        ``FileNotFoundError`` if no index exists at the default. Each
        record is a dict with keys ``source_id``, ``entity_id``,
        ``source_kind``, ``entity_types``, ``chunk_index``,
        ``char_start``, ``char_end``, ``token_count``, ``text`` —
        with ``text`` reconstructed at query time from the canonical
        ``text_units`` row via SUBSTR. Streaming: peak memory ≈ one
        chunk's text.

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

        def _iter() -> Iterator[dict[str, Any]]:
            with Store(resolved) as store:
                yield from store.iter_chunk_records(filters=merged)

        return _iter()

    def _cached_text_records(
        self,
        store_path: str | Path,
        filters: Mapping[str, Any] | None,
        *,
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
            with Store(store_path) as store:
                yield from store.iter_text_records(filters=merged)

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
        view_ids = set(self._entities.keys())
        if "entity_id" in merged:
            user_ids = set(merged["entity_id"])
            intersected = list(user_ids & view_ids)
            if not intersected:
                return None
            merged["entity_id"] = intersected
        else:
            merged["entity_id"] = list(view_ids)
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

    def semantic_search(
        self,
        query: str,
        *,
        store_path: str | Path | None = None,
        k: int = 10,
        filters: Mapping[str, Any] | None = None,
        restrict_to_view: bool = True,
    ) -> list[Any]:
        """Run a semantic search against an existing index.

        Requires the ``[index]`` extra and a previously-built index.
        ``store_path`` defaults to :attr:`default_index_path`; if no
        index exists there a clear error is raised. Filter keys:
        ``source_id``, ``entity_id``, ``entity_types``, ``source_kind``.

        By default (``restrict_to_view=True``), search results are
        restricted to entities present in *this* graph — so a filtered
        subgraph (``crate.where(...)``) only returns hits from its own
        entities, not from filtered-out ones. Pass
        ``restrict_to_view=False`` to query the full index regardless
        of the current view.

        Issues a warning if the graph's source ids don't overlap with
        the index's known sources (likely sign of an unrelated index).

        Returns a list of :class:`~crategraph.index.SearchHit`.
        """
        import warnings

        try:
            from crategraph.index import Searcher
        except ImportError:
            msg = (
                "Semantic search requires the [index] extra. "
                "Install it with: pip install crategraph[index]"
            )
            raise ImportError(msg) from None

        resolved = self._resolve_index_path(store_path, must_exist=True)
        searcher = Searcher(resolved)

        # Manifest / source-set sanity check.
        graph_sources = set(self.sources)
        if graph_sources:
            indexed_sources = set(searcher.known_source_ids())
            if indexed_sources and not (graph_sources & indexed_sources):
                warnings.warn(
                    f"Graph sources {sorted(graph_sources)} don't overlap "
                    f"with index sources {sorted(indexed_sources)}; "
                    "this may be the wrong index file.",
                    stacklevel=2,
                )

        merged_filters: dict[str, Any] = dict(filters) if filters else {}
        if restrict_to_view:
            view_ids = set(self._entities.keys())
            if "entity_id" in merged_filters:
                # Intersect a user-supplied entity_id filter with the current
                # view rather than letting the user's filter bypass it.
                user_ids = set(merged_filters["entity_id"])
                intersected = list(user_ids & view_ids)
                if not intersected:
                    return []
                merged_filters["entity_id"] = intersected
            else:
                merged_filters["entity_id"] = list(view_ids)

        return searcher.search(query, k=k, filters=merged_filters)

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

    def where(self, **kwargs: Any) -> Graph:
        """Filter by entity property values."""
        return filtering.where(self, **kwargs)

    def search(
        self,
        query: str,
        *,
        properties: list[str] | None = None,
        threshold: int = 80,
        top_n: int = 10,
    ) -> Graph:
        """Fuzzy content search across entity properties."""
        return filtering.search(
            self, query, properties=properties, threshold=threshold, top_n=top_n
        )

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
        if entity.source is not None:
            from pathlib import PurePosixPath

            self._source_names.add(PurePosixPath(entity.source).name)
        self._graph.add_node(entity.id, entity=entity)

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
        self._graph.add_edge(
            relationship.source,
            relationship.target,
            relationship=relationship,
        )

    def _display_name(self, entity_id: str) -> str:
        """Return the best display name for an entity ID."""
        entity = self._entities.get(entity_id)
        return entity.name if entity else entity_id

    def _neighbours(self, node_id: str) -> set[str]:
        """Return IDs of all nodes adjacent to *node_id* (in either direction)."""
        if node_id not in self._graph:
            return set()
        return set(self._graph.successors(node_id)) | set(self._graph.predecessors(node_id))

    def _coerce_entity(self, entity: Entity | str) -> Entity:
        """Resolve an entity object or ID string to an Entity."""
        return self.get(entity) if isinstance(entity, str) else entity

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
        from pathlib import PurePosixPath

        derived._source_names = {
            PurePosixPath(entity.source).name
            for entity in derived._entities.values()
            if entity.source is not None
        }
        derived._graph = nx.MultiDiGraph()
        for nid, entity in derived._entities.items():
            derived._graph.add_node(nid, entity=entity)
        for relationship in derived._relationships:
            derived._graph.add_edge(
                relationship.source,
                relationship.target,
                relationship=relationship,
            )
        derived._root = self._root
        derived._simplification_k = None
        return derived

    def _subgraph(self, node_ids: set[str]) -> Graph:
        """Return a new Graph containing only the specified nodes and their mutual edges."""
        return self._build_derived_graph(node_ids=node_ids)
