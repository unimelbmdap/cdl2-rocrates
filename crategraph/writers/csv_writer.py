"""CSV writer — serialises a Graph to nodes.csv + edges.csv in a directory.

Tabular export for analysis tools (pandas, R, Excel). Uses the shared
``crategraph.writers._flatten`` utility so nodes carry the promoted
``id``/``label``/``type``/``types`` columns and edges carry
``source``/``target``/``type``/``rel_id``. Remaining property keys appear
alphabetically. Nested values round-trip via pipe-delimited lists or
sort-stable JSON (see ``docs/writers.md`` once it lands).

Line endings follow the stdlib ``csv`` module's default dialect (``\\r\\n``),
which maximises interoperability with Excel and RFC 4180. ``open()`` is called
with ``newline=""`` as the stdlib recommends so the csv module controls line
endings exclusively.
"""

from __future__ import annotations

import csv as stdcsv
from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core.interfaces import Writer
from crategraph.writers._flatten import (
    EDGE_PROMOTED_COLUMNS,
    NODE_PROMOTED_COLUMNS,
    flatten_edge,
    flatten_node,
)

if TYPE_CHECKING:
    from crategraph.core.graph import Graph


class CsvWriter(Writer):
    """Write a :class:`Graph` to ``nodes.csv`` and ``edges.csv``."""

    def can_write(self, path: str) -> bool:
        """Return True if *path* looks like a directory target.

        Accepts paths that end with ``/`` (explicit directory notation) or
        already exist as a directory on disc.
        """
        p = str(path)
        return p.endswith("/") or Path(p).is_dir()

    def write(
        self,
        graph: Graph,
        path: str,
        *,
        overwrite: bool = False,
        **kwargs: Any,
    ) -> None:
        """Serialise *graph* to ``nodes.csv`` and ``edges.csv`` inside *path*.

        Args:
            graph: The graph to serialise.
            path: Target directory path. Created (with parents) if absent.
            overwrite: When ``True``, replace an existing non-empty directory.
                Defaults to ``False``.
            **kwargs: Accepted for forward-compatibility; currently unused.

        Raises:
            FileExistsError: If *path* exists as a non-directory file, or if
                the directory is non-empty and *overwrite* is ``False``.
        """
        target = Path(path)
        if target.exists():
            if not target.is_dir():
                msg = f"{target} exists and is not a directory."
                raise FileExistsError(msg)
            if any(target.iterdir()) and not overwrite:
                msg = f"{target} is not empty. Pass overwrite=True to replace its contents."
                raise FileExistsError(msg)
        else:
            target.mkdir(parents=True)

        # Iterate the domain lists so export follows Graph's public relationship
        # model rather than NetworkX-specific edge attributes.
        node_rows = [flatten_node(e) for e in graph._entities.values()]
        edge_rows = [flatten_edge(r) for r in graph.relationships]

        _write_rows(target / "nodes.csv", node_rows, NODE_PROMOTED_COLUMNS)
        _write_rows(target / "edges.csv", edge_rows, EDGE_PROMOTED_COLUMNS)


def _ordered_fieldnames(rows: list[dict[str, Any]], promoted: tuple[str, ...]) -> list[str]:
    """Return fieldnames with promoted columns first, then remaining keys alphabetically.

    When *rows* is empty, returns all promoted columns so that an empty
    CSV still gets a meaningful header (e.g. edges.csv for a graph with no
    relationships). When *rows* is non-empty, only promoted columns that
    actually appear in at least one row are included (defensive — this keeps
    ``CsvWriter`` robust if ``_flatten``'s contract changes).
    """
    extra: set[str] = set()
    for row in rows:
        extra.update(row)
    remaining = sorted(k for k in extra if k not in promoted)
    if not rows:
        return list(promoted) + remaining
    return [k for k in promoted if any(k in row for row in rows)] + remaining


def _write_rows(target: Path, rows: list[dict[str, Any]], promoted: tuple[str, ...]) -> None:
    """Write *rows* to *target* as CSV with deterministic column ordering."""
    fieldnames = _ordered_fieldnames(rows, promoted)
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = stdcsv.DictWriter(f, fieldnames=fieldnames, quoting=stdcsv.QUOTE_MINIMAL)
        writer.writeheader()
        writer.writerows(rows)


__all__ = ["CsvWriter"]
