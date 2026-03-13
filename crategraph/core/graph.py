"""Graph class — the central object for loading, querying, and visualising graphs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from rapidfuzz import fuzz

from crategraph.core import analysis as analysis_mod
from crategraph.core.backends import default_backend
from crategraph.core.models import Entity, Relationship
from crategraph.core.types import TypeRegistry

if TYPE_CHECKING:
    from crategraph.core.interfaces import GraphBackend
    from crategraph.core.models import FileInfo, ViewInfo


class Graph:
    """The central object for loading, querying, and visualising graphs.

    By default uses the best available backend (rustworkx if installed,
    otherwise NetworkX).  Pass an explicit *backend* to override.
    """

    def __init__(
        self,
        *,
        source: str | None = None,
        metadata: dict[str, Any] | None = None,
        backend: GraphBackend | None = None,
    ) -> None:
        self.source = source
        self.metadata: dict[str, Any] = metadata if metadata is not None else {}
        self._entities: dict[str, Entity] = {}
        self._relationships: list[Relationship] = []
        self._source_names: set[str] = set()
        self._backend: GraphBackend = backend if backend is not None else default_backend()
        self._root: Graph = self  # reference to the root/full graph for expand()

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
                3d-force-graph, ``"svg"`` for static SVG.
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
        else:
            msg = (
                f'Unknown renderer "{renderer}". '
                f'Choose "2d" (pyvis), "3d" (3d-force-graph), or "svg" (static SVG).'
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
        from pathlib import Path as _Path

        from crategraph.core.models import FileInfo
        from crategraph.inspectors import find_inspector

        # Resolve entity from string ID.
        if isinstance(entity, str):
            entity = self.get(entity)

        # Reject contextual entities.
        entity_id = entity.properties.get("raw_id", entity.id)
        if (
            entity_id.startswith("#")
            or entity_id.startswith("http")
            or entity_id == "./"
            or entity.properties.get("_is_root")
        ):
            msg = (
                f"Entity {entity.id!r} is a contextual entity "
                f"— inspect() works with data entities that point to local files."
            )
            raise ValueError(msg)

        # Resolve file path.
        crate_root = entity.source or self.source
        if crate_root is None:
            msg = f"Cannot resolve file path for {entity.id!r} — no crate source directory is set."
            raise ValueError(msg)

        file_path = _Path(crate_root) / entity_id
        crate_root_resolved = _Path(crate_root).resolve(strict=False)
        try:
            file_path_resolved = file_path.resolve(strict=False)
            file_path_resolved.relative_to(crate_root_resolved)
        except ValueError:
            msg = (
                f"Entity ID {entity_id!r} resolves outside the crate directory "
                f"{str(crate_root_resolved)!r}."
            )
            raise ValueError(msg) from None
        if not file_path.is_file():
            msg = (
                f"Cannot find file {entity_id!r} in crate at {crate_root!r}. "
                f"Check the entity ID refers to a local file."
            )
            raise FileNotFoundError(msg)

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
        from pathlib import Path as _Path

        from crategraph.core.models import ViewInfo
        from crategraph.viewers import find_viewer

        # Resolve entity from string ID.
        if isinstance(entity, str):
            entity = self.get(entity)

        # Reject contextual entities.
        entity_id = entity.properties.get("raw_id", entity.id)
        if (
            entity_id.startswith("#")
            or entity_id.startswith("http")
            or entity_id == "./"
            or entity.properties.get("_is_root")
        ):
            msg = (
                f"Entity {entity.id!r} is a contextual entity "
                f"— view() works with data entities that point to local files."
            )
            raise ValueError(msg)

        # Resolve file path.
        crate_root = entity.source or self.source
        if crate_root is None:
            msg = f"Cannot resolve file path for {entity.id!r} — no crate source directory is set."
            raise ValueError(msg)

        file_path = _Path(crate_root) / entity_id
        crate_root_resolved = _Path(crate_root).resolve(strict=False)
        try:
            file_path_resolved = file_path.resolve(strict=False)
            file_path_resolved.relative_to(crate_root_resolved)
        except ValueError:
            msg = (
                f"Entity ID {entity_id!r} resolves outside the crate directory "
                f"{str(crate_root_resolved)!r}."
            )
            raise ValueError(msg) from None
        if not file_path.is_file():
            msg = (
                f"Cannot find file {entity_id!r} in crate at {crate_root!r}. "
                f"Check the entity ID refers to a local file."
            )
            raise FileNotFoundError(msg)

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
        """Aggregate nodes by a property, returning a collapsed graph.

        Each unique value of *by* (either entity type via the special
        value ``"type"``, or a property key) becomes one node in the
        result.  Edges between groups are preserved with a ``weight``
        property counting the original edges.

        Args:
            by: ``"type"`` to group by entity type, or a property key
                name (e.g. ``"location"``, ``"decade"``).

        Returns a new ``Graph`` with one node per group and weighted edges.
        """
        from collections import Counter

        # Assign each entity to a group.
        groups: dict[str, str] = {}  # entity_id → group_label
        for eid, entity in self._entities.items():
            if by == "type":
                groups[eid] = entity.type
            else:
                value = entity.properties.get(by)
                groups[eid] = str(value) if value is not None else "(no value)"

        # Build group nodes.
        merged = Graph(source=self.source, metadata=dict(self.metadata))
        group_counts: Counter[str] = Counter(groups.values())

        for label, count in group_counts.items():
            merged._add_node(
                Entity(
                    id=label,
                    types=["MergedGroup"],
                    properties={"label": label, "count": count, "merged_by": by},
                )
            )

        # Build weighted edges between groups, preserving relationship types.
        edge_weights: Counter[tuple[str, str, str]] = Counter()
        for rel in self._relationships:
            src_group = groups.get(rel.source)
            tgt_group = groups.get(rel.target)
            if src_group is not None and tgt_group is not None and src_group != tgt_group:
                edge_weights[(src_group, tgt_group, rel.type)] += 1

        for (src, tgt, rel_type), weight in edge_weights.items():
            merged._add_edge(
                Relationship(
                    source=src,
                    target=tgt,
                    type=rel_type,
                    properties={"weight": weight},
                )
            )

        return merged

    def simplify(
        self,
        *,
        min_connections: int | None = None,
    ) -> Graph:
        """Remove peripheral nodes to reveal the structural backbone.

        Each call strips away one more layer of weakly-connected nodes
        (k-core peeling).  Chainable: calling ``simplify()`` on an
        already-simplified graph automatically increases the threshold.

        Surviving nodes gain a ``"simplified"`` property — a dict
        mapping removed-neighbour type to count.

        Args:
            min_connections: Explicit minimum-degree threshold.  When
                omitted the method auto-escalates: first call uses 2,
                subsequent calls increment from the previous level.

        Returns a new ``Graph``, or ``self`` if no further
        simplification is possible (with a warning).
        """
        import warnings

        if min_connections is not None:
            k = min_connections
        elif hasattr(self, "_simplification_k"):
            k = self._simplification_k + 1
        else:
            k = 2

        result = self._simplify_core(k)

        if len(result) == 0 or len(result) == len(self):
            warnings.warn(
                f"Graph is fully simplified: all {len(self)} remaining "
                f"nodes have fewer than {k} connections. "
                f"Returning the current graph.",
                stacklevel=2,
            )
            return self

        result._simplification_k = k
        return result

    def _simplify_core(self, min_connections: int) -> Graph:
        """BFS k-core peeling implementation (O(V+E), backend-agnostic).

        1. Compute degrees via ``_neighbours()``
        2. BFS-peel nodes below *min_connections*
        3. Annotate survivors with type-counted summary of removed neighbours
        4. Build new ``Graph`` preserving ``_root``
        """
        from collections import deque
        from dataclasses import replace

        # Step 1 — initial degrees (unique neighbours, both directions).
        all_ids = set(self._entities.keys())
        degree: dict[str, int] = {}
        neighbours: dict[str, set[str]] = {}
        for nid in all_ids:
            nbrs = self._neighbours(nid) & all_ids
            neighbours[nid] = nbrs
            degree[nid] = len(nbrs)

        # Step 2 — BFS peel.
        removed: set[str] = set()
        queue: deque[str] = deque(nid for nid, deg in degree.items() if deg < min_connections)
        while queue:
            nid = queue.popleft()
            if nid in removed:
                continue
            removed.add(nid)
            for nbr in neighbours[nid]:
                if nbr not in removed:
                    degree[nbr] -= 1
                    if degree[nbr] < min_connections:
                        queue.append(nbr)

        surviving = all_ids - removed

        # Step 3 — annotate survivors with removed-neighbour summary.
        removed_direct: dict[str, dict[str, int]] = {}
        for sid in surviving:
            type_counts: dict[str, int] = {}
            for nbr in neighbours[sid]:
                if nbr in removed:
                    entity = self._entities[nbr]
                    primary = entity.types[0] if entity.types else "Unknown"
                    type_counts[primary] = type_counts.get(primary, 0) + 1
            removed_direct[sid] = type_counts

        # Step 4 — build new Graph (mirrors _subgraph pattern).
        sub = Graph.__new__(Graph)
        sub.source = self.source
        sub.metadata = dict(self.metadata)
        sub._entities = {}
        for nid in surviving:
            entity = self._entities[nid]
            annotation = removed_direct[nid]
            if annotation:
                new_props = {**entity.properties, "simplified": annotation}
                sub._entities[nid] = replace(entity, properties=new_props)
            else:
                sub._entities[nid] = entity
        sub._relationships = [
            r for r in self._relationships if r.source in surviving and r.target in surviving
        ]
        sub._source_names = set(self._source_names)
        new_backend = self._backend.subgraph(surviving, sub._entities, sub._relationships)
        sub._backend = new_backend
        sub._root = self._root
        return sub

    def collapse_edges(self) -> Graph:
        """Collapse parallel edges between node pairs into single summary edges.

        For each pair of nodes, all edges (in either direction) are combined
        into one edge.  The resulting edge carries summary metadata:
        ``count``, ``types`` list, ``bidirectional`` flag, and ``weight``.

        Single edges between a pair pass through unchanged.

        Returns a new ``Graph`` with the same nodes and simplified edges.
        """
        from collections import defaultdict

        # Group edges by unordered node pair.
        pair_edges: dict[frozenset[str], list[Relationship]] = defaultdict(list)
        for rel in self._relationships:
            pair_key = frozenset((rel.source, rel.target))
            pair_edges[pair_key].append(rel)

        # Build the new graph with same nodes.
        collapsed = Graph(
            source=self.source,
            metadata=dict(self.metadata),
            backend=type(self._backend)(),
        )
        for entity in self._entities.values():
            collapsed._add_node(entity)

        # Collapse each group of edges.
        for pair_key, edges in pair_edges.items():
            if len(edges) == 1:
                # Single edge — pass through unchanged.
                collapsed._add_edge(edges[0])
                continue

            # Determine directionality.
            directions = {(r.source, r.target) for r in edges}
            bidirectional = len(directions) > 1

            # Canonical source/target ordering.
            if bidirectional:
                source, target = sorted(pair_key)
            else:
                source, target = edges[0].source, edges[0].target

            # Collect types (sorted, deduplicated).
            types_list = sorted(set(r.type for r in edges))

            # Sum existing weights or count edges.
            total_weight = sum(r.properties.get("weight", 1) for r in edges)

            # Type label.
            type_label = types_list[0] if len(types_list) == 1 else f"{len(edges)} relationships"

            collapsed._add_edge(
                Relationship(
                    source=source,
                    target=target,
                    type=type_label,
                    properties={
                        "collapsed": True,
                        "count": len(edges),
                        "types": types_list,
                        "bidirectional": bidirectional,
                        "weight": total_weight,
                    },
                )
            )

        return collapsed

    # --- Public query methods ---

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
        """Filter by graph structure — type, time, source, connectivity.

        Returns a new ``Graph`` containing only the matching entities and
        their mutual relationships.
        """
        # Normalise string args to lists.
        if isinstance(relationship_types, str):
            relationship_types = [relationship_types]

        # Validate time_range ordering.
        if time_range is not None and time_range[0] > time_range[1]:
            msg = (
                f"Start of range must be before end — got {time_range}. "
                f"Did you mean ({time_range[1]}, {time_range[0]})?"
            )
            raise ValueError(msg)

        candidates = set(self._entities.keys())

        # Filter by id.
        if id is not None:
            candidates &= {id} if id in self._entities else set()

        # Filter by entity type — matches if any of the entity's types are in the list.
        if entity_types is not None:
            type_set = set(entity_types)
            for t in entity_types:
                self.types.validate(t)
            candidates = {
                eid for eid in candidates if type_set.intersection(self._entities[eid].types)
            }

        # Filter by source.
        if source is not None:
            candidates = {
                eid
                for eid in candidates
                if self._entities[eid].source is not None and source in self._entities[eid].source
            }

        # Filter by connectivity.
        if min_connections is not None or max_connections is not None:
            filtered: set[str] = set()
            for eid in candidates:
                degree = len(self._neighbours(eid))
                if min_connections is not None and degree < min_connections:
                    continue
                if max_connections is not None and degree > max_connections:
                    continue
                filtered.add(eid)
            candidates = filtered

        # Filter by relationship types — keep entities connected by matching rels.
        if relationship_types is not None:
            for t in relationship_types:
                self.relationship_types.validate(t)
            connected: set[str] = set()
            for rel in self._relationships:
                if rel.type in relationship_types:
                    connected.add(rel.source)
                    connected.add(rel.target)
            candidates &= connected

        return self._subgraph(candidates)

    def where(self, **kwargs: Any) -> Graph:
        """Filter by entity property values.

        Scalar values are matched exactly.  Tuple ``(low, high)`` values
        match entities whose property falls within the inclusive range.

        Returns a new ``Graph`` containing only the matching entities.
        """
        if not kwargs:
            return self._subgraph(set(self._entities.keys()))

        candidates: set[str] = set()
        for eid, entity in self._entities.items():
            if self._entity_matches_where(entity, kwargs):
                candidates.add(eid)
        return self._subgraph(candidates)

    def _entity_matches_where(self, entity: Entity, filters: dict[str, Any]) -> bool:
        for key, expected in filters.items():
            value = entity.properties.get(key)
            if value is None:
                return False
            if isinstance(expected, tuple) and len(expected) == 2:
                # Range filter.
                low, high = expected
                try:
                    numeric = float(value) if not isinstance(value, (int, float)) else value
                    if not (low <= numeric <= high):
                        return False
                except (ValueError, TypeError):
                    return False
            elif value != expected:
                return False
        return True

    def search(
        self,
        query: str,
        *,
        properties: list[str] | None = None,
        threshold: int = 60,
    ) -> Graph:
        """Fuzzy content search across entity properties.

        Args:
            query: The search term.
            properties: Limit search to these property keys (default: all).
            threshold: Minimum match score 0-100 (default 60).

        Returns a new ``Graph`` containing matching entities and their
        mutual relationships.
        """
        candidates: set[str] = set()
        query_lower = query.lower()

        for eid, entity in self._entities.items():
            props = entity.properties
            keys = properties if properties is not None else list(props.keys())
            for key in keys:
                value = props.get(key)
                if value is None:
                    continue
                text = str(value)
                score = fuzz.partial_ratio(query_lower, text.lower())
                if score >= threshold:
                    candidates.add(eid)
                    break

        return self._subgraph(candidates)

    def expand(
        self,
        *,
        depth: int = 1,
        entity_types: list[str] | None = None,
        via: str | None = None,
    ) -> Graph:
        """Grow this selection outward to include connected neighbours.

        Reaches into the root graph to find neighbours beyond the current
        subgraph — so ``crate.select(...).expand()`` discovers entities
        not in the initial selection.

        Args:
            depth: Number of hops outward (default 1).
            entity_types: Only include neighbours of these types.
            via: Only follow relationships of this type.

        Returns a new ``Graph`` (rooted at the same root) containing the
        original entities plus their neighbours.
        """

        root = self._root
        current = set(self._entities.keys())

        for _ in range(depth):
            new_neighbours: set[str] = set()
            for eid in current:
                for rel in root._relationships:
                    if rel.source == eid:
                        candidate = rel.target
                    elif rel.target == eid:
                        candidate = rel.source
                    else:
                        continue

                    if via is not None and rel.type != via:
                        continue

                    if candidate not in root._entities:
                        continue

                    if entity_types is not None and not set(entity_types).intersection(
                        root._entities[candidate].types
                    ):
                        continue

                    new_neighbours.add(candidate)

            current |= new_neighbours

        return root._subgraph(current)

    def pattern(
        self,
        *,
        from_type: str | None = None,
        via: str | None = None,
        to_type: str | None = None,
    ) -> Graph:
        """Match relationships by source type, relationship type, and/or target type.

        Returns a subgraph containing all matched source and target entities
        and the relationships between them.

        Args:
            from_type: Only include relationships from entities of this type.
            via: Only include relationships of this type.
            to_type: Only include relationships to entities of this type.

        All parameters are optional — omit any to match everything.
        """
        # Validate types if provided.
        if from_type is not None:
            self.types.validate(from_type)
        if to_type is not None:
            self.types.validate(to_type)
        if via is not None:
            self.relationship_types.validate(via)

        # No filters → return full graph.
        if from_type is None and via is None and to_type is None:
            return self._subgraph(set(self._entities.keys()))

        matched_ids: set[str] = set()
        for rel in self._relationships:
            if via is not None and rel.type != via:
                continue

            source_entity = self._entities.get(rel.source)
            target_entity = self._entities.get(rel.target)

            if source_entity is None or target_entity is None:
                continue

            if from_type is not None and from_type not in source_entity.types:
                continue

            if to_type is not None and to_type not in target_entity.types:
                continue

            matched_ids.add(rel.source)
            matched_ids.add(rel.target)

        return self._subgraph(matched_ids)

    def query(self, cypher: str) -> Graph:
        """Run a Cypher query and return a subgraph of matched entities.

        Requires ``grand-cypher`` — install via ``uv add crategraph[cypher]``.

        Args:
            cypher: A Cypher query string, or a bare pattern shorthand.

        Returns a new ``Graph`` containing matched entities and their
        mutual relationships.

        Examples::

            # Full Cypher
            crate.query("MATCH (a:Person)-[:author]->(b) RETURN a, b")

            # Shorthand — MATCH/RETURN added automatically
            crate.query("(a:Person)-[:author]->(b)")
        """
        from crategraph.core.query import run_cypher

        return run_cypher(self, cypher)

    # --- Private backend abstraction ---

    def _add_node(self, entity: Entity) -> None:
        """Add or replace an entity in the graph."""
        self._entities[entity.id] = entity
        if entity.source is not None:
            from pathlib import PurePosixPath

            self._source_names.add(PurePosixPath(entity.source).name)
        self._backend.add_node(entity.id, entity=entity)

    def _add_edge(self, relationship: Relationship) -> None:
        """Add a relationship to the graph."""
        self._relationships.append(relationship)
        self._backend.add_edge(
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
        if not self._backend.has_node(node_id):
            return set()
        return self._backend.successors(node_id) | self._backend.predecessors(node_id)

    def _subgraph(self, node_ids: set[str]) -> Graph:
        """Return a new Graph containing only the specified nodes and their mutual edges."""
        root = self._root
        new_backend = self._backend.subgraph(
            node_ids,
            self._entities,
            self._relationships,
        )
        sub = Graph.__new__(Graph)
        sub.source = self.source
        sub.metadata = dict(self.metadata)
        sub._entities = {nid: self._entities[nid] for nid in node_ids if nid in self._entities}
        sub._relationships = [
            r for r in self._relationships if r.source in node_ids and r.target in node_ids
        ]
        sub._source_names = set(self._source_names)
        sub._backend = new_backend
        sub._root = root
        return sub
