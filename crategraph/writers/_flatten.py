"""Shared attribute-flattening utility for writers producing scalar-only outputs.

GraphML and CSV both need node/edge attributes as scalar primitives. This
module converts the rich ``Entity`` / ``Relationship`` dataclasses (which
carry nested dicts and lists in ``properties``) into flat dicts whose values
are all ``str``/``int``/``float``/``bool``, with deterministic key order.

The encoding is round-trippable:
- Scalars (str/int/float/bool) pass through unchanged.
- ``None`` becomes the empty string ``""`` (for GraphML compatibility).
- Lists of scalars become pipe-delimited strings. ``\\`` is escaped as
  ``\\\\`` first, then ``|`` as ``\\|``. Decoders split on unescaped ``|``
  then reverse the escape pairs.
- Nested dicts, lists of dicts, and anything else not covered above are
  serialised via ``json.dumps(value, sort_keys=True, ensure_ascii=False)``.

Keys follow a deterministic order: promoted columns first in the fixed
order declared below, then remaining property keys sorted alphabetically.
Property keys that collide with a promoted column are re-emitted under
``prop_<key>``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from crategraph.core.models import Entity, Relationship

NODE_PROMOTED_COLUMNS: tuple[str, ...] = ("id", "label", "type", "types")
EDGE_PROMOTED_COLUMNS: tuple[str, ...] = ("source", "target", "type", "rel_id")

_NODE_COLLISION_KEYS: frozenset[str] = frozenset(NODE_PROMOTED_COLUMNS)
_EDGE_COLLISION_KEYS: frozenset[str] = frozenset(EDGE_PROMOTED_COLUMNS)

_ScalarValue = str | int | float | bool


def _unique_key(base: str, collision_keys: frozenset[str], taken: set[str]) -> str:
    """Return an output key that won't clobber an existing column.

    If *base* is one of the promoted column names (*collision_keys*) or is
    already present in *taken*, prepend ``prop_`` repeatedly until the key
    is unused. This preserves both values when an entity carries both a
    promoted-name property and its already-prefixed form — for example
    ``{"id": ..., "prop_id": ...}`` becomes ``{"prop_id": ..., "prop_prop_id": ...}``.
    """
    key = base
    while key in collision_keys or key in taken:
        key = f"prop_{key}"
    return key


def _encode_pipe_list(items: Sequence[Any]) -> str:
    """Encode a sequence of scalars (or None) as a pipe-delimited string.

    Backslashes are escaped first, then pipes, so the encoding is reversible
    via :func:`decode_pipe_list`.
    """
    parts: list[str] = []
    for item in items:
        s = "" if item is None else str(item)
        # Escape backslashes first, then pipes.
        s = s.replace("\\", "\\\\").replace("|", "\\|")
        parts.append(s)
    return "|".join(parts)


def decode_pipe_list(encoded: str) -> list[str]:
    """Inverse of the pipe-list encoder. Returns strings — upstream types are lost.

    Convention: empty string returns ``[]``. A single empty element (encoded as
    ``""`` within a non-empty list) is returned as ``[""]``.
    """
    if not encoded:
        return []

    parts: list[str] = []
    current: list[str] = []
    i = 0
    while i < len(encoded):
        ch = encoded[i]
        if ch == "\\":
            # Consume the next character literally (escape sequence).
            i += 1
            if i < len(encoded):
                current.append(encoded[i])
        elif ch == "|":
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    parts.append("".join(current))
    return parts


def _is_scalar(value: Any) -> bool:
    """Return True if *value* is a scalar type (str, int, float, bool, or None)."""
    # bool must be checked before int because bool is a subclass of int.
    return value is None or isinstance(value, (bool, int, float, str))


def _encode_value(value: Any) -> _ScalarValue:
    """Encode a single property value as a scalar-compatible type.

    - ``None`` → ``""``
    - ``bool`` → passed through (checked before ``int``).
    - ``int``, ``float``, ``str`` → passed through.
    - List / tuple of scalars → pipe-delimited string via :func:`_encode_pipe_list`.
    - Anything else (dict, list of dicts, etc.) → JSON string.
    """
    if value is None:
        return ""
    # bool before int — bool is a subclass of int.
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        if all(_is_scalar(item) for item in value):
            return _encode_pipe_list(value)
        # Contains non-scalar elements — fall through to JSON.
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    # Last-resort fallback for arbitrary objects.
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def flatten_node(entity: Entity) -> dict[str, _ScalarValue]:
    """Return a flat, scalar-only dict representing *entity*.

    Promoted columns appear first in :data:`NODE_PROMOTED_COLUMNS` order,
    then remaining property keys sorted alphabetically. Property keys that
    collide with a promoted column are emitted as ``prop_<key>``.
    """
    # --- Promoted columns ---

    # label: name > title > id fallback chain.
    name_val = entity.properties.get("name")
    title_val = entity.properties.get("title")
    if name_val and isinstance(name_val, str):
        label: str = name_val
    elif title_val and isinstance(title_val, str):
        label = title_val
    elif name_val is not None and name_val != "":
        # name present but not a str — coerce.
        label = str(name_val)
    elif title_val is not None and title_val != "":
        label = str(title_val)
    else:
        label = entity.id

    # type: first entry of entity.types or "".
    node_type: str = entity.types[0] if entity.types else ""

    # types: pipe-delimited list or "".
    types_encoded: str = _encode_pipe_list(entity.types) if entity.types else ""

    result: dict[str, _ScalarValue] = {
        "id": entity.id,
        "label": label,
        "type": node_type,
        "types": types_encoded,
    }

    # --- Properties (sorted alphabetically, collision-prefixed) ---
    _encode_properties(entity.properties, _NODE_COLLISION_KEYS, result)

    return result


def flatten_edge(rel: Relationship) -> dict[str, _ScalarValue]:
    """Return a flat, scalar-only dict representing *rel*.

    Promoted columns appear first in :data:`EDGE_PROMOTED_COLUMNS` order,
    then remaining property keys sorted alphabetically. Property keys that
    collide with a promoted column are emitted as ``prop_<key>``.
    """
    result: dict[str, _ScalarValue] = {
        "source": rel.source,
        "target": rel.target,
        "type": rel.type,
        "rel_id": rel.id or "",
    }

    _encode_properties(rel.properties, _EDGE_COLLISION_KEYS, result)

    return result


def _encode_properties(
    properties: dict[str, Any],
    collision_keys: frozenset[str],
    result: dict[str, _ScalarValue],
) -> None:
    """Encode *properties* into *result* in place with deterministic naming.

    Non-colliding keys are emitted first (preserving user-defined names),
    then collision-named keys via :func:`_unique_key` which prepends
    ``prop_`` repeatedly until the target name is unused.
    """
    taken: set[str] = set(result)
    # Sort with non-colliding keys first so user-defined names are preserved.
    ordered = sorted(properties, key=lambda k: (k in collision_keys, k))

    for key in ordered:
        out_key = _unique_key(key, collision_keys, taken)
        result[out_key] = _encode_value(properties[key])
        taken.add(out_key)


__all__ = [
    "EDGE_PROMOTED_COLUMNS",
    "NODE_PROMOTED_COLUMNS",
    "decode_pipe_list",
    "flatten_edge",
    "flatten_node",
]
