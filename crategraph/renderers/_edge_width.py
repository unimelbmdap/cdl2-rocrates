"""Shared per-edge width resolution for renderers.

``resolve_edge_widths`` is the one place the ``edge_width`` API is
interpreted. Returning ``None`` signals "caller should keep its own
default behaviour"; returning a list means "use these widths verbatim".
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.models import Relationship


def resolve_edge_widths(
    relationships: Sequence[Relationship],
    edge_width: int | float | str | None,
) -> list[float] | None:
    """Return per-edge widths, or ``None`` to mean 'renderer default'.

    Args:
        relationships: The edges to resolve widths for, in render order.
        edge_width:
            * ``None`` — return ``None`` (caller keeps existing behaviour).
            * ``int`` or ``float`` — every edge gets that literal width.
            * ``str`` — property name; per-edge width is
              ``1 + 2 * log1p(v)`` when ``v`` is a positive non-bool
              number, else ``1.0``.
    """
    if edge_width is None:
        return None
    if isinstance(edge_width, bool):
        # bool is a subclass of int — guard against `edge_width=True`
        # silently becoming `edge_width=1`.
        return [1.0] * len(relationships)
    if isinstance(edge_width, (int, float)):
        return [float(edge_width)] * len(relationships)

    widths: list[float] = []
    for rel in relationships:
        v = rel.properties.get(edge_width)
        # Exclude bool before the numeric check: isinstance(True, int) is
        # True in Python, and `bidirectional` is a real boolean edge
        # property. Without this, `edge_width="bidirectional"` would
        # encode True=~2.39 and False=1.0 rather than falling through.
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
            widths.append(1.0)
        else:
            widths.append(1.0 + 2.0 * math.log1p(v))
    return widths
