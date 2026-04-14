"""Writer plugins for exporting graph data to various formats."""

from __future__ import annotations

from crategraph.core.interfaces import Writer
from crategraph.writers.errors import UnknownFormatError

_REGISTRY: dict[str, type[Writer]] = {}


def register_writer(name: str, writer_cls: type[Writer]) -> None:
    """Register *writer_cls* under *name* for lookup via get_writer."""
    _REGISTRY[name] = writer_cls


def get_writer(name: str) -> type[Writer]:
    """Return the writer class registered under *name*.

    Raises:
        UnknownFormatError: if no writer is registered for *name*.
    """
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        msg = f"Unknown writer format {name!r}. Known formats: {known}."
        raise UnknownFormatError(msg) from exc


__all__ = ["UnknownFormatError", "get_writer", "register_writer"]

# --- Built-in writer registrations ---

from crategraph.writers.graphml import GraphMLWriter  # noqa: E402

register_writer("graphml", GraphMLWriter)
