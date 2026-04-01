"""Graph class — the central object for loading, querying, and visualising graphs."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Any

import networkx as nx

from crategraph.core import analysis as analysis_mod
from crategraph.core._files import entity_raw_id, is_contextual_entity, resolve_entity_path
from crategraph.core.models import Entity, Relationship
from crategraph.core.types import TypeRegistry

if TYPE_CHECKING:
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

        return f"<pre style='font-size:13px; line-height:1.4'>{text}</pre>"

    def get(self, entity_id: str) -> Entity:
        """Return a single ``Entity`` by its ID.

        Raises ``KeyError`` with a clear message if the ID doesn't exist.
        """
        try:
            return self._entities[entity_id]
        except KeyError:
            msg = f'No entity with id "{entity_id}" in this graph.'
            raise KeyError(msg) from None

    # --- Analysis methods (delegated to core/analysis.py) ---

    def summary(self) -> analysis_mod.GraphSummary:
        """Return a structured summary of type/relationship counts."""
        return analysis_mod.summary(self)

    def most_connected(
        self, *, n: int = 10, entity_types: list[str] | None = None
    ) -> list[tuple[Entity, int]]:
        """Return the top *n* entities by number of connections."""
        return analysis_mod.most_connected(self, n=n, entity_types=entity_types)

    def profile(self) -> analysis_mod.GraphProfile:
        """Return a structural profile with density, components, degree stats."""
        return analysis_mod.profile(self)

    def _coverage(
        self,
        *,
        inline_relations: bool | list[str] = False,
        min_occurrences: int = 5,
    ) -> list[CoverageResult]:
        """Analyse relationship coverage across entity types.

        Discovers structural patterns ``(relationship_type, source_type,
        target_type)`` and measures what fraction of each entity type
        participates.  Partial coverage suggests data quality gaps.

        Args:
            inline_relations: Include inline ``@id`` references.
                ``False`` = reified only. ``True`` = all.
                A list of property names includes only those inline types.
            min_occurrences: Minimum relationship count for a triple to
                be considered a pattern worth reporting.
        """
        return analysis_mod.coverage(
            self,
            inline_relations=inline_relations,
            min_occurrences=min_occurrences,
        )

    # --- Layout ---

    _FA2_FALLBACK_LIMIT = 2000

    def layout(self) -> dict[str, tuple[float, float]]:
        """Compute 2D node positions for visualisation.

        Uses ForceAtlas2 (via the ``fa2`` package) when available, with
        parameters matched to graphology's ``inferSettings()``.  Falls
        back to NetworkX ``spring_layout`` for small graphs when ``fa2``
        is not installed.

        Install the fast backend with::

            pip install crategraph[fa2]

        Returns ``{entity_id: (x, y)}`` with raw coordinates (not scaled
        to any canvas).
        """
        if not self._entities:
            return {}

        n = len(self._entities)
        nx_undirected = self._graph.to_undirected()

        try:
            from fa2 import ForceAtlas2

            # Match graphology-layout-forceatlas2's inferSettings():
            #   barnesHutOptimize: order > 2000
            #   strongGravityMode: true
            #   gravity: 0.05
            #   scalingRatio: 10
            #   slowDown: 1 + Math.log(order)
            fa2 = ForceAtlas2(
                outboundAttractionDistribution=False,
                barnesHutOptimize=n > 2000,
                barnesHutTheta=0.5,
                scalingRatio=10,
                strongGravityMode=True,
                gravity=0.05,
                verbose=False,
            )
            iters = min(200, 50 + n // 100)
            return fa2.forceatlas2_networkx_layout(nx_undirected, iterations=iters)
        except ImportError:
            pass

        if n > self._FA2_FALLBACK_LIMIT:
            msg = (
                f"This graph has {n:,} nodes — the fallback spring layout "
                f"will be extremely slow without the fa2 package.\n"
                f"Install it with: pip install crategraph[fa2]"
            )
            raise ImportError(msg)

        return nx.spring_layout(nx_undirected, seed=42)

    # --- Visualisation ---

    def visualise(
        self,
        *,
        renderer: str = "2d",
        colour_by: str = "type",
        size_by: str = "connections",
        height: str = "100vh",
        width: str = "100%",
        filepath: str | None = None,
        collapse_edges: bool = False,
        **kwargs: Any,
    ) -> Any:
        """Render the graph as a network visualisation.

        Args:
            renderer: ``"2d"`` (default) for pyvis, ``"3d"`` for
                3d-force-graph, ``"svg"`` for static SVG,
                ``"sigma"`` for sigma.js WebGL.
            colour_by: Property to colour nodes by (default ``"type"``).
                Any entity property or attribute works. ``"community"``
                auto-computes Louvain communities if not already present.
            size_by: ``"connections"`` (default) scales node size by degree.
            height: CSS height of the canvas.
            width: CSS width of the canvas.
            filepath: Save output to this path instead of returning
                the display object.
            collapse_edges: If ``True``, collapse parallel edges between
                the same pair of nodes before rendering.

        Returns a renderer-specific object (for inline notebook display)
        or the filepath string if *filepath* was provided.
        """
        graph = self.collapse_edges() if collapse_edges else self

        if renderer == "2d":
            from crategraph.renderers.pyvis import PyvisRenderer

            impl = PyvisRenderer()
        elif renderer == "3d":
            from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer

            impl = ForceGraph3DRenderer()
        elif renderer == "svg":
            from crategraph.renderers.svg import SvgRenderer

            impl = SvgRenderer()
        elif renderer == "sigma":
            from crategraph.renderers.sigma import SigmaRenderer

            impl = SigmaRenderer()
        else:
            msg = (
                f'Unknown renderer "{renderer}". '
                'Choose "2d" (pyvis), "3d" (3d-force-graph), '
                '"svg" (static SVG), or "sigma" (sigma.js WebGL).'
            )
            raise ValueError(msg)

        return impl.render(
            graph,
            colour_by=colour_by,
            size_by=size_by,
            height=height,
            width=width,
            filepath=filepath,
            **kwargs,
        )

    def glimpse(self, *, filepath: str | None = None) -> Any:
        """Inline snapshot of the type-level graph structure.

        Always merges entities by primary type — shows one node per type
        with entity counts and weighted edges.  Designed for quick
        orientation in notebooks, not detailed exploration.

        Args:
            filepath: Save the output to this path instead of displaying
                inline.

        Returns a display object for notebook rendering, or the filepath
        string if *filepath* was provided.
        """
        from crategraph.core.analysis import merge_by_primary_type

        merged = merge_by_primary_type(self)
        from crategraph.renderers.svg import SvgRenderer

        return SvgRenderer().render(
            merged,
            width=600,
            height=450,
            filepath=filepath,
        )

    # --- Inspection ---

    def inspect(self, entity: Entity | str) -> FileInfo:
        """Inspect the data file associated with an entity.

        Reads the file referenced by a data entity and returns a preview
        with metadata. Requires ``markitdown`` — install via
        ``pip install crategraph[inspect]``.

        Args:
            entity: An ``Entity`` object or an entity ID string.

        Returns a ``FileInfo`` with the file's content, metadata, and size.

        Raises:
            KeyError: If the entity ID doesn't exist in the graph.
            ValueError: If the entity is contextual (``#``-prefixed or URL).
            FileNotFoundError: If the referenced file doesn't exist on disk.
        """
        from crategraph.core.models import FileInfo
        from crategraph.inspectors import find_inspector

        entity = self._coerce_entity(entity)
        entity_id, file_path = self._require_local_entity_file(entity, action="inspect")

        # Find an inspector.
        inspector = find_inspector(entity)
        if inspector is None:
            msg = f"Could not inspect {entity_id!r} — format not supported."
            raise ValueError(msg)

        # Inspect and fill in media_type from entity properties.
        info = inspector.inspect(file_path)
        media_type = entity.properties.get("encodingFormat")

        # Return a new FileInfo with media_type filled in.
        return FileInfo(
            path=info.path,
            content=info.content,
            title=info.title,
            size_bytes=info.size_bytes,
            media_type=media_type if media_type else info.media_type,
        )

    # --- View ---

    def view(self, entity: Entity | str) -> ViewInfo:
        """View the data file associated with an entity.

        Returns a rich HTML preview of the file — images as ``<img>``
        tags, CSVs as HTML tables, audio with playback controls.

        Args:
            entity: An ``Entity`` object or an entity ID string.

        Returns a ``ViewInfo`` with the file's HTML preview and metadata.

        Raises:
            KeyError: If the entity ID doesn't exist in the graph.
            ValueError: If the entity is contextual (``#``-prefixed or URL).
            FileNotFoundError: If the referenced file doesn't exist on disk.
        """
        from crategraph.core.models import ViewInfo
        from crategraph.viewers import find_viewer

        entity = self._coerce_entity(entity)
        entity_id, file_path = self._require_local_entity_file(entity, action="view")

        # Find a viewer.
        viewer = find_viewer(entity)
        if viewer is None:
            msg = f"Could not view {entity_id!r} — format not supported."
            raise ValueError(msg)

        # View and fill in media_type from entity properties if available.
        info = viewer.view(file_path)
        media_type = entity.properties.get("encodingFormat")

        return ViewInfo(
            path=info.path,
            html=info.html,
            title=info.title,
            size_bytes=info.size_bytes,
            media_type=media_type if media_type else info.media_type,
        )

    # --- Transform methods ---

    def detect_communities(self, *, resolution: float = 1.0, seed: int | None = None) -> Graph:
        """Return a new graph with a ``"community"`` property on each entity.

        Uses the Louvain algorithm via :func:`analysis.detect_communities`.
        """
        return analysis_mod.detect_communities_transform(
            self,
            resolution=resolution,
            seed=seed,
        )

    def merge_nodes(self, *, by: str) -> Graph:
        """Aggregate nodes by a property, returning a collapsed graph."""
        from crategraph.core import transforms

        return transforms.merge_nodes(self, by=by)

    def simplify(
        self,
        *,
        min_connections: int | None = None,
    ) -> Graph:
        """Remove peripheral nodes to reveal the structural backbone."""
        from crategraph.core import transforms

        return transforms.simplify(self, min_connections=min_connections)

    def collapse_edges(self) -> Graph:
        """Collapse parallel edges between node pairs into single summary edges."""
        from crategraph.core import transforms

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
        from crategraph.core import filtering

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

    def where(self, **kwargs: Any) -> Graph:
        """Filter by entity property values."""
        from crategraph.core import filtering

        return filtering.where(self, **kwargs)

    def search(
        self,
        query: str,
        *,
        properties: list[str] | None = None,
        threshold: int = 60,
    ) -> Graph:
        """Fuzzy content search across entity properties."""
        from crategraph.core import filtering

        return filtering.search(self, query, properties=properties, threshold=threshold)

    def expand(
        self,
        *,
        depth: int = 1,
        entity_types: list[str] | None = None,
        via: str | None = None,
    ) -> Graph:
        """Grow this selection outward to include connected neighbours."""
        from crategraph.core import filtering

        return filtering.expand(self, depth=depth, entity_types=entity_types, via=via)

    def pattern(
        self,
        *,
        from_type: str | None = None,
        via: str | None = None,
        to_type: str | None = None,
    ) -> Graph:
        """Match relationships by source type, relationship type, and/or target type."""
        from crategraph.core import filtering

        return filtering.pattern(self, from_type=from_type, via=via, to_type=to_type)

    def query(self, cypher: str) -> Graph:
        """Run a Cypher query and return a subgraph of matched entities."""
        from crategraph.core import filtering

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
            key=relationship.type,
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
        simplification_k: int | None = None,
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
        derived._relationships = (
            relationships
            if relationships is not None
            else [r for r in self._relationships if r.source in node_ids and r.target in node_ids]
        )
        derived._source_names = set(self._source_names)
        derived._graph = self._graph.subgraph(node_ids).copy()
        for nid, entity in derived._entities.items():
            if nid in derived._graph:
                derived._graph.nodes[nid]["entity"] = entity
        derived._root = self._root
        derived._simplification_k = simplification_k
        return derived

    def _subgraph(self, node_ids: set[str]) -> Graph:
        """Return a new Graph containing only the specified nodes and their mutual edges."""
        return self._build_derived_graph(node_ids=node_ids)
