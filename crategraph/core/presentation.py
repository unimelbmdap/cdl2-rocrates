"""Visualisation, layout, and file access methods mixed into Graph.

Functions for rendering graphs (2D, 3D, SVG, sigma.js), computing
node positions, and accessing data files referenced by entities.
"""

from __future__ import annotations

import sys
import warnings
from html import escape
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TextIO

    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity, FileInfo, ViewInfo
    from crategraph.core.views import EntityView

# Below this node count layout is fast, so we stay silent. Set to the same
# 2000 figure as the Barnes-Hut neighbourhood, where layout starts to get
# slow; note progress triggers at ``>= 2000`` whereas ``barnesHutOptimize``
# flips at ``> 2000``.
_LAYOUT_PROGRESS_MIN_NODES = 2000

# Granularity of the ``layout N%`` progress lines.
_PROGRESS_STEP_PERCENT = 5


def _in_notebook() -> bool:
    """True when running inside a Jupyter kernel (not a terminal or plain script)."""
    try:
        from IPython import get_ipython

        shell = get_ipython()
    except Exception:
        return False
    return shell is not None and shell.__class__.__name__ == "ZMQInteractiveShell"


def _render_profile(n: int) -> dict[str, Any]:
    """crategraph's ForceAtlas2 settings floor, keyed by graphology camelCase.

    Derived from graphology-layout-forceatlas2's ``inferSettings()``, with
    two deliberate departures chosen by eye across real crates: ``gravity``
    is 0.3 (inferSettings uses 0.05) and ``slowDown`` is 1 (not
    ``1 + log(order)``).
    """
    return {
        "outboundAttractionDistribution": False,
        "barnesHutOptimize": n > 2000,
        "barnesHutTheta": 0.5,
        "scalingRatio": 10,
        "strongGravityMode": True,
        "slowDown": 1,
        "gravity": 0.3,
    }


def _percentage_reporter(stream: TextIO) -> Callable[[int, int], None]:
    """A progress callback printing ``layout N%`` lines at ~5% steps."""
    last_step = -1

    def report(i: int, total: int) -> None:
        nonlocal last_step
        percent = 100 if total <= 0 else (i * 100) // total
        step = percent - percent % _PROGRESS_STEP_PERCENT
        if step > last_step:
            last_step = step
            print(f"layout {step}%", file=stream)

    return report


def _terminal_progress_reporter(stream: TextIO, label: str) -> Callable[[int, int], None]:
    """Return terminal progress feedback, using an updating bar on real TTYs."""
    print(label, file=stream)
    if not stream.isatty():
        return _percentage_reporter(stream)

    last_step = -1
    bar_width = 28

    def write_bar(percent: int) -> None:
        filled = (percent * bar_width) // 100
        bar = "#" * filled + "-" * (bar_width - filled)
        end = "\n" if percent >= 100 else ""
        print(f"\rlayout [{bar}] {percent:3d}%", end=end, file=stream, flush=True)

    write_bar(0)

    def report(i: int, total: int) -> None:
        nonlocal last_step
        percent = 100 if total <= 0 else (i * 100) // total
        step = percent - percent % _PROGRESS_STEP_PERCENT
        if step > last_step:
            last_step = step
            write_bar(step)

    return report


def _progress_bar_html(percent: int, label: str) -> str:
    """Return a compact notebook progress bar fragment."""
    safe_label = escape(label)
    return f"""
    <div style="font-family: system-ui, -apple-system, Segoe UI, sans-serif;
                max-width: 520px; margin: 0.4rem 0;">
      <div style="display: flex; justify-content: space-between;
                  font-size: 0.85rem; color: #4a4e59; margin-bottom: 0.25rem;">
        <span>{safe_label}</span>
        <span>{percent}%</span>
      </div>
      <div role="progressbar" aria-valuemin="0" aria-valuemax="100"
           aria-valuenow="{percent}"
           style="height: 8px; background: #e6e8eb; border-radius: 999px;
                  overflow: hidden;">
        <div style="height: 100%; width: {percent}%; background: #2ba89e;
                    transition: width 120ms ease-out;"></div>
      </div>
    </div>
    """


