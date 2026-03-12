"""Corpus — profile and compare multiple crates."""

from __future__ import annotations

import glob as glob_mod
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

        Requires ``pandas`` — install via ``pip install pandas``.
        """
        from dataclasses import asdict

        import pandas as pd

        rows = [asdict(p) for p in self.profiles]
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
