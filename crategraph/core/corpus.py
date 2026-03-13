"""Corpus — profile and compare multiple crates."""

from __future__ import annotations

import glob as glob_mod
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core.analysis import GraphProfile

if TYPE_CHECKING:
    from crategraph.core.interfaces import Reader


@dataclass
class CorpusProfile:
    """Aggregate profiling results across multiple crates."""

    profiles: list[GraphProfile] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)

    @property
    def crate_count(self) -> int:
        return len(self.profiles)

    @property
    def failure_count(self) -> int:
        return len(self.failures)

    def to_dataframe(self) -> Any:
        """Return profiles as a pandas DataFrame (one row per crate).

        Dict fields (``entity_type_counts``, ``relationship_type_counts``)
        are replaced with scalar summaries: ``top_entity_type`` and
        ``top_relationship_type`` (most common type name).

        Requires ``pandas`` — install via ``pip install pandas``.
        """
        from dataclasses import asdict

        import pandas as pd

        rows = []
        for p in self.profiles:
            row = asdict(p)
            # Replace dicts with the top type name for flat DataFrame output.
            etc = row.pop("entity_type_counts")
            rtc = row.pop("relationship_type_counts")
            row["top_entity_type"] = max(etc, key=etc.get) if etc else None
            row["top_relationship_type"] = max(rtc, key=rtc.get) if rtc else None
            rows.append(row)
        return pd.DataFrame(rows)

    def __repr__(self) -> str:
        from statistics import median

        lines = [f"=== Corpus Profile: {self.crate_count} crates ==="]
        if self.failure_count:
            lines.append(f"Failures: {self.failure_count}")
        if self.profiles:
            densities = [p.density for p in self.profiles]
            entities = [p.entity_count for p in self.profiles]
            lines.append(
                f"Entities: {min(entities)}\u2013{max(entities)} (median {median(entities):.0f})"
            )
            lines.append(
                f"Density: {min(densities):.4f}\u2013{max(densities):.4f} "
                f"(median {median(densities):.4f})"
            )
            components = [p.component_count for p in self.profiles]
            lines.append(
                f"Components: {min(components)}\u2013{max(components)} "
                f"(median {median(components):.0f})"
            )
        return "\n".join(lines)

    def _repr_html_(self) -> str:
        from html import escape

        return f"<pre style='font-size:13px; line-height:1.4'>{escape(repr(self))}</pre>"