def _notebook_progress_reporter(n_nodes: int, n_relationships: int) -> Callable[[int, int], None]:
    """A progress callback that updates one inline Jupyter progress bar."""
    from IPython.display import HTML, display

    label = (
        f"Laying out {n_nodes:,} nodes and {n_relationships:,} relationships; "
        f"this can take a while for large graphs."
    )
    handle = display(HTML(_progress_bar_html(0, label)), display_id=True)
    last_step = -1

    def report(i: int, total: int) -> None:
        nonlocal last_step
        percent = 100 if total <= 0 else (i * 100) // total
        step = percent - percent % _PROGRESS_STEP_PERCENT
        if step > last_step:
            last_step = step
            handle.update(HTML(_progress_bar_html(step, label)))

    return report


def layout(
    graph: Graph,
    *,
    engine: str | None = None,
    gravity: float | None = None,
    iterations: int | None = None,
    layout_settings: dict[str, Any] | None = None,
    progress: bool = False,
) -> dict[str, tuple[float, float]]:
    """Compute 2D node positions for visualisation.

    Runs ForceAtlas2 through a pluggable layout engine: the compiled
    ``crategraph_forceatlas2`` package (fast, and seeded so layouts are
    reproducible run-to-run), with NetworkX's pure-Python
    ``forceatlas2_layout`` retained as a defensive fallback.

    Args:
        engine: Layout engine name (``"forceatlas2"`` or ``"nx"``).
            ``None`` (default) picks the first available engine, preferring
            the compiled backend.
        gravity: Pull towards the centre, in graphology/rust units (the old
            ``fa2`` dialect ran roughly 10x smaller under
            ``strongGravityMode``, so an fa2-era 0.05 is not comparable).
            ``None`` (default) means "not passed": the documented default of
            0.3 comes from the render profile. An explicit value here always
            wins, including over a ``gravity`` key in *layout_settings*.
        iterations: Number of layout iterations. ``None`` (default) uses an
            ``iterations`` key in *layout_settings* if present, else the size
            formula ``min(200, 50 + n // 100)``.
        layout_settings: Extra ForceAtlas2 settings (graphology camelCase
            keys, e.g. ``{"barnesHutTheta": 0.9}``), layered over the render
            profile. Keys an engine does not support are handled per engine:
            the rust engine rejects unknown keys, the nx engine drops
            unsupported ones with a warning.
        progress: When ``True`` and the graph is large enough to be slow
            (``>= _LAYOUT_PROGRESS_MIN_NODES`` nodes), print an upfront size
            line and ``layout N%`` lines at ~5% steps (on stdout in a
            notebook, stderr otherwise). The nx engine has no per-iteration
            hook, so it reports a single final tick. Defaults to ``False``
            here because ``layout()`` is often called programmatically, where
            such output would be surprising; ``visualise()`` opts in on the
            user's behalf.

    Returns ``{entity_id: (x, y)}`` with raw coordinates (not scaled
    to any canvas).
    """
    from crategraph.core.layout_engines import resolve_engine

    if not graph._entities:
        return {}

    # This function owns the id<->index mapping: engines work on integer
    # indices ``[0, n)`` in the graph's stable entity order.
    entity_ids = list(graph._entities)
    n = len(entity_ids)
    index_by_id = {entity_id: i for i, entity_id in enumerate(entity_ids)}

    # Deduped undirected integer edges. Self-loops are dropped: they inflate
    # a node's mass without contributing any useful layout force, and the
    # rust engine rejects them outright.
    edge_set: set[tuple[int, int]] = set()
    for rel in graph._relationships:
        a = index_by_id[rel.source]
        b = index_by_id[rel.target]
        if a != b:
            edge_set.add((a, b) if a < b else (b, a))
    edges = sorted(edge_set)

    # ``iterations`` precedence: named arg > layout_settings key > formula.
    # The key is always popped so it never reaches an engine's settings dict.
    settings = dict(layout_settings) if layout_settings else {}
    settings_iterations = settings.pop("iterations", None)
    if iterations is None:
        iterations = settings_iterations
    if iterations is None:
        iterations = min(200, 50 + n // 100)

    # Settings precedence: named gravity > layout_settings > render profile.
    merged_settings = {**_render_profile(n), **settings}
    if gravity is not None:
        merged_settings["gravity"] = gravity

    layout_engine = resolve_engine(engine)

    progress_cb = None
    if progress and n >= _LAYOUT_PROGRESS_MIN_NODES:
        m = len(graph._relationships)
        label = (
            f"Laying out {n:,} nodes and {m:,} relationships; "
            f"this can take a while for large graphs."
        )
        if _in_notebook():
            progress_cb = _notebook_progress_reporter(n, m)
        else:
            progress_cb = _terminal_progress_reporter(sys.stderr, label)

    positions = layout_engine.compute(
        n,
        edges,
        iterations=iterations,
        settings=merged_settings,
        progress_cb=progress_cb,
    )
    return {entity_ids[i]: xy for i, xy in positions.items()}


def visualise(
    graph: Graph,
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
    """Render the graph as a network visualisation.

    Args:
        graph: The graph to visualise.
        renderer: ``"2d"`` (default) for sigma.js WebGL, ``"3d"`` for
            3d-force-graph, ``"svg"`` for static SVG,
            ``"pyvis"`` for pyvis/vis.js (requires ``pip install crategraph[pyvis]``).
        colour_by: Property to colour nodes by (default ``"type"``).
            Any entity property or attribute works. ``"community"``
            auto-computes Louvain communities if not already present.
        size_by: ``"connections"`` (default) scales node size by degree.
        edge_width: Per-edge width control. ``None`` (default) keeps
            each renderer's own behaviour. A number sets every edge to
            that literal pixel width. A string is treated as an edge
            property name and width-encodes via ``1 + 2*log1p(v)``.
            Non-numeric / missing / zero / negative / boolean values
            fall back to 1.0.
        height: CSS height of the canvas.
        width: CSS width of the canvas.
        filepath: Save output to this path instead of returning
            the display object.
        collapse_edges: If ``True``, collapse parallel edges between
            the same pair of nodes before rendering.
        progress: When ``True`` (default), show layout progress for large
            graphs (an upfront size line plus ``layout N%`` lines at ~5%
            steps, on stdout in a notebook and stderr otherwise). Pass
            ``False`` to render silently. Has no effect on small graphs or
            the browser-side ``"3d"`` renderer.
        engine: Layout engine name, forwarded to :func:`layout`. Ignored
            (with a warning) by the ``"3d"`` renderer, whose layout runs
            client-side.
        gravity: Layout gravity, forwarded to :func:`layout`. Ignored (with
            a warning) by the ``"3d"`` renderer.
        iterations: Layout iteration count, forwarded to :func:`layout`.
            Ignored (with a warning) by the ``"3d"`` renderer.
        layout_settings: Extra ForceAtlas2 settings, forwarded to
            :func:`layout`. Ignored (with a warning) by the ``"3d"``
            renderer.

    Returns a renderer-specific object (for inline notebook display)
    or the filepath string if *filepath* was provided.
    """
    if renderer == "3d" and any(
        v is not None for v in (engine, gravity, iterations, layout_settings)
    ):
        warnings.warn(
            "engine/gravity/iterations/layout_settings are ignored by the "
            'client-side "3d" renderer — its layout runs in the browser.',
            UserWarning,
            stacklevel=2,
        )

    target = graph.collapse_edges() if collapse_edges else graph

    if renderer == "2d":
        from crategraph.renderers.sigma import SigmaRenderer

        impl = SigmaRenderer()
    elif renderer == "3d":
        from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer

        impl = ForceGraph3DRenderer()
    elif renderer == "svg":
        from crategraph.renderers.svg import SvgRenderer

        impl = SvgRenderer()
    elif renderer == "pyvis":
        from crategraph.renderers.pyvis import PyvisRenderer

        impl = PyvisRenderer()
    else:
        msg = (
            f'Unknown renderer "{renderer}". '
            'Choose "2d" (sigma.js, default), "3d" (3d-force-graph), '
            '"svg" (static SVG), or "pyvis" (pyvis/vis.js).'
        )
        raise ValueError(msg)

    layout_kwargs: dict[str, Any] = {}
    if renderer != "3d":
        layout_kwargs = {
            "engine": engine,
            "gravity": gravity,
            "iterations": iterations,
            "layout_settings": layout_settings,
        }

    return impl.render(
        target,
        colour_by=colour_by,
        size_by=size_by,
        edge_width=edge_width,
        height=height,
        width=width,
        filepath=filepath,
        progress=progress,
        **layout_kwargs,
        **kwargs,
    )


def glimpse(graph: Graph, *, filepath: str | None = None) -> Any:
    """Inline snapshot of the type-level graph structure.

    Always merges entities by primary type — shows one node per type
    with entity counts and weighted edges.  Designed for quick
    orientation in notebooks, not detailed exploration.

    Args:
        graph: The graph to glimpse.
        filepath: Save the output to this path instead of displaying
            inline.

    Returns a display object for notebook rendering, or the filepath
    string if *filepath* was provided.
    """
    from crategraph.core.analysis import merge_by_primary_type

    merged = merge_by_primary_type(graph)
    from crategraph.renderers.svg import SvgRenderer

    return SvgRenderer().render(
        merged,
        width=600,
        height=450,
        filepath=filepath,
    )


def gallery(
    graph: Graph,
    *,
    caption: str | None = "label",
    hover: str | Sequence[str] | None = None,
    columns: int = 4,
    limit: int | None = 48,
    filepath: str | None = None,
) -> Any:
    """Lay the graph's image-bearing entities out as a thumbnail gallery.

    Finds the entities that carry an image (a ``thumbnail`` property, or an
    image ``File`` itself), embeds each as a base64 data-URI, and arranges them
    in a CSS grid. Composes with ``where``/``select`` to gallery a subset.

    Args:
        graph: The graph to gallery.
        caption: Property shown as an always-visible caption below each
            thumbnail. ``"label"`` (the default) uses the entity's human label;
            ``None`` shows no caption.
        hover: Property, or sequence of properties, shown as the native hover
            tooltip (joined with ``" · "``). ``None`` adds no tooltip.
        columns: Number of grid columns.
        limit: Cap on the number of thumbnails. Every image is embedded inline,
            so this bounds the output size; it defaults to ``48`` and warns
            when more are available. Pass ``None`` to embed them all, or filter
            the graph first (e.g. ``graph.where(...)``).
        filepath: Save a self-contained HTML page here instead of displaying
            inline.

    Returns a display object for notebook rendering, or the filepath string if
    *filepath* was provided.
    """
    from crategraph.renderers.gallery import GalleryRenderer

    return GalleryRenderer().render(
        graph,
        caption=caption,
        hover=hover,
        columns=columns,
        limit=limit,
        filepath=filepath,
    )


def inspect(graph: Graph, entity: Entity | str | EntityView) -> FileInfo:
    """Inspect the data file associated with an entity.

    Reads the file referenced by a data entity and returns a preview
    with metadata. Requires ``markitdown`` — install via
    ``pip install crategraph[inspect]``.

    Args:
        graph: The graph containing the entity.
        entity: An ``Entity`` object, an ``EntityView``, or an entity ID string.

    Returns a ``FileInfo`` with the file's content, metadata, and size.

    Raises:
        KeyError: If the entity ID doesn't exist in the graph.
        ValueError: If the entity is contextual (``#``-prefixed or URL).
        FileNotFoundError: If the referenced file doesn't exist on disk.
    """
    from crategraph.core.models import FileInfo
    from crategraph.inspectors import find_inspector

    entity = graph._coerce_entity(entity)
    entity_id, file_path = graph._require_local_entity_file(entity, action="inspect")

    # Find an inspector.
    inspector = find_inspector(file_path)
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


def view(graph: Graph, entity: Entity | str | EntityView) -> ViewInfo:
    """View the data file associated with an entity.

    Returns a rich HTML preview of the file — images as ``<img>``
    tags, CSVs as HTML tables, audio with playback controls.

    Args:
        graph: The graph containing the entity.
        entity: An ``Entity`` object, an ``EntityView``, or an entity ID string.

    Returns a ``ViewInfo`` with the file's HTML preview and metadata.

    Raises:
        KeyError: If the entity ID doesn't exist in the graph.
        ValueError: If the entity is contextual (``#``-prefixed or URL).
        FileNotFoundError: If the referenced file doesn't exist on disk.
    """
    from crategraph.core.models import ViewInfo
    from crategraph.viewers import find_viewer

    entity = graph._coerce_entity(entity)
    entity_id, file_path = graph._require_local_entity_file(entity, action="view")

    # Find a viewer.
    viewer = find_viewer(file_path)
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
