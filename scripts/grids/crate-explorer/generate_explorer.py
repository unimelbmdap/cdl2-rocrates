"""Generate a Three.js gallery with "Enter Crate" ForceGraph3D exploration.

Produces an output folder with:
  - index.html         (lightweight gallery — card metadata only)
  - snapshots/*.png    (sigma graph thumbnails)
  - graphs/*.json      (ForceGraph3D data, loaded on demand)

Usage (from repo root):
    uv run --with playwright --with pillow scripts/grids/crate-explorer/generate_explorer.py
    uv run --with playwright --with pillow \
        scripts/grids/crate-explorer/generate_explorer.py --colour-by community

Then serve the output folder:
    python -m http.server -d scripts/grids/crate-explorer/output 8000

Requires Playwright browsers on first run:
    uv run --with playwright python -m playwright install chromium
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GRIDS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(GRIDS_DIR))

OUT = Path(__file__).resolve().parent
TEMPLATE_PATH = OUT / "templates" / "explorer_grid.html"
CUBE_TEMPLATE_PATH = OUT / "templates" / "explorer_cube.html"
VIEWER_TEMPLATE_PATH = OUT / "templates" / "crate_viewer.html"

from crategraph.core.corpus import Corpus  # noqa: E402
from crategraph.core.graph import Graph  # noqa: E402
from crategraph.renderers.forcegraph3d import ForceGraph3DRenderer  # noqa: E402
from crategraph.renderers.sigma import SigmaRenderer  # noqa: E402

# ---- Configuration --------------------------------------------------------
DATA_DIR = Path(os.environ.get("CRATEGRAPH_DATA", str(ROOT / "data")))

CRATE_GLOBS = [
    "ldaca/Australian_Corpus_of_English",
    "ldaca/metadata_only/*",
    "ohrm/*/",
    "ohrm/metadata_only/*",
]

MAX_NODES = 10_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cap_graph(graph: Graph) -> Graph:
    """Apply MAX_NODES cap, keeping the most connected nodes."""
    if MAX_NODES <= 0 or len(graph._entities) <= MAX_NODES:
        return graph
    ranked = sorted(
        graph._entities,
        key=lambda eid: len(graph._neighbours(eid)),
        reverse=True,
    )
    keep = set(ranked[:MAX_NODES])
    sampled = Graph(source=graph.source, metadata=graph.metadata)
    for eid in keep:
        sampled._add_node(graph._entities[eid])
    for rel in graph._relationships:
        if rel.source in keep and rel.target in keep:
            sampled._add_edge(rel)
    return sampled


def _safe_filename(label: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in label)


# ---------------------------------------------------------------------------
# Phase 1: Render sigma snapshots and save ForceGraph3D JSON
# ---------------------------------------------------------------------------


def _render_snapshots_and_graphs(
    corpus: Corpus,
    colour_by: str,
    snap_dir: Path,
    graph_dir: Path,
) -> list[dict]:
    """Render sigma snapshots headlessly and save ForceGraph3D JSON files.

    Returns a list of card dicts with keys:
        snapshot, graphFile, label, meta
    """
    from grid_builder import build_grid_html
    from playwright.sync_api import sync_playwright

    snap_dir.mkdir(parents=True, exist_ok=True)
    graph_dir.mkdir(parents=True, exist_ok=True)

    sigma_renderer = SigmaRenderer()
    fg3d_renderer = ForceGraph3DRenderer()

    grid_data: list[dict] = []
    graphs: list[dict] = []
    labels: list[str] = []

    for path in corpus._resolved:
        reader = corpus._find_reader(path)
        if reader is None:
            continue
        try:
            graph = reader.read(path)
            total_entities = len(graph._entities)
            total_rels = len(graph._relationships)
            graph = _cap_graph(graph)

            sigma_json = sigma_renderer.graph_to_json(
                graph, colour_by=colour_by, size_by="connections"
            )
            label = Path(path).stem or Path(path).name

            grid_data.append(
                {
                    "graphData": sigma_json,
                    "label": label,
                    "totalNodes": total_entities,
                    "totalEdges": total_rels,
                }
            )

            fg3d_graph = graph.collapse_edges()
            fg3d_json = fg3d_renderer._graph_to_json(
                fg3d_graph, colour_by=colour_by, size_by="connections"
            )
            # Build group-to-colour legend from the colour map.
            from crategraph.renderers._colours import (
                _resolve_group,
            )
            from crategraph.renderers._colours import (
                resolve_colour_map as _rcm,
            )

            _cmap = _rcm(fg3d_graph, colour_by)
            _group_colours: dict[str, str] = {}
            for eid, entity in fg3d_graph._entities.items():
                c = _cmap.get(eid)
                group = _resolve_group(entity, colour_by)
                if c and group not in _group_colours:
                    _group_colours[group] = c
            fg3d_json["typeColours"] = _group_colours
            graphs.append(fg3d_json)
            labels.append(label)

        except Exception:
            continue

    if not grid_data:
        print("  [WARN] No crates loaded")
        return []

    # Sort by node count (keep parallel arrays aligned).
    indices = sorted(range(len(grid_data)), key=lambda i: grid_data[i]["totalNodes"])
    grid_data = [grid_data[i] for i in indices]
    graphs = [graphs[i] for i in indices]
    labels = [labels[i] for i in indices]

    # Render sigma grid headlessly to extract snapshot PNGs.
    html_str = build_grid_html(grid_data, show_edges=False)

    with tempfile.NamedTemporaryFile(
        suffix=".html", mode="w", encoding="utf-8", delete=False
    ) as f:
        f.write(html_str)
        tmp_path = Path(f.name)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.goto(tmp_path.as_uri())

            page.wait_for_function(
                """() => {
                    const c = document.querySelectorAll('.sigma-container');
                    return c.length > 0
                        && c.length === document.querySelectorAll('.sigma-container img').length;
                }""",
                timeout=300_000,
            )

            cards = page.evaluate("""() => {
                const cells = document.querySelectorAll('.grid-cell');
                return Array.from(cells).map(cell => {
                    const img = cell.querySelector('.sigma-container img');
                    const label = cell.querySelector('.cell-label');
                    const meta = cell.querySelector('.cell-meta');
                    return {
                        dataUri: img ? img.src : '',
                        label: label ? label.textContent : '',
                        meta: meta ? meta.textContent : '',
                    };
                });
            }""")

            browser.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    # Save PNGs and graph JSON files.
    results = []
    for i, card in enumerate(cards):
        data_uri = card["dataUri"]
        if not data_uri.startswith("data:image/png;base64,"):
            continue

        safe_label = _safe_filename(card["label"])
        prefix = f"{i:02d}_{safe_label}"

        # Save snapshot PNG.
        png_bytes = base64.b64decode(data_uri.split(",", 1)[1])
        png_path = snap_dir / f"{prefix}.png"
        png_path.write_bytes(png_bytes)

        # Save graph JSON.
        graph_file = f"{prefix}.json"
        if i < len(graphs):
            graph_path = graph_dir / graph_file
            graph_path.write_text(json.dumps(graphs[i]), encoding="utf-8")
        else:
            graph_file = None

        results.append(
            {
                "snapshot": f"snapshots/{prefix}.png",
                "graphFile": f"graphs/{graph_file}" if graph_file else None,
                "label": card["label"],
                "meta": card["meta"],
            }
        )

    return results


# ---------------------------------------------------------------------------
# Phase 2: Build explorer HTML
# ---------------------------------------------------------------------------


def _build_explorer_html(cards_json_str: str) -> str:
    """Build the explorer HTML from the template."""
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    return template % {"cards_json": cards_json_str}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate crate explorer gallery")
    parser.add_argument(
        "--colour-by",
        default="type",
        help="Property to colour nodes by (default: type). Try 'community'.",
    )
    args = parser.parse_args()
    colour_by: str = args.colour_by

    # Output dirs include the colour scheme so variants don't collide.
    suffix = f"-{colour_by}" if colour_by != "type" else ""
    output_dir = OUT / f"output{suffix}"
    snap_dir = output_dir / "snapshots"
    graph_dir = output_dir / "graphs"

    corpus = Corpus(*(str(DATA_DIR / g) for g in CRATE_GLOBS))
    print(f"Resolved {len(corpus._resolved)} crate paths")
    print(f"Colour by: {colour_by}  →  {output_dir}/")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Check for cached snapshots.
    cached_snaps = sorted(snap_dir.glob("*.png")) if snap_dir.exists() else []
    cached_graphs = sorted(graph_dir.glob("*.json")) if graph_dir.exists() else []

    if cached_snaps:
        print(f"\nUsing {len(cached_snaps)} cached snapshots from {snap_dir}/")

        if cached_graphs:
            print(f"  Using {len(cached_graphs)} cached graph JSONs from {graph_dir}/")
            cards = []
            for png in cached_snaps:
                parts = png.stem.split("_", 1)
                label = parts[1].replace("_", " ") if len(parts) > 1 else png.stem
                graph_json_path = graph_dir / f"{png.stem}.json"
                cards.append(
                    {
                        "snapshot": f"snapshots/{png.name}",
                        "graphFile": f"graphs/{png.stem}.json"
                        if graph_json_path.exists()
                        else None,
                        "label": label,
                        "meta": "",
                    }
                )
        else:
            # Re-compute graph JSONs for cached snapshots.
            print("  Computing ForceGraph3D JSON for each crate...")
            graph_dir.mkdir(parents=True, exist_ok=True)
            fg3d_renderer = ForceGraph3DRenderer()
            graph_labels: list[tuple[str, str]] = []

            for path in sorted(corpus._resolved):
                reader = corpus._find_reader(path)
                if reader is None:
                    continue
                try:
                    graph = reader.read(path)
                    graph = _cap_graph(graph).collapse_edges()
                    fg3d_json = fg3d_renderer._graph_to_json(
                        graph, colour_by=colour_by, size_by="connections"
                    )
                    # Build group-to-colour legend.
                    from crategraph.renderers._colours import (
                        _resolve_group,
                    )
                    from crategraph.renderers._colours import (
                        resolve_colour_map as _rcm,
                    )

                    _cmap = _rcm(graph, colour_by)
                    _group_colours: dict[str, str] = {}
                    for eid, entity in graph._entities.items():
                        c = _cmap.get(eid)
                        group = _resolve_group(entity, colour_by)
                        if c and group not in _group_colours:
                            _group_colours[group] = c
                    fg3d_json["typeColours"] = _group_colours
                    label = Path(path).stem or Path(path).name
                    safe_label = _safe_filename(label)
                    graph_labels.append((label, safe_label))

                    # Find matching snapshot index.
                    matches = [p for p in cached_snaps if safe_label in p.stem]
                    if matches:
                        prefix = matches[0].stem
                    else:
                        prefix = f"{len(graph_labels) - 1:02d}_{safe_label}"

                    graph_path = graph_dir / f"{prefix}.json"
                    graph_path.write_text(json.dumps(fg3d_json), encoding="utf-8")
                except Exception:
                    continue

            cards = []
            for png in cached_snaps:
                parts = png.stem.split("_", 1)
                label = parts[1].replace("_", " ") if len(parts) > 1 else png.stem
                graph_json_path = graph_dir / f"{png.stem}.json"
                cards.append(
                    {
                        "snapshot": f"snapshots/{png.name}",
                        "graphFile": f"graphs/{png.stem}.json"
                        if graph_json_path.exists()
                        else None,
                        "label": label,
                        "meta": "",
                    }
                )
    else:
        print("\nRendering snapshots via headless Chromium...")
        cards = _render_snapshots_and_graphs(corpus, colour_by, snap_dir, graph_dir)
        print(f"  {len(cards)} snapshots + graph JSONs saved to {output_dir}/")

    if not cards:
        print("No cards to build explorer from.")
        return

    # Build explorer HTML (just card metadata, no embedded data).
    cards_json_str = json.dumps(cards).replace("</", "<\\/")
    html = _build_explorer_html(cards_json_str)

    out_path = output_dir / "index.html"
    out_path.write_text(html, encoding="utf-8")

    # Build cube variant.
    cube_template = CUBE_TEMPLATE_PATH.read_text(encoding="utf-8")
    cube_html = cube_template % {"cards_json": cards_json_str}
    cube_path = output_dir / "cube.html"
    cube_path.write_text(cube_html, encoding="utf-8")

    # Copy crate viewer HTML into output folder.
    import shutil

    viewer_out = output_dir / "crate-viewer.html"
    shutil.copy2(VIEWER_TEMPLATE_PATH, viewer_out)

    print(f"\nExplorer built: {out_path} ({len(cards)} cards)")
    print(f"Cube variant:   {cube_path}")
    print("\nTo view, serve the output folder:")
    print(f"  python -m http.server -d {output_dir} 8000")
    print("  Then open http://localhost:8000 (grid) or http://localhost:8000/cube.html (cube)")
    print("Done!")


if __name__ == "__main__":
    main()
