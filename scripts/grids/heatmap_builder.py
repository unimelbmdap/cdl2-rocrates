"""Build an adjacency-heatmap grid HTML page from a corpus.

Each crate gets a type-level adjacency matrix rendered as a heatmap.
Rows and columns are entity types; cell intensity = relationship count
between those types.

Not part of the crategraph public API — lives in examples/ for
experimental / report-generation use.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from markupsafe import Markup

_HERE = Path(__file__).resolve().parent
_TEMPLATE_PATH = _HERE / "templates" / "heatmap_grid.html"


def _safe_json(obj: object) -> Markup:
    """JSON-encode with </script> escaping for safe inline embedding."""
    return Markup(json.dumps(obj).replace("</", "<\\/"))


def graph_to_adjacency(graph: Any) -> dict[str, Any]:
    """Build a type-level adjacency matrix from a Graph.

    Returns a dict with keys: ``types`` (sorted list), ``matrix``
    (NxN list of lists), ``totalNodes``, ``totalEdges``.
    """

    # Use primary type (first in types list) to avoid compound type
    # strings like "RepositoryObject, DigitalObject, Review" creating
    # hundreds of unique categories.
    def _primary_type(entity: Any) -> str:
        if entity.types:
            return entity.types[0]
        return "Unknown"

    # Count relationships between each pair of primary types.
    pair_counts: Counter[tuple[str, str]] = Counter()
    for rel in graph._relationships:
        src = graph._entities.get(rel.source)
        tgt = graph._entities.get(rel.target)
        if src is None or tgt is None:
            continue
        pair_counts[(_primary_type(src), _primary_type(tgt))] += 1

    # Collect all types, sorted by total involvement (descending)
    # so the most connected types cluster at top-left.
    type_totals: Counter[str] = Counter()
    for (st, tt), count in pair_counts.items():
        type_totals[st] += count
        type_totals[tt] += count

    # Also include types with no relationships.
    for entity in graph._entities.values():
        t = _primary_type(entity)
        if t not in type_totals:
            type_totals[t] = 0

    types = [t for t, _ in type_totals.most_common()]

    # Build the matrix.
    type_idx = {t: i for i, t in enumerate(types)}
    n = len(types)
    matrix = [[0] * n for _ in range(n)]
    for (st, tt), count in pair_counts.items():
        i, j = type_idx[st], type_idx[tt]
        matrix[i][j] += count
        if i != j:
            matrix[j][i] += count  # symmetric

    return {
        "types": types,
        "matrix": matrix,
        "totalNodes": len(graph._entities),
        "totalEdges": len(graph._relationships),
    }


def build_heatmap_grid_html(
    heatmap_data: list[dict[str, Any]],
    *,
    columns: int = 0,
    cell_height: str = "320px",
) -> str:
    """Assemble a self-contained heatmap grid HTML page.

    Args:
        heatmap_data: List of dicts from ``graph_to_adjacency``, each
            augmented with a ``label`` key.
        columns: Grid columns (0 = auto).
        cell_height: CSS height per cell.

    Returns:
        Complete HTML string.
    """
    if columns <= 0:
        columns = min(4, math.ceil(math.sqrt(len(heatmap_data))))

    template = Markup(_TEMPLATE_PATH.read_text(encoding="utf-8"))

    return template % {
        "heatmap_data": _safe_json(heatmap_data),
        "columns": columns,
        "cell_height": cell_height,
    }
