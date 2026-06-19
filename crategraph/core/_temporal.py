"""One honest engine for coercing RO-Crate's messy date strings.

RO-Crate dates arrive as raw strings in a dozen shapes — ISO datetimes with a
space or a trailing ``Z``, human formats like ``"12 March 2017"`` or
``"Dec 1914"``, bare years, year ranges (``"1870-71"``), circa markers
(``"c.1966"``) and uncertain/decade forms (``"192?"``). Historically two
separate ad-hoc parsers handled slices of this: notebook string-slicing and a
regex inside ``filtering.py``. This module replaces both.

Design: a thin **domain engine** owns the cultural-heritage semantics that
general date libraries get wrong — *precision* (never fabricate a missing
day/month), year *ranges*, *circa*/*uncertain* qualifiers, and *decade*
forms — and delegates "parse one ordinary human date token" to
``python-dateutil``. The two-different-``default``-dates technique recovers the
real precision dateutil parsed (so ``"Dec 1914"`` is month-precision, not a
fabricated 14 Dec).

Two layers:

- :func:`parse_temporal` — a pure ``str -> TemporalValue | None`` parser. This
  is the conservative, pluggable unit (``convert_dates(parser=...)`` swaps it).
- :func:`entity_temporal` / :func:`matches_time_range` — graph-aware helpers
  that pick the right properties off an entity (preferring the machine
  ``*ISOString`` fields, folding in sibling ``*Modifier`` qualifiers) and feed
  the workhorse ``e.year`` / ``select(time_range=)``.

Stdlib + dateutil only; no graph imports (the helpers take a plain property
mapping), so the accessors work on a graphless test-constructed view too.
"""

from __future__ import annotations

import calendar
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import TYPE_CHECKING, Any, Literal

from dateutil import parser as _dateutil_parser

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

Precision = Literal["decade", "year", "month", "day"]

# Field precedence — moved here from filtering.py so the accessors, convert_dates
# and select(time_range=) all share one source of truth. ``*ISOString`` first:
# it is the machine-readable sibling of the human ``startDate``/``endDate``.
_TEMPORAL_RANGE_PAIRS: tuple[tuple[str, str], ...] = (
    ("startDateISOString", "endDateISOString"),
    ("startDate", "endDate"),
)
_TEMPORAL_POINT_KEYS: tuple[str, ...] = (
    "datePublished",
    "dateCreated",
    "dateModified",
    "date",
    "year",
)

# Sibling qualifier fields. Both correct and misspelt (``endDateModifer``,
# 341 occurrences in real crates) spellings are read, for each endpoint.
_START_MODIFIER_KEYS: tuple[str, ...] = ("startDateModifier", "startDateModifer", "dateModifier")
_END_MODIFIER_KEYS: tuple[str, ...] = ("endDateModifier", "endDateModifer", "dateModifier")

# ---------------------------------------------------------------------------
# Regexes for the shapes dateutil can't be trusted with
# ---------------------------------------------------------------------------

_CIRCA_RE = re.compile(
    r"^\s*(?:c\.?|ca\.?|circa)\s+?(?=\d)|^\s*(?:c\.?|ca\.?|circa)\.?\s*(?=\d)", re.I
)
_YEAR_ONWARDS_RE = re.compile(r"^\s*(\d{4})\?\s+onwards\s*$", re.I)
_YEAR_UNCERTAIN_RE = re.compile(r"^\s*(\d{4})\?\s*$")
_DECADE_QMARK_RE = re.compile(r"^\s*(\d{3})\?\s*$")
_DECADE_S_RE = re.compile(r"^\s*(\d{4})s\s*$")
_BARE_YEAR_RE = re.compile(r"^\s*(\d{4})\s*$")
_RANGE_RE = re.compile(r"^\s*(\d{4})\s*-\s*(\d{2,4})\s*$")

# Two probe defaults with every field distinct, so a field that stays equal
# across both was supplied by the string (see _parse_human).
_PROBE_A = datetime(1, 1, 1)
_PROBE_B = datetime(2, 6, 15)


@dataclass(frozen=True)
class TemporalValue:
    """What a single date string denotes — possibly itself a range.

    ``start``/``end`` bracket the value at its native precision (a year-only
    value spans Jan 1 → Dec 31; a decade spans ten years), so a partial date
    never masquerades as a precise one. ``year`` is the start year — the
    workhorse behind ``e.year``.
    """

    start: date | None
    end: date | None
    year: int | None
    precision: Precision | None
    circa: bool = False
    uncertain: bool = False
    is_range: bool = False


