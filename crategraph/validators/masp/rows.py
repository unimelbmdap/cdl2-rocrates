"""Report rows and messages for the MASP validation engine."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from crategraph.validators.masp.values import parse_regex_literal
from crategraph.validators.report import make_row

if TYPE_CHECKING:
    from crategraph.validators.masp.profile import ClassRule, Profile

_SCHEMA = "http://schema.org/"
_NEAR_MISS_LIMIT = 5


def js_string(value: Any) -> str:
    """Describe a value the way JS ``String()`` / ``JSON.stringify`` would."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), ensure_ascii=False)
    return str(value)


def _compact(iri: str) -> str:
    return iri[len(_SCHEMA) :] if iri.startswith(_SCHEMA) else iri


def regex_flag_warnings(profile: Profile) -> list[dict]:
    """One warning per PropertyValue rule whose regexes use unsupported flags."""
    rows = []
    for rule in profile.property_values.values():
        flags: dict[str, None] = {}
        for value in rule.values:
            parsed = parse_regex_literal(value)
            if parsed is not None:
                flags.update(dict.fromkeys(parsed[1]))
        if flags:
            rows.append(
                make_row(
                    passed=False,
                    severity="warning",
                    rule="profile",
                    entity_id=rule.id,
                    property=None,
                    message=(
                        f"PropertyValue rule {rule.id} uses unsupported regex flags "
                        f"{''.join(flags)!r}; they are ignored"
                    ),
                    source=profile.source,
                )
            )
    return rows


def cardinality_row(
    rule: ClassRule, valid: int, near_misses: list[tuple[str, list[str]]], source: str
) -> dict:
    """The class rule's instance-count row; *near_misses* pairs ids with reasons."""
    types = ", ".join(sorted(_compact(t) for t in rule.type_iris))
    label = f"{rule.name} ({types})"
    passed = False
    if valid < rule.min_count:
        # Difference 1: explain each candidate that matched the types and failed.
        message = f"Expected at least {rule.min_count} instances of {label}, found {valid} valid."
        if near_misses:
            entries = [
                f"{node_id}: {'; '.join(reasons)}"
                for node_id, reasons in near_misses[:_NEAR_MISS_LIMIT]
            ]
            message += " Near misses: " + " | ".join(entries)
            if len(near_misses) > _NEAR_MISS_LIMIT:
                message += f" (+{len(near_misses) - _NEAR_MISS_LIMIT} more)"
    elif rule.max_count is not None and valid > rule.max_count:
        message = f"Expected at most {rule.max_count} instances of {label}, found {valid} valid."
    else:
        passed = True
        maximum = "unbounded" if rule.max_count is None else rule.max_count
        message = (
            f"Found {valid} valid instances of {label} "
            f"(expected between {rule.min_count} and {maximum})"
        )
    return make_row(
        passed=passed,
        severity=None if passed else "error",
        rule=rule.id,
        entity_id=None,
        property=None,
        message=message,
        source=source,
    )


def property_row(
    class_id: str,
    entity_id: str,
    name: str,
    passed: bool,
    severity: str | None,
    reason: str | None,
    source: str,
) -> dict:
    """One property rule's row for one entity."""
    message = f"Property `{name}` is valid" if passed else f"Property `{name}`: {reason}"
    return make_row(
        passed=passed,
        severity=severity,
        rule=class_id,
        entity_id=entity_id,
        property=name,
        message=message,
        source=source,
    )
