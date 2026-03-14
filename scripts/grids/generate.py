"""Generate snapshot PNGs, PDF grids, and a Three.js gallery.

Pipeline:
  1. Build graph JSON via Corpus + SigmaRenderer
  2. Render the grid HTML headlessly (Playwright), extract PNG data URIs
  3. Save snapshots to scripts/grids/snapshots/
  4. Assemble PDFs from the saved PNGs (Pillow — no browser)
  5. Build a Three.js gallery HTML from the saved PNGs (instant load)

Usage (from repo root):
    uv run --with playwright --with pillow scripts/grids/generate.py

Requires Playwright browsers on first run:
    uv run --with playwright python -m playwright install chromium
"""

from __future__ import annotations

import base64
import json
import math
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT = Path(__file__).parent
SNAP_DIR = OUT / "snapshots"

from crategraph.core.corpus import Corpus  # noqa: E402

# ---- Configuration --------------------------------------------------------
# Glob patterns passed to Corpus to locate RO-Crate directories.  Each entry
# is resolved relative to DATA_DIR.  Adjust these to match your local data
# layout, or override DATA_DIR via the CRATEGRAPH_DATA environment variable.
DATA_DIR = Path(os.environ.get("CRATEGRAPH_DATA", str(ROOT / "data")))

CRATE_GLOBS = [
    "ldaca/Australian_Corpus_of_English",
    "ldaca/metadata_only/*",
    "ohrm/*/",
    "ohrm/metadata_only/*",
]

GRIDS = [
    {
        "name": "grid-all-crates",
        "kwargs": {},
    },
    {
        "name": "grid-all-crates-by-type",
        "kwargs": {
            "transform": lambda g: g.merge_nodes(by="type"),
            "show_edges": True,
        },
    },
]


# ---------------------------------------------------------------------------
# Phase 1: Render grid HTML headlessly → extract snapshots
# ---------------------------------------------------------------------------


def _render_snapshots(corpus: Corpus, name: str, **kwargs) -> list[dict]:
    """Render a grid via Playwright and return a list of card metadata
    with PNG file paths saved under ``SNAP_DIR/<name>/``."""
    from grid_builder import build_grid_html
    from playwright.sync_api import sync_playwright

    from crategraph.core.graph import Graph
    from crategraph.renderers.sigma import SigmaRenderer

    snap_subdir = SNAP_DIR / name
    snap_subdir.mkdir(parents=True, exist_ok=True)

    renderer = SigmaRenderer()
    transform = kwargs.get("transform")
    show_edges = kwargs.get("show_edges", False)
    colour_by = kwargs.get("colour_by", "type")
    size_by = kwargs.get("size_by", "connections")
    max_nodes = kwargs.get("max_nodes", 10_000)

    grid_data: list[dict] = []
    for path in corpus._resolved:
        reader = corpus._find_reader(path)
        if reader is None:
            continue
        try:
            graph = reader.read(path)
            total_entities = len(graph._entities)
            total_rels = len(graph._relationships)
            if transform is not None:
                graph = transform(graph)
            if max_nodes > 0 and len(graph._entities) > max_nodes:
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
            graph_json = renderer.graph_to_json(
                graph,
                colour_by=colour_by,
                size_by=size_by,
            )
            label = Path(path).stem or Path(path).name
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
        print(f"  [WARN] No crates loaded for {name}")
        return []

    grid_data.sort(key=lambda d: d["totalNodes"])
    html_str = build_grid_html(
        grid_data,
        show_edges=show_edges,
    )

    with tempfile.NamedTemporaryFile(
        suffix=".html",
        mode="w",
        encoding="utf-8",
        delete=False,
    ) as f:
        f.write(html_str)
        tmp_path = Path(f.name)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 900})
            page.goto(tmp_path.as_uri())

            # Wait until every sigma container has a snapshot <img>.
            page.wait_for_function(
                """() => {
                    const c = document.querySelectorAll('.sigma-container');
                    return c.length > 0
                        && c.length === document.querySelectorAll('.sigma-container img').length;
                }""",
                timeout=300_000,
            )

            # Extract card data from the rendered DOM.
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

    # Save PNGs to disk and build metadata.
    results = []
    for i, card in enumerate(cards):
        data_uri = card["dataUri"]
        if not data_uri.startswith("data:image/png;base64,"):
            continue
        png_bytes = base64.b64decode(data_uri.split(",", 1)[1])
        # Sanitise label for filename.
        safe_label = "".join(c if c.isalnum() or c in "-_" else "_" for c in card["label"])
        png_path = snap_subdir / f"{i:02d}_{safe_label}.png"
        png_path.write_bytes(png_bytes)
        results.append(
            {
                "png_path": str(png_path),
                "png_name": png_path.name,
                "label": card["label"],
                "meta": card["meta"],
            }
        )

    return results


# ---------------------------------------------------------------------------
# Phase 2: Assemble PDFs from saved PNGs (no browser needed)
# ---------------------------------------------------------------------------


