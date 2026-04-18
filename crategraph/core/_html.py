"""Shared helpers for ``_repr_html_`` rendering in Jupyter notebooks."""

from __future__ import annotations

from html import escape

_PRE_STYLE = "font-size:13px; line-height:1.4"


def repr_pre(obj: object) -> str:
    """Render ``repr(obj)`` HTML-escaped in the standard styled ``<pre>``."""
    return f"<pre style='{_PRE_STYLE}'>{escape(repr(obj))}</pre>"


def text_pre(text: str) -> str:
    """Wrap pre-escaped *text* in the standard styled ``<pre>``."""
    return f"<pre style='{_PRE_STYLE}'>{text}</pre>"
