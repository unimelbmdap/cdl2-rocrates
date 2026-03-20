"""CSV loader — TabularGraphReader subclass that reads CSV files via pandas.

Requires ``pandas`` — install via ``pip install crategraph[ohrm]``.
"""

from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import Any

from crategraph.core.graph import Graph
from crategraph.readers.shared.tabular import TabularGraphReader


def _require_pandas() -> Any:
    """Import and return pandas, raising a helpful error if unavailable."""
    try:
        import pandas as pd
    except ImportError:
        msg = (
            "pandas is required for the CSV reader. Install it with: pip install crategraph[ohrm]"
        )
        raise ImportError(msg) from None
    return pd


def _nan_to_none(value: Any) -> Any:
    """Convert NaN/NaT to None, pass everything else through."""
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


class CsvGraphReader(TabularGraphReader):
    """Read a directory of CSV files into a Graph.

    Each CSV file is matched to a configured table by its stem name
    (case-insensitive). Rows are normalised to ``list[dict]`` with
    ``None`` for missing values before graph-building.
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._csv_map: dict[str, Path] = {}

    def can_read(self, path: str) -> bool:
        """Return True if *path* is a directory containing at least one matching CSV."""
        p = Path(path)
        if not p.is_dir():
            return False
        expected = self._all_table_names()
        if not expected:
            return False
        csv_map = self._discover_csvs(p)
        return bool(expected & set(csv_map.keys()))

    def read(self, path: str) -> Graph:
        """Read CSV files at *path* and return a populated Graph."""
        _require_pandas()
        self._csv_map = self._discover_csvs(Path(path))
        return super().read(path)

    def _load_table(self, table_name: str) -> list[dict[str, Any]] | None:
        """Load a CSV by table name, returning rows as dicts or None."""
        pd = _require_pandas()
        key = table_name.upper()
        if key not in self._csv_map:
            warnings.warn(
                f"CSV file for table '{table_name}' not found — skipping.",
                stacklevel=3,
            )
            return None
        csv_path = self._csv_map[key]
        try:
            df = pd.read_csv(csv_path, encoding="utf-8")
        except UnicodeDecodeError:
            df = pd.read_csv(csv_path, encoding="latin-1")
        # Normalise NaN → None so base class only checks None.
        records = df.to_dict("records")
        return [{k: _nan_to_none(v) for k, v in row.items()} for row in records]

    def _discover_csvs(self, root: Path) -> dict[str, Path]:
        """Map upper-cased CSV stem names to their Paths, searching recursively."""
        csv_map: dict[str, Path] = {}
        for csv_file in root.rglob("*.csv"):
            csv_map[csv_file.stem.upper()] = csv_file
        return csv_map
