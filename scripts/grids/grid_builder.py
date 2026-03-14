"""Build a sigma grid HTML page from a list of graph data dicts.

Not part of the crategraph public API — lives in examples/ for
experimental / report-generation use.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from markupsafe import Markup

_HERE = Path(__file__).resolve().parent
_TEMPLATE_PATH = _HERE / "templates" / "sigma_grid.html"
_BUNDLE_PATH = (
    _HERE.parents[1] / "crategraph" / "renderers" / "templates" / "vendor" / "sigma-fa2.min.js"
)


def _safe_json(obj: object) -> Markup:
    """JSON-encode with </script> escaping for safe inline embedding."""
    return Markup(json.dumps(obj).replace("</", "<\\/"))


def build_grid_html(
    grid_data: list[dict[str, Any]],
    *,
    columns: int = 0,
    cell_height: str = "280px",
    show_edges: bool = False,
) -> str:
    """Assemble a self-contained grid HTML page.

    Args:
        grid_data: List of dicts, each with keys ``graphData``,
            ``label``, ``totalNodes``, ``totalEdges``.
        columns: Grid columns (0 = auto).
        cell_height: CSS height per thumbnail cell.
        show_edges: Keep edges visible after layout.

    Returns:
        Complete HTML string.
    """
    if columns <= 0:
        columns = min(4, math.ceil(math.sqrt(len(grid_data))))

    config: dict[str, Any] = {"grid": True, "showEdges": show_edges}

    template = Markup(_TEMPLATE_PATH.read_text(encoding="utf-8"))
    bundle = Markup(_BUNDLE_PATH.read_text(encoding="utf-8"))

    return template % {
        "grid_data": _safe_json(grid_data),
        "config": _safe_json(config),
        "bundle": bundle,
        "columns": columns,
        "cell_height": cell_height,
    }
