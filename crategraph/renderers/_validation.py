"""Shared validation helpers for renderer parameters."""

from __future__ import annotations

import re
from pathlib import Path

_CSS_DIMENSION_RE = re.compile(r"^[\d.]+(%|px|vh|vw|em|rem|ch)$")


def ensure_writable(filepath: str, overwrite: bool) -> None:
    """Guard a render-to-disk target against accidental clobbering.

    Mirrors the writers' contract (see ``crategraph.writers``): refuse to
    replace an existing file unless *overwrite* is ``True``.

    Args:
        filepath: The target path the renderer is about to write.
        overwrite: When ``True``, an existing file is replaced silently.

    Raises:
        FileExistsError: If *filepath* exists and *overwrite* is ``False``.
    """
    if not overwrite and Path(filepath).exists():
        msg = f"{filepath} already exists. Pass overwrite=True to replace it."
        raise FileExistsError(msg)


def validate_css_dimension(value: str, name: str) -> None:
    """Raise ``ValueError`` if *value* is not a safe CSS dimension.

    Accepts values like ``100vh``, ``100%``, ``600px``, ``50em``,
    ``50rem``, ``10ch``.
    """
    if not _CSS_DIMENSION_RE.match(value):
        msg = (
            f"Invalid CSS dimension for {name}: {value!r}. "
            f"Expected a value like '100vh', '100%', '600px', '50em', '50rem', or '10ch'."
        )
        raise ValueError(msg)
