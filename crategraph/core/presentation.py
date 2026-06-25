"""Visualisation, layout, and file access methods mixed into Graph.

Functions for rendering graphs (2D, 3D, SVG, sigma.js), computing
node positions, and accessing data files referenced by entities.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity, FileInfo, ViewInfo

_FA2_FALLBACK_LIMIT = 2000


def layout(graph: Graph) -> dict[str, tuple[float, float]]:
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
    if not graph._entities:
        return {}

    n = len(graph._entities)
    nx_undirected = graph._graph.to_undirected()

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

    if n > _FA2_FALLBACK_LIMIT:
        msg = (
            f"This graph has {n:,} nodes — the fallback spring layout "
            f"will be extremely slow without the fa2 package.\n"
            f"Install it with: pip install crategraph[fa2]"
        )
        raise ImportError(msg)

    import networkx as nx

    return nx.spring_layout(nx_undirected, seed=42)


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

    Returns a renderer-specific object (for inline notebook display)
    or the filepath string if *filepath* was provided.
    """
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

    return impl.render(
        target,
        colour_by=colour_by,
        size_by=size_by,
        edge_width=edge_width,
        height=height,
        width=width,
        filepath=filepath,
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


def inspect(graph: Graph, entity: Entity | str) -> FileInfo:
    """Inspect the data file associated with an entity.

    Reads the file referenced by a data entity and returns a preview
    with metadata. Requires ``markitdown`` — install via
    ``pip install crategraph[inspect]``.

    Args:
        graph: The graph containing the entity.
        entity: An ``Entity`` object or an entity ID string.

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


def view(graph: Graph, entity: Entity | str) -> ViewInfo:
    """View the data file associated with an entity.

    Returns a rich HTML preview of the file — images as ``<img>``
    tags, CSVs as HTML tables, audio with playback controls.

    Args:
        graph: The graph containing the entity.
        entity: An ``Entity`` object or an entity ID string.

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
