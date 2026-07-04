"""Pluggable 2D layout engines for graph visualisation.

Mirrors the house plugin convention (see ``Renderer`` in interfaces.py):
``LayoutEngine`` is the ABC, ``ENGINES`` lists the built-in implementations
in priority order, and ``resolve_engine`` picks one by name (or the first
available one when ``name`` is ``None``).

Two engines ship out of the box:

- ``ForceAtlas2RustEngine`` ("forceatlas2"): wraps the compiled
  ``crategraph_forceatlas2`` package — fast, deterministic (seeded), the
  preferred default.
- ``NxFallbackEngine`` ("nx"): pure-Python fallback using NetworkX's own
  ``forceatlas2_layout`` (present from NetworkX 3.5), used when the rust
  package is not installed.

Both engines operate on integer node indices ``[0, n_nodes)`` and undirected
edge pairs; callers own the mapping between graph entity IDs and indices.
Availability is probed lazily on every call (never cached), so callers can
simulate an uninstalled rust package mid-process (e.g. in tests) without
restarting.
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from collections.abc import Callable

_FORCEATLAS_INSTALL_HINT = 'pip install "crategraph[forceatlas]"'
_NX_LARGE_GRAPH_THRESHOLD = 2000


class LayoutEngine(ABC):
    """Base class for pluggable 2D layout backends."""

    name: str

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """Return ``(True, version)`` if usable, else ``(False, install_hint)``."""

    @abstractmethod
    def compute(
        self,
        n_nodes: int,
        edges: list[tuple[int, int]],
        *,
        iterations: int,
        settings: dict,
        progress_cb: Callable[[int, int], None] | None,
    ) -> dict[int, tuple[float, float]]:
        """Compute ``{index: (x, y)}`` positions for ``n_nodes`` indices.

        ``edges`` are undirected index pairs (no self-loops — callers must
        drop those before calling). ``settings`` uses graphology's camelCase
        ForceAtlas2 keys regardless of engine; each engine translates or
        drops what it does not support. ``progress_cb``, if given, is called
        as ``progress_cb(i, iterations)`` (1-based ``i``).
        """


class ForceAtlas2RustEngine(LayoutEngine):
    """Wraps the compiled ``crategraph_forceatlas2`` package."""

    name = "forceatlas2"

    def available(self) -> tuple[bool, str]:
        try:
            import crategraph_forceatlas2 as cfa2
        except ImportError:
            return False, f"not installed — {_FORCEATLAS_INSTALL_HINT}"
        return True, cfa2.__version__

    def compute(
        self,
        n_nodes: int,
        edges: list[tuple[int, int]],
        *,
        iterations: int,
        settings: dict,
        progress_cb: Callable[[int, int], None] | None,
    ) -> dict[int, tuple[float, float]]:
        import crategraph_forceatlas2 as cfa2

        positions = cfa2.layout(
            n_nodes,
            edges,
            init=None,
            seed=42,
            iterations=iterations,
            progress=progress_cb,
            **settings,
        )
        return {i: (float(x), float(y)) for i, (x, y) in enumerate(positions)}


# Explicit graphology-camelCase -> nx snake_case settings map. Anything not
# listed here and not in _NX_DROPPED_SETTINGS is left untranslated (and dropped
# with a warning) — in practice the render profile only ever supplies the keys
# covered below.
_NX_SETTINGS_MAP = {
    "gravity": "gravity",
    "strongGravityMode": "strong_gravity",
    "scalingRatio": "scaling_ratio",
    "linLogMode": "linlog",
    "outboundAttractionDistribution": "distributed_action",
}
_NX_DROPPED_SETTINGS = frozenset(
    {"adjustSizes", "barnesHutOptimize", "barnesHutTheta", "edgeWeightInfluence", "slowDown"}
)


class NxFallbackEngine(LayoutEngine):
    """Pure-Python fallback using NetworkX's ``forceatlas2_layout``.

    Requires a NetworkX version that ships ``forceatlas2_layout`` (from
    3.5). Settings the nx implementation has no equivalent for (Barnes-Hut
    approximation, slow-down) are dropped with a single warning rather than
    raising, so a settings dict written for the rust engine degrades
    gracefully here instead of erroring.
    """

    name = "nx"

    def available(self) -> tuple[bool, str]:
        import networkx as nx

        if getattr(nx, "forceatlas2_layout", None) is None:
            return False, (
                "this NetworkX version has no forceatlas2_layout — upgrade "
                f"NetworkX, or install the fast backend: {_FORCEATLAS_INSTALL_HINT}"
            )
        return True, nx.__version__

    def compute(
        self,
        n_nodes: int,
        edges: list[tuple[int, int]],
        *,
        iterations: int,
        settings: dict,
        progress_cb: Callable[[int, int], None] | None,
    ) -> dict[int, tuple[float, float]]:
        import networkx as nx

        graph = nx.Graph()
        graph.add_nodes_from(range(n_nodes))
        graph.add_edges_from(edges)

        nx_settings: dict[str, object] = {"max_iter": iterations}
        dropped = sorted(key for key in settings if key in _NX_DROPPED_SETTINGS)
        for key, value in settings.items():
            mapped = _NX_SETTINGS_MAP.get(key)
            if mapped is not None:
                nx_settings[mapped] = value
        if dropped:
            warnings.warn(
                f"nx layout engine does not support {', '.join(dropped)}; "
                "dropping — use the forceatlas2 engine for full settings support.",
                UserWarning,
                stacklevel=2,
            )

        if n_nodes >= _NX_LARGE_GRAPH_THRESHOLD:
            warnings.warn(
                f"layout will be slow without the forceatlas extra: {_FORCEATLAS_INSTALL_HINT}",
                UserWarning,
                stacklevel=2,
            )

        positions = nx.forceatlas2_layout(graph, seed=42, **nx_settings)

        if progress_cb is not None:
            # nx's forceatlas2_layout runs its own loop with no callback hook —
            # report a single completed step so callers relying on progress_cb
            # still see a final tick rather than silence.
            progress_cb(iterations, iterations)

        return {i: (float(x), float(y)) for i, (x, y) in positions.items()}


ENGINES: list[LayoutEngine] = [ForceAtlas2RustEngine(), NxFallbackEngine()]


def resolve_engine(name: str | None) -> LayoutEngine:
    """Resolve a layout engine by name, or the first available one if ``name`` is ``None``.

    Raises ``ValueError`` listing engine names and install hints if ``name``
    is unknown, or names an engine that is not currently available.
    """
    if name is None:
        for engine in ENGINES:
            if engine.available()[0]:
                return engine
        hints = "; ".join(f"{e.name} ({e.available()[1]})" for e in ENGINES)
        msg = f"No layout engine is available: {hints}"
        raise ValueError(msg)

    by_name = {engine.name: engine for engine in ENGINES}
    if name not in by_name:
        options = ", ".join(engine.name for engine in ENGINES)
        msg = f'Unknown layout engine "{name}". Available engines: {options}.'
        raise ValueError(msg)

    engine = by_name[name]
    ok, hint = engine.available()
    if not ok:
        msg = f'Layout engine "{name}" is not available: {hint}'
        raise ValueError(msg)
    return engine
