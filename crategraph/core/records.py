"""Native ``list[dict]`` export, notebook display, and value counts.

Module-level functions build plain Python records from a :class:`Graph`.
Each record is a dict with promoted keys first (``id``, ``label``,
``type``, ``types`` for entities; ``source``, ``target``, ``type``,
``rel_id`` for relationships), followed by non-colliding properties
sorted alphabetically, followed by any properties whose names collide
with a promoted key — those are emitted as ``prop_<key>`` (also
alphabetically within that group), matching :class:`CsvWriter`'s
convention so user-defined names are preserved when there is no actual
collision.

Property values are deep-copied so callers can mutate returned records
freely without touching graph state. Native Python types are preserved —
lists stay lists, dicts stay dicts, ``None`` stays ``None``. Wrap with
the DataFrame library of your choice::

    import pandas as pd

    nodes = pd.DataFrame(graph.entity_records())
    edges = pd.DataFrame(graph.relationship_records())

:func:`entity_records` / :func:`relationship_records` return
:class:`Records` — a ``list`` subclass that additionally renders as a
compact table in notebooks. :func:`entity_counts` /
:func:`relationship_counts` reuse the *same* record projection (so they
count exactly the columns the records show) to tally one field.

This module has no third-party dependencies.
"""

from __future__ import annotations

import copy
import html
from collections import Counter
from typing import TYPE_CHECKING, Any

from crategraph.core._properties import merge_properties
from crategraph.core.models import _derive_label

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from crategraph.core.graph import Graph
    from crategraph.core.models import Entity, Relationship


_ENTITY_PROMOTED_KEYS: frozenset[str] = frozenset({"id", "label", "type", "types"})
_RELATIONSHIP_PROMOTED_KEYS: frozenset[str] = frozenset({"source", "target", "type", "rel_id"})


# ---------------------------------------------------------------------------
# Records — list[dict] that renders as a humble preview table in notebooks
# ---------------------------------------------------------------------------

# Inline styles only (no CSS class): the repr must survive nbconvert / Colab /
# VS Code where no stylesheet loads, and must neutralise the host's default
# table CSS (Jupyter adds borders/striping) so it reads as a plain preview, not
# a dataframe widget. Everything is left-aligned with no index column.
_WRAP_STYLE = (
    "font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; color: #222;"
)
_TITLE_STYLE = "color: #666; margin-bottom: 2px;"
_TABLE_STYLE = "border-collapse: collapse; border: none; background: none;"
_TH_STYLE = (
    "text-align: left; padding: 1px 12px 3px 0; border: none; "
    "border-bottom: 1px solid #ccc; color: #666; font-weight: 600; white-space: nowrap;"
)
_TD_STYLE = (
    "text-align: left; padding: 1px 12px 1px 0; border: none; "
    "white-space: nowrap; vertical-align: top;"
)
_FOOT_STYLE = "color: #999; margin-top: 3px;"