def _build_pdf(cards: list[dict], pdf_path: Path, columns: int = 4) -> None:
    """Lay out snapshot PNGs in a grid and save as a single-page PDF."""
    from PIL import Image

    if not cards:
        return

    # Layout constants.
    cell_pad = 16
    label_height = 48
    bg_colour = (17, 17, 19)  # #111113
    cell_bg = (24, 24, 27)  # #18181b
    text_colour = (216, 218, 222)  # #d8dade
    meta_colour = (122, 126, 133)  # #7a7e85

    # Load first image to get cell dimensions.
    sample = Image.open(cards[0]["png_path"])
    img_w, img_h = sample.size
    cell_w = img_w + cell_pad * 2
    cell_h = img_h + label_height + cell_pad * 2

    rows = math.ceil(len(cards) / columns)
    gap = 16
    canvas_w = columns * cell_w + (columns - 1) * gap + gap * 2
    canvas_h = rows * cell_h + (rows - 1) * gap + gap * 2

    canvas = Image.new("RGB", (canvas_w, canvas_h), bg_colour)

    # Optional: draw labels if Pillow has text support.
    try:
        from PIL import ImageDraw, ImageFont

        draw = ImageDraw.Draw(canvas)
        try:
            font_label = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
            font_meta = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        except OSError:
            font_label = ImageFont.load_default()
            font_meta = ImageFont.load_default()
        has_draw = True
    except ImportError:
        has_draw = False

    for i, card in enumerate(cards):
        col = i % columns
        row = i // columns
        x = gap + col * (cell_w + gap)
        y = gap + row * (cell_h + gap)

        # Cell background.
        cell_img = Image.new("RGB", (cell_w, cell_h), cell_bg)
        canvas.paste(cell_img, (x, y))

        # Thumbnail.
        thumb = Image.open(card["png_path"])
        canvas.paste(thumb, (x + cell_pad, y + cell_pad))

        # Labels.
        if has_draw:
            label_y = y + cell_pad + img_h + 6
            draw.text((x + cell_pad, label_y), card["label"], fill=text_colour, font=font_label)
            draw.text((x + cell_pad, label_y + 22), card["meta"], fill=meta_colour, font=font_meta)

    canvas.save(str(pdf_path), "PDF", resolution=150.0)


# ---------------------------------------------------------------------------
# Phase 3: Three.js gallery from saved PNGs (no sigma bundle needed)
# ---------------------------------------------------------------------------

GALLERY_VARIANTS = [
    "grid",
    "sphere",
    "carousel",
    "amphitheatre",
]


def _encode_cards(cards: list[dict]) -> list[dict]:
    """Encode snapshot PNGs as base64 data URIs."""
    gallery_cards = []
    for card in cards:
        png_bytes = Path(card["png_path"]).read_bytes()
        data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode()
        gallery_cards.append(
            {
                "dataUri": data_uri,
                "label": card["label"],
                "meta": card["meta"],
            }
        )
    return gallery_cards


def _build_threejs_html(cards_json_str: str, variant: str) -> str:
    """Build a Three.js gallery HTML from a pre-encoded cards JSON string."""
    template = (OUT / "templates" / f"gallery_{variant}.html").read_text(encoding="utf-8")
    return template % {"cards_json": cards_json_str}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    corpus = Corpus(*(str(DATA_DIR / g) for g in CRATE_GLOBS))
    print(f"Resolved {len(corpus._resolved)} crate paths")

    all_cards: dict[str, list[dict]] = {}

    for grid in GRIDS:
        name = grid["name"]
        kwargs = grid["kwargs"]
        snap_subdir = SNAP_DIR / name

        # Phase 1: Render snapshots (skip if cached).
        cached = sorted(snap_subdir.glob("*.png")) if snap_subdir.exists() else []
        if cached:
            print(f"\n[{name}] Using {len(cached)} cached snapshots from {snap_subdir}/")
            cards = []
            for png in cached:
                parts = png.stem.split("_", 1)
                label = parts[1].replace("_", " ") if len(parts) > 1 else png.stem
                cards.append(
                    {
                        "png_path": str(png),
                        "label": label,
                        "meta": "",
                    }
                )
        else:
            print(f"\n[{name}] Rendering snapshots via headless Chromium...")
            cards = _render_snapshots(corpus, name, **kwargs)
            print(f"  {len(cards)} snapshots saved to {snap_subdir}/")

        all_cards[name] = cards

        # Phase 2: Assemble PDF.
        pdf_path = OUT / f"{name}.pdf"
        print("  Assembling PDF...")
        _build_pdf(cards, pdf_path)
        print(f"  -> {pdf_path}")

    # Phase 2b: Adjacency heatmap grid.
    print("\nBuilding adjacency heatmap grid...")
    from heatmap_builder import build_heatmap_grid_html, graph_to_adjacency

    heatmap_data: list[dict] = []
    for path in corpus._resolved:
        reader = corpus._find_reader(path)
        if reader is None:
            continue
        try:
            graph = reader.read(path)
            adj = graph_to_adjacency(graph)
            adj["label"] = Path(path).stem or Path(path).name
            heatmap_data.append(adj)
        except Exception:
            continue

    if heatmap_data:
        heatmap_data.sort(key=lambda d: len(d["types"]), reverse=True)
        heatmap_html = build_heatmap_grid_html(heatmap_data)
        heatmap_path = OUT / "heatmap-grid.html"
        heatmap_path.write_text(heatmap_html, encoding="utf-8")
        print(f"  {len(heatmap_data)} crates -> {heatmap_path}")

    # Phase 3: Three.js galleries (uses the first grid's snapshots).
    first_cards = all_cards.get(GRIDS[0]["name"], [])
    if first_cards:
        encoded = _encode_cards(first_cards)
        cards_json_str = json.dumps(encoded).replace("</", "<\\/")
        for variant in GALLERY_VARIANTS:
            template_path = OUT / "templates" / f"gallery_{variant}.html"
            if not template_path.exists():
                print(f"\n  Skipping gallery_{variant}.html (template not found)")
                continue
            print(f"\nBuilding gallery-{variant}.html ({len(first_cards)} cards)...")
            html = _build_threejs_html(cards_json_str, variant)
            out_path = OUT / f"gallery-{variant}.html"
            out_path.write_text(html, encoding="utf-8")
            print(f"  -> {out_path}")

    print("\nDone!")


if __name__ == "__main__":
    main()
