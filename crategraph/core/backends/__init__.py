"""Graph backend factory — auto-detect available engines."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from crategraph.core.interfaces import GraphBackend


def networkx_backend() -> GraphBackend:
    """Return a fresh NetworkX backend."""
    from crategraph.core.backends.networkx import NetworkXBackend

    return NetworkXBackend()


def rustworkx_backend() -> GraphBackend:
    """Return a fresh rustworkx backend.

    Raises ``ImportError`` if rustworkx is not installed.
    """
    from crategraph.core.backends.rustworkx import RustworkxBackend

    return RustworkxBackend()


def default_backend() -> GraphBackend:
    """Return the best available backend (rustworkx if installed, else NetworkX)."""
    try:
        return rustworkx_backend()
    except ImportError:
        return networkx_backend()