class Corpus:
    """Load and profile multiple crates for comparative analysis.

    Accepts explicit paths or glob patterns. Each crate is loaded,
    profiled, and discarded — memory usage is constant regardless
    of corpus size.

    Profiles are only comparable when generated with the same reader
    configuration.  In particular, ``ROCrateReader``'s
    ``inline_relations`` setting dramatically affects edge count and
    density.  To compare settings, create separate ``Corpus`` instances
    and concatenate the DataFrames.

    Args:
        *paths: Paths to crate directories, metadata files, or
            glob patterns (e.g. ``"data/*/"``) that resolve to them.
        readers: Optional list of ``Reader`` instances to try for
            each path (in order).  Defaults to ``[ROCrateReader()]``.

    Examples::

        corpus = Corpus("data/ldaca/*")
        report = corpus.profile()
        report.to_dataframe().to_csv("profiles.csv")
    """

    def __init__(
        self,
        *paths: str,
        readers: list[Reader] | None = None,
    ) -> None:
        if not paths:
            msg = "Corpus requires at least one path or glob pattern."
            raise TypeError(msg)
        self._readers = readers
        self._resolved = self._resolve_paths(paths)
        if not self._resolved:
            msg = f"No crates found matching: {', '.join(paths)}"
            raise ValueError(msg)

    def _resolve_paths(self, paths: tuple[str, ...]) -> list[str]:
        """Expand globs and deduplicate paths."""
        resolved: list[str] = []
        seen: set[str] = set()
        for pattern in paths:
            expanded = glob_mod.glob(pattern)
            if expanded:
                for p in sorted(expanded):
                    real = str(Path(p).resolve())
                    if real not in seen:
                        seen.add(real)
                        resolved.append(p)
            elif not glob_mod.has_magic(pattern):
                # Direct path, not a glob — keep as-is (may be valid or invalid).
                real = str(Path(pattern).resolve())
                if real not in seen:
                    seen.add(real)
                    resolved.append(pattern)
            # else: glob pattern matched nothing — skip silently.
        return resolved

    def _find_reader(self, path: str) -> Reader | None:
        """Return a reader that can handle *path*, or None."""
        if self._readers is not None:
            readers = self._readers
        else:
            from crategraph.readers.rocrate import ROCrateReader

            readers = [ROCrateReader()]
        for reader in readers:
            if reader.can_read(path):
                return reader
        return None

    def profile(self) -> CorpusProfile:
        """Profile every crate and return aggregate results."""
        from crategraph.core.analysis import profile as profile_fn

        profiles: list[GraphProfile] = []
        failures: list[tuple[str, str]] = []

        for path in self._resolved:
            try:
                reader = self._find_reader(path)
                if reader is None:
                    failures.append((path, "No compatible reader found"))
                    continue
                graph = reader.read(path)
                p = profile_fn(graph)
                profiles.append(p)
            except Exception as exc:
                failures.append((path, str(exc)))

        return CorpusProfile(profiles=profiles, failures=failures)

    def visualise(
        self,
        *,
        colour_by: str = "type",
        size_by: str = "connections",
        columns: int = 0,
        cell_height: str = "280px",
        max_nodes: int = 10_000,
        show_edges: bool = False,
        transform: Callable[[Any], Any] | None = None,
        filepath: str | None = None,
    ) -> Any:
        """Render a grid of sigma thumbnails — one per crate.

        Each crate is loaded, converted to a graph JSON, then discarded
        (constant memory).

        Args:
            colour_by: Property to colour nodes by.
            size_by: Node sizing strategy.
            columns: Grid columns (0 = auto).
            cell_height: CSS height per thumbnail.
            show_edges: Keep edges visible in thumbnails (default hides
                them after layout to reduce visual clutter).
            transform: Optional callable applied to each ``Graph`` after
                loading (before sampling and JSON conversion).  For example
                ``lambda g: g.merge_nodes(by="type")`` to show a
                type-level summary of each crate.
            filepath: Save HTML to this path.

        Returns an ``IPython.display.HTML`` object or filepath string.
        """
        import json
        import math

        from markupsafe import Markup

        from crategraph.core.graph import Graph
        from crategraph.renderers.sigma import SigmaRenderer

        renderer = SigmaRenderer()
        grid_data: list[dict[str, Any]] = []

        for path in self._resolved:
            reader = self._find_reader(path)
            if reader is None:
                continue
            try:
                graph = reader.read(path)
                total_entities = len(graph._entities)
                total_rels = len(graph._relationships)
                if transform is not None:
                    graph = transform(graph)
                if max_nodes > 0 and len(graph._entities) > max_nodes:
                    # Keep top-N nodes by degree for a representative thumbnail.
                    ranked = sorted(
                        graph._entities,
                        key=lambda eid: len(graph._neighbours(eid)),
                        reverse=True,
                    )
                    keep = set(ranked[:max_nodes])
                    sampled = Graph(source=graph.source, metadata=graph.metadata)
                    for eid in keep:
                        sampled._add_node(graph._entities[eid])
                    for rel in graph._relationships:
                        if rel.source in keep and rel.target in keep:
                            sampled._add_edge(rel)
                    graph = sampled
                graph_json = renderer._graph_to_json(
                    graph,
                    colour_by=colour_by,
                    size_by=size_by,
                )
                label = Path(path).stem or Path(path).name
                # Show original counts so the label is accurate.
                grid_data.append(
                    {
                        "graphData": graph_json,
                        "label": label,
                        "totalNodes": total_entities,
                        "totalEdges": total_rels,
                    }
                )
            except Exception:
                continue

        if not grid_data:
            msg = "No crates could be loaded for visualisation."
            raise ValueError(msg)

        grid_data.sort(key=lambda d: d["totalNodes"])

        if columns <= 0:
            columns = min(4, math.ceil(math.sqrt(len(grid_data))))

        config: dict[str, Any] = {"grid": True, "showEdges": show_edges}
        template = renderer._load_template(variant="grid")
        bundle = renderer._load_bundle()

        def _safe_json(obj: object) -> Markup:
            return Markup(json.dumps(obj).replace("</", "<\\/"))

        html = template % {
            "grid_data": _safe_json(grid_data),
            "config": _safe_json(config),
            "bundle": bundle,
            "columns": columns,
            "cell_height": cell_height,
        }

        if filepath:
            with open(filepath, "w", encoding="utf-8") as fh:
                fh.write(html)
            return filepath

        from IPython.display import HTML

        return HTML(html)
