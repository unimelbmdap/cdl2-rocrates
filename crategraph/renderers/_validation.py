"""Shared validation helpers for renderer parameters."""

from __future__ import annotations

import re

_CSS_DIMENSION_RE = re.compile(r"^[\d.]+(%|px|vh|vw|em|rem|ch)$")


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
