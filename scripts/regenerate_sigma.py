"""Regenerate all sigma HTML visualisations in examples/sigma/.

Usage (from repo root):
    uv run scripts/regenerate_sigma.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from crategraph.core.corpus import Corpus  # noqa: E402

DATA_DIR = Path(os.environ.get("CRATEGRAPH_DATA", str(ROOT / "data")))
OUT_DIR = ROOT / "examples" / "sigma"

CRATE_GLOBS = [
    "ldaca/Australian_Corpus_of_English",
    "ldaca/metadata_only/*",
    "ohrm/*/",
    "ohrm/metadata_only/*",
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    corpus = Corpus(*(str(DATA_DIR / g) for g in CRATE_GLOBS))
    paths = corpus._resolved
    print(f"Resolved {len(paths)} crate paths")

    for i, path in enumerate(paths, 1):
        reader = corpus._find_reader(path)
        if reader is None:
            continue
        label = Path(path).stem or Path(path).name
        out_path = str(OUT_DIR / f"{label}.html")

        try:
            t0 = time.perf_counter()
            graph = reader.read(path)
            n_nodes = len(graph._entities)
            n_edges = len(graph._relationships)
            graph.visualise(filepath=out_path)
            dt = time.perf_counter() - t0
            print(f"  [{i}/{len(paths)}] {label}: {n_nodes} nodes, {n_edges} edges ({dt:.1f}s)")
        except Exception as exc:
            print(f"  [{i}/{len(paths)}] {label}: FAILED — {exc}")

    print("\nDone!")


if __name__ == "__main__":
    main()