@dataclass(frozen=True)
class EntityTemporal:
    """An entity's combined temporal reading, drawn from its date fields."""

    start_date: date | None
    end_date: date | None
    year: int | None
    precision: Precision | None
    circa: bool
    uncertain: bool


# ---------------------------------------------------------------------------
# Layer A — the pure string parser
# ---------------------------------------------------------------------------


def parse_temporal(text: str) -> TemporalValue | None:
    """Parse one date string conservatively; ``None`` when genuinely ambiguous.

    Prefers ``None`` to a confident wrong guess. Handles ISO datetimes
    (space/``Z``/fractional), human formats via dateutil (with real precision),
    bare years, year ranges, circa, uncertain and decade forms. See the module
    docstring for the full pipeline.
    """
    if not isinstance(text, str):
        return None
    raw = text.strip()
    if not raw:
        return None

    # 1. Circa prefix — strip and flag, then parse the remainder.
    circa = False
    stripped = _CIRCA_RE.sub("", raw)
    if stripped != raw:
        circa = True
        raw = stripped.strip()

    # 2. Explicit uncertainty / decade rules, ordered, before the generic paths.
    m = _YEAR_ONWARDS_RE.match(raw) or _YEAR_UNCERTAIN_RE.match(raw)
    if m:
        return _year_value(int(m.group(1)), circa=circa, uncertain=True)
    m = _DECADE_QMARK_RE.match(raw)
    if m:
        return _decade_value(int(m.group(1)) * 10, circa=circa, uncertain=True)
    m = _DECADE_S_RE.match(raw)
    if m:
        return _decade_value((int(m.group(1)) // 10) * 10, circa=circa, uncertain=False)
    # A lone "?" anywhere that wasn't one of the shapes above is too ambiguous.
    if "?" in raw:
        return None

    # 3. Year range ("1870-71", "1945-1947") — but not ISO "YYYY-MM".
    ranged = _parse_range(raw, circa=circa)
    if ranged is not None:
        return ranged

    # 4. Bare year.
    m = _BARE_YEAR_RE.match(raw)
    if m:
        return _year_value(int(m.group(1)), circa=circa, uncertain=False)

    # 5. ISO fast path (cheap, precise) then dateutil for everything human.
    parsed = _parse_iso(raw) or _parse_human(raw)
    if parsed is None:
        return None
    d, precision = parsed
    return _point_value(d, precision, circa=circa, uncertain=False)


def _parse_range(raw: str, *, circa: bool) -> TemporalValue | None:
    """Parse "1870-71"/"1945-1947" as a year range; reject ISO "YYYY-MM".

    The second group is read as the end year (a 2-digit suffix completes the
    first year's century). Only a *forward* span (end > start) is a range —
    otherwise "2017-03" would parse to 2017→2003, so it falls through to be
    read as ISO March 2017 instead.
    """
    m = _RANGE_RE.match(raw)
    if m is None:
        return None
    start_year = int(m.group(1))
    tail = m.group(2)
    # A 2-digit suffix completes the start year's century (1870-71 -> 1871).
    end_year = (start_year // 100) * 100 + int(tail) if len(tail) == 2 else int(tail)
    if end_year <= start_year:
        return None
    return TemporalValue(
        start=date(start_year, 1, 1),
        end=date(end_year, 12, 31),
        year=start_year,
        precision="year",
        circa=circa,
        uncertain=False,
        is_range=True,
    )


def _parse_iso(raw: str) -> tuple[date, Precision] | None:
    """Stdlib fast path for ISO date / datetime strings (3.12 handles Z + ms)."""
    try:
        return datetime.fromisoformat(raw).date(), "day"
    except ValueError:
        pass
    try:
        return date.fromisoformat(raw), "day"
    except ValueError:
        return None


def _parse_human(raw: str) -> tuple[date, Precision] | None:
    """Delegate to dateutil, recovering true precision via two probe defaults.

    A field whose value is identical under both ``_PROBE_A`` and ``_PROBE_B``
    was supplied by the string; a field that changed with the default was
    fabricated, so it lowers the precision. If even the year was not supplied
    (pure time / day-month with no year), the string isn't a date → ``None``.
    """
    try:
        a = _dateutil_parser.parse(raw, default=_PROBE_A)
        b = _dateutil_parser.parse(raw, default=_PROBE_B)
    except (ValueError, OverflowError):
        return None
    if a.year != b.year:
        return None  # year came from the default → not really a date
    if a.month != b.month:
        return a.date(), "year"
    if a.day != b.day:
        return a.date(), "month"
    return a.date(), "day"


def _year_value(year: int, *, circa: bool, uncertain: bool) -> TemporalValue:
    return TemporalValue(
        start=date(year, 1, 1),
        end=date(year, 12, 31),
        year=year,
        precision="year",
        circa=circa,
        uncertain=uncertain,
    )


def _decade_value(decade_start: int, *, circa: bool, uncertain: bool) -> TemporalValue:
    return TemporalValue(
        start=date(decade_start, 1, 1),
        end=date(decade_start + 9, 12, 31),
        year=decade_start,
        precision="decade",
        circa=circa,
        uncertain=uncertain,
    )


def _point_value(d: date, precision: Precision, *, circa: bool, uncertain: bool) -> TemporalValue:
    """Build start/end brackets around a single parsed date at its precision."""
    if precision == "year":
        start, end = date(d.year, 1, 1), date(d.year, 12, 31)
    elif precision == "month":
        last = calendar.monthrange(d.year, d.month)[1]
        start, end = date(d.year, d.month, 1), date(d.year, d.month, last)
    else:  # day
        start = end = d
    return TemporalValue(
        start=start,
        end=end,
        year=d.year,
        precision=precision,
        circa=circa,
        uncertain=uncertain,
    )


# ---------------------------------------------------------------------------
# Layer B — entity-level helpers
# ---------------------------------------------------------------------------


def _looks_temporal_key(key: str) -> bool:
    """Heuristic for arbitrary date-ish property keys (preserved from filtering)."""
    lowered = key.lower()
    if _is_qualifier_key(key):
        return False
    return "date" in lowered or lowered == "year" or lowered.endswith("_year")


def _is_qualifier_key(key: str) -> bool:
    """Whether *key* is a qualifier/modifier, not a date value field.

    ``*Modifier``/``*Modifer`` (circa/uncertain flags) and ``dateQualifier``
    (free text) carry no parseable date themselves — they would otherwise be
    swept up by the ``"date" in key`` heuristic.
    """
    return key.lower().endswith(("modifier", "modifer", "qualifier"))


def _coerce_temporal(
    value: Any, parser: Callable[[str], TemporalValue | None]
) -> TemporalValue | None:
    """Parse a property value of *any* type into a ``TemporalValue``.

    Preserves the pre-refactor ``select`` behaviour: ``int`` and integral
    ``float`` are treated as years, lists yield their first parseable element,
    strings go through *parser*. ``bool`` is excluded (it is an ``int``
    subclass but never a year).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return _year_value(value, circa=False, uncertain=False)
    if isinstance(value, float):
        if math.isfinite(value) and value == int(value):
            return _year_value(int(value), circa=False, uncertain=False)
        return None
    if isinstance(value, str):
        return parser(value)
    if isinstance(value, (list, tuple)):
        for item in value:
            result = _coerce_temporal(item, parser)
            if result is not None:
                return result
    return None


def _modifier_flags(
    properties: Mapping[str, Any], keys: tuple[str, ...]
) -> tuple[bool, bool, bool]:
    """Read sibling ``*Modifier`` fields → (circa, uncertain, decade) flags."""
    circa = uncertain = decade = False
    for key in keys:
        value = properties.get(key)
        if not isinstance(value, str):
            continue
        token = value.strip().lower()
        if token == "c":
            circa = True
        elif token == "?":
            uncertain = True
        elif token == "s":
            decade = True
    return circa, uncertain, decade


def _apply_decade(value: TemporalValue) -> TemporalValue:
    """Downgrade a year-precision value to a decade (sibling ``*Modifier="s"``)."""
    if value.year is None or value.precision != "year":
        return value
    return _decade_value((value.year // 10) * 10, circa=value.circa, uncertain=value.uncertain)


def entity_temporal(
    properties: Mapping[str, Any],
    *,
    parser: Callable[[str], TemporalValue | None] = parse_temporal,
) -> EntityTemporal:
    """Combine an entity's date fields into one temporal reading.

    Tries each range pair in turn (``*ISOString`` first) and uses the **first
    pair that parses to a result** — so blank/unparseable ISO fields fall back
    to the human ``startDate``/``endDate`` pair. Failing that, falls back to the
    first point/date-ish field that parses. Sibling ``*Modifier`` qualifiers and
    any inline markers are OR-ed into one entity-level ``circa``/``uncertain``.
    """
    start_mod_c, start_mod_u, start_mod_s = _modifier_flags(properties, _START_MODIFIER_KEYS)
    end_mod_c, end_mod_u, end_mod_s = _modifier_flags(properties, _END_MODIFIER_KEYS)

    for start_key, end_key in _TEMPORAL_RANGE_PAIRS:
        start_tv = _coerce_temporal(properties.get(start_key), parser)
        end_tv = _coerce_temporal(properties.get(end_key), parser)
        if start_tv is None and end_tv is None:
            continue
        if start_tv is not None and start_mod_s:
            start_tv = _apply_decade(start_tv)
        if end_tv is not None and end_mod_s:
            end_tv = _apply_decade(end_tv)
        start_date = start_tv.start if start_tv else (end_tv.start if end_tv else None)
        end_date = end_tv.end if end_tv else (start_tv.end if start_tv else None)
        year = start_tv.year if start_tv else (end_tv.year if end_tv else None)
        precision = start_tv.precision if start_tv else (end_tv.precision if end_tv else None)
        circa = (
            start_mod_c
            or end_mod_c
            or bool(start_tv and start_tv.circa)
            or bool(end_tv and end_tv.circa)
        )
        uncertain = (
            start_mod_u
            or end_mod_u
            or bool(start_tv and start_tv.uncertain)
            or bool(end_tv and end_tv.uncertain)
        )
        return EntityTemporal(start_date, end_date, year, precision, circa, uncertain)

    # No range pair matched — try point/date-ish fields in precedence order.
    seen = {key for pair in _TEMPORAL_RANGE_PAIRS for key in pair}
    point_keys = list(_TEMPORAL_POINT_KEYS)
    point_keys.extend(k for k in properties if k not in seen and _looks_temporal_key(k))
    for key in point_keys:
        tv = _coerce_temporal(properties.get(key), parser)
        if tv is None:
            continue
        if start_mod_s or end_mod_s:
            tv = _apply_decade(tv)
        circa = tv.circa or start_mod_c or end_mod_c
        uncertain = tv.uncertain or start_mod_u or end_mod_u
        return EntityTemporal(tv.start, tv.end, tv.year, tv.precision, circa, uncertain)

    return EntityTemporal(None, None, None, None, False, False)


def has_temporal_field(
    properties: Mapping[str, Any],
    *,
    parser: Callable[[str], TemporalValue | None] = parse_temporal,
) -> bool:
    """Whether the entity carries a date field that *parses*.

    Modifier-only fields (``*Modifier``) and free-text ``dateQualifier`` do not
    count — used by ``convert_dates`` so an entity with only a qualifier gets no
    empty date columns.
    """
    return entity_temporal(properties, parser=parser).year is not None


def temporal_field_values(properties: Mapping[str, Any]) -> list[tuple[str, Any]]:
    """Present date *value* fields (key, value), in precedence order.

    Excludes qualifier/modifier fields and blank values. Used by
    ``convert_dates`` to decide whether an entity is "in scope" for coverage and
    to surface the offending field when its value won't parse.
    """
    found: list[tuple[str, Any]] = []
    seen: set[str] = set()

    def _consider(key: str) -> None:
        if key in seen or key not in properties:
            return
        seen.add(key)
        value = properties[key]
        if value is None or (isinstance(value, str) and not value.strip()):
            return
        found.append((key, value))

    for start_key, end_key in _TEMPORAL_RANGE_PAIRS:
        _consider(start_key)
        _consider(end_key)
    for key in _TEMPORAL_POINT_KEYS:
        _consider(key)
    for key in properties:
        if _looks_temporal_key(key):
            _consider(key)
    return found


def matches_time_range(
    properties: Mapping[str, Any],
    *,
    low: int,
    high: int,
    parser: Callable[[str], TemporalValue | None] = parse_temporal,
) -> bool:
    """Whether the entity falls within ``[low, high]`` (inclusive years).

    Reproduces the pre-refactor ``select(time_range=)`` semantics: a range pair
    matches when its span overlaps ``[low, high]``; a point/date-ish field
    matches when its year lies inside. Checks *all* candidate fields (any match
    wins), unlike :func:`entity_temporal` which picks one source.
    """
    for start_key, end_key in _TEMPORAL_RANGE_PAIRS:
        start_tv = _coerce_temporal(properties.get(start_key), parser)
        end_tv = _coerce_temporal(properties.get(end_key), parser)
        start_year = start_tv.year if start_tv else None
        end_year = end_tv.year if end_tv else None
        if start_year is None and end_year is None:
            continue
        if start_year is None:
            start_year = end_year
        if end_year is None:
            end_year = start_year
        if start_year <= high and end_year >= low:
            return True

    seen = {key for pair in _TEMPORAL_RANGE_PAIRS for key in pair}
    point_keys = list(_TEMPORAL_POINT_KEYS)
    point_keys.extend(k for k in properties if k not in seen and _looks_temporal_key(k))
    for key in point_keys:
        tv = _coerce_temporal(properties.get(key), parser)
        if tv is not None and tv.year is not None and low <= tv.year <= high:
            return True
    return False
