"""Inline notebook display helpers for renderers that emit a full HTML page."""

from __future__ import annotations

import html as _html
from typing import Any


def _iframe_height(height: str) -> str:
    """Concrete pixel height for an inline iframe.

    Viewport (``vh``) and percentage heights are meaningless for a frame
    embedded in a scrolling notebook output, so fall back to a sensible pixel
    height while honouring an explicit ``px`` request.
    """
    value = str(height).strip()
    return value if value.endswith("px") else "600px"


def _iframe_width(width: str) -> str:
    value = str(width).strip()
    return value if value.endswith(("px", "%")) else "100%"


def wrap_iframe(page: str, *, width: str = "100%", height: str = "100vh") -> Any:
    """Wrap a self-contained HTML *page* in an ``<iframe srcdoc>`` for inline display.

    Jupyter does not execute ``<script>`` tags inserted straight into cell
    output, so a script-driven renderer (sigma.js, 3d-force-graph) would show
    nothing. An iframe gives the page its own browsing context where its
    scripts run normally, the same approach pyvis uses.
    """
    from IPython.display import HTML

    # Coerce to a plain str first: ``page`` may be a markupsafe ``Markup``,
    # whose string methods re-escape their arguments and would double-escape
    # the payload (rendering the iframe as visible source instead of a graph).
    srcdoc = _html.escape(str(page), quote=True)
    # Wrap in a <div> so the payload does not start with "<iframe", which makes
    # IPython.display.HTML emit a "Consider using IFrame instead" warning
    # (IFrame takes a src URL, not the srcdoc we need here).
    frame = (
        f'<div class="crategraph-viz">'
        f'<iframe srcdoc="{srcdoc}" '
        f'style="width:{_iframe_width(width)};height:{_iframe_height(height)};'
        f'border:none;"></iframe>'
        f"</div>"
    )
    return HTML(frame)