def _format_cell(value: Any) -> str:
    """Render a single record value as a plain string for HTML display."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return ", ".join(str(item) for item in value)
    return str(value)


class Records(list):
    """A ``list[dict]`` of records that renders as a compact table in notebooks.

    Returned by :meth:`Graph.entity_records`, :meth:`Graph.relationship_records`,
    :meth:`Graph.entity_counts` and :meth:`Graph.relationship_counts`. It
    subclasses ``list``, so it is a drop-in for a plain ``list[dict]`` —
    indexing, iteration, ``len()``, equality with a plain list, slicing (which
    returns a plain ``list``), and ``pd.DataFrame(records)`` all behave as
    before. The only addition is :meth:`_repr_html_`, a deliberately humble
    preview table (not a dataframe widget). Display only — counting/filtering
    live on :class:`~crategraph.core.graph.Graph`.

    Caps are display-only; the full data is always present in the list. Tune
    via the class attributes below.
    """

    #: Maximum body rows rendered (the full set stays in the list).
    max_display_rows: int = 20
    #: Maximum columns rendered before the rest are summarised in the footer.
    max_display_cols: int = 12
    #: Cell text longer than this is truncated with a trailing ``...``.
    max_cell_chars: int = 60

    def _truncate(self, value: Any) -> str:
        text = _format_cell(value)
        if len(text) > self.max_cell_chars:
            text = text[: self.max_cell_chars] + "..."
        return html.escape(text)

    def _repr_html_(self) -> str:
        n_rows = len(self)
        if n_rows == 0:
            return f'<div style="{_WRAP_STYLE}">Records: 0 rows</div>'

        # Column order = first-seen across records (promoted keys come first).
        all_columns = list(dict.fromkeys(key for record in self for key in record))
        n_cols = len(all_columns)
        shown_columns = all_columns[: self.max_display_cols]
        hidden_cols = n_cols - len(shown_columns)
        shown_rows = self[: self.max_display_rows]

        head = "".join(
            f'<th style="{_TH_STYLE}">{html.escape(str(col))}</th>' for col in shown_columns
        )
        body = "".join(
            "<tr>"
            + "".join(
                f'<td style="{_TD_STYLE}">{self._truncate(record.get(col))}</td>'
                for col in shown_columns
            )
            + "</tr>"
            for record in shown_rows
        )

        title = html.escape(f"Records: {n_rows:,} rows x {n_cols} fields")
        footer_parts: list[str] = []
        if n_rows > self.max_display_rows:
            footer_parts.append(f"Showing {len(shown_rows)} of {n_rows:,} rows")
        if hidden_cols > 0:
            footer_parts.append(f"+{hidden_cols} more columns")
        footer = (
            f'<div style="{_FOOT_STYLE}">{html.escape(" | ".join(footer_parts))}</div>'
            if footer_parts
            else ""
        )

        return (
            f'<div style="{_WRAP_STYLE}">'
            f'<div style="{_TITLE_STYLE}">{title}</div>'
            f'<table style="{_TABLE_STYLE}">'
            f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
            f"{footer}</div>"
        )


# ---------------------------------------------------------------------------
# Shared record builders (one source of truth for the column vocabulary)
# ---------------------------------------------------------------------------


def _add_properties(
    properties: dict[str, Any],
    promoted_keys: frozenset[str],
    record: dict[str, Any],
    *,
    deep_copy: bool = True,
) -> None:
    """Add *properties* into *record*, prefixing collisions with ``prop_``.

    Non-colliding property names are emitted in alphabetical order first
    so that user-defined names are preserved when possible. Property
    names that collide with a promoted key (or with an already-emitted
    key) get ``prop_`` prepended repeatedly until the name is unique.
    The collision/deep-copy rule lives in
    :func:`crategraph.core._properties.merge_properties`; this function
    owns only the records-export ordering policy. *deep_copy* is passed
    through — counters set it ``False`` to skip copying values they only read.
    """
    # Sort with non-colliding keys first so user-defined names survive when
    # there is no actual collision yet.
    ordered = sorted(properties, key=lambda k: (k in promoted_keys, k))
    merge_properties(record, properties, ordered, reserved=promoted_keys, deep_copy=deep_copy)


def _entity_record(entity: Entity, *, deep_copy: bool = True) -> dict[str, Any]:
    """Build one entity record. The single source of the entity column vocabulary."""
    record: dict[str, Any] = {
        "id": entity.id,
        "label": _derive_label(entity),
        "type": entity.types[0] if entity.types else "",
        "types": list(entity.types),
    }
    _add_properties(entity.properties, _ENTITY_PROMOTED_KEYS, record, deep_copy=deep_copy)
    return record


def _relationship_record(rel: Relationship, *, deep_copy: bool = True) -> dict[str, Any]:
    """Build one relationship record. The single source of the rel column vocabulary."""
    record: dict[str, Any] = {
        "source": rel.source,
        "target": rel.target,
        "type": rel.type,
        "rel_id": rel.id,
    }
    _add_properties(rel.properties, _RELATIONSHIP_PROMOTED_KEYS, record, deep_copy=deep_copy)
    return record


def _project(record: dict[str, Any], columns: list[str]) -> dict[str, Any]:
    """Keep just *columns* (in order), deep-copying the kept values.

    Every requested column is present in the output — missing ones are
    ``None`` — so a column selection yields a stable schema across records.
    """
    return {column: copy.deepcopy(record.get(column)) for column in columns}


def entity_records(graph: Graph, columns: Sequence[str] | None = None) -> Records:
    """Return one ``dict`` per entity with native Python values.

    Keys: ``id``, ``label``, ``type``, ``types`` first, then
    non-colliding entity properties sorted alphabetically, then any
    properties whose names collide with a promoted key emitted as
    ``prop_<key>``. ``label`` is derived from ``name → title → id``.
    ``type`` is the first entry of ``entity.types`` (or the empty
    string for an untyped entity). ``types`` is a ``list[str]``. Property
    values are deep-copied.

    Pass *columns* to project to just those keys, in that order — naming
    them as they appear here (``id``/``label``/``type``/``types`` or a
    property; a property colliding with a promoted name is ``prop_<key>``).
    Every requested column is present in every record (``None`` where the
    entity lacks it), so the result keeps a stable schema.

    Returns a :class:`Records` (a ``list`` subclass — drop-in compatible,
    plus a notebook table preview). Wrap with your DataFrame library::

        import pandas as pd
        df = pd.DataFrame(graph.entity_records())
    """
    if columns is None:
        return Records(_entity_record(entity) for entity in graph._entities.values())
    cols = list(columns)
    return Records(
        _project(_entity_record(entity, deep_copy=False), cols)
        for entity in graph._entities.values()
    )


def relationship_records(graph: Graph, columns: Sequence[str] | None = None) -> Records:
    """Return one ``dict`` per relationship with native Python values.

    Keys: ``source``, ``target``, ``type``, ``rel_id`` first, then
    non-colliding relationship properties sorted alphabetically, then
    any properties whose names collide with a promoted key emitted as
    ``prop_<key>``. ``rel_id`` is ``None`` for inline (non-reified)
    relationships, preserving the distinction between inline and reified
    rather than collapsing both to an empty string the way CSV does.
    Property values are deep-copied. Returns a :class:`Records`.

    Pass *columns* to project to just those keys (same rules as
    :func:`entity_records`).
    """
    if columns is None:
        return Records(_relationship_record(rel) for rel in graph.relationships)
    cols = list(columns)
    return Records(
        _project(_relationship_record(rel, deep_copy=False), cols) for rel in graph.relationships
    )


# ---------------------------------------------------------------------------
# Single-field value counts (reuse the record projection — count what you see)
# ---------------------------------------------------------------------------


def _count_key(item: Any) -> tuple[Any, Any]:
    """Return ``(counter_key, output_value)`` for one value.

    Hashable scalars keep their native type as both key and output (an
    ``int`` year stays ``int``). Unhashable values (dict/list) are
    stringified for output, with a type-tagged key so a dict's ``str()``
    cannot collide in the counter with a genuine string of the same text.
    """
    try:
        hash(item)
    except TypeError:
        text = str(item)
        return (type(item).__name__, text), text
    return item, item


def _count_values(records: Iterable[dict[str, Any]], field: str) -> Records:
    """Tally *field* across *records*, exploding list/tuple values.

    ``None``/absent values are skipped (pandas ``value_counts`` dropna
    parity). Rows are sorted count-descending, then by string value.
    """
    counter: Counter[Any] = Counter()
    output: dict[Any, Any] = {}
    for record in records:
        if field not in record:
            continue
        value = record[field]
        if value is None:
            continue
        items = value if isinstance(value, (list, tuple)) else (value,)
        for item in items:
            if item is None:
                continue
            key, out = _count_key(item)
            counter[key] += 1
            output.setdefault(key, out)

    rows = sorted(counter.items(), key=lambda kv: (-kv[1], str(output[kv[0]])))
    # Avoid a self-collision when counting a field literally named "count".
    count_col = "count" if field != "count" else "n"
    return Records({field: output[key], count_col: total} for key, total in rows)


def entity_counts(graph: Graph, field: str) -> Records:
    """Count entities by *field*, returning ``Records`` of ``{field, count}``.

    *field* names a column as it appears in :meth:`Graph.entity_records`
    (``id``/``label``/``type``/``types`` or a property; a property that
    collides with a promoted name is ``prop_<key>``), so counts always
    agree with the records. List-valued columns explode — ``"types"``
    counts each type membership, so totals may exceed the entity count.
    ``None``/absent values are skipped; rows are sorted count-descending.
    """
    return _count_values(
        (_entity_record(e, deep_copy=False) for e in graph._entities.values()), field
    )


def relationship_counts(graph: Graph, field: str) -> Records:
    """Count relationships by *field*, returning ``Records`` of ``{field, count}``.

    *field* names a column as it appears in
    :meth:`Graph.relationship_records` (``source``/``target``/``type``/
    ``rel_id`` or a property). Same semantics as :func:`entity_counts`.
    """
    return _count_values(
        (_relationship_record(r, deep_copy=False) for r in graph.relationships), field
    )
