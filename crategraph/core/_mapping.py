"""A read-only mapping view that reprs as a plain dict.

``types.MappingProxyType`` is the obvious way to hand out a read-only view of
an entity's or relationship's properties, but its ``repr`` wraps the dict in
``mappingproxy(...)``. That leaks into notebooks and the docs, where displaying
``entity.properties`` should read as a plain ``{...}`` dict. ``ReadOnlyMapping``
keeps the same guarantees (top-level assignment raises ``TypeError``; it stays a
live view of the underlying dict, so the documented shallow-mutation boundary is
unchanged) while reprensenting itself as the wrapped dict.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ReadOnlyMapping(Mapping):
    """A live, read-only view over a dict that displays as a plain dict."""

    __slots__ = ("_data",)

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def copy(self) -> dict[str, Any]:
        """Return a shallow, mutable ``dict`` copy (parity with ``MappingProxyType``)."""
        return dict(self._data)

    def __or__(self, other: Mapping[str, Any]) -> dict[str, Any]:
        """``view | other`` merges into a new plain ``dict`` (parity with ``MappingProxyType``)."""
        return {**self._data, **other}

    def __ror__(self, other: Mapping[str, Any]) -> dict[str, Any]:
        return {**other, **self._data}

    def __repr__(self) -> str:
        return repr(self._data)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Mapping):
            return dict(self._data) == dict(other)
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]  # mutable-valued like dict; unhashable
