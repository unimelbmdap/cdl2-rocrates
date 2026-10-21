"""Validation engine: check a crate document against a parsed MASP profile.

Ports the class, property and value checks of ``masp-validator.js``
(``ClassRule.validate``, ``validateCardinality``,
``validatePropertyConstraints``, ``validateEntity`` and
``validatePropertyValue``), with the deliberate differences numbered as in
the user docs.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

from crategraph.validators.masp.context import normalise_iri
from crategraph.validators.masp.values import (
    check_literal,
    matches_item_list,
    matches_property_value,
    matches_template,
    parse_regex_literal,
)
from crategraph.validators.report import make_row

if TYPE_CHECKING:
    from crategraph.validators.masp.document import CrateDocument, Node
    from crategraph.validators.masp.profile import ClassRule, Profile, PropertyRule

Key = tuple[str, str]  # (entity id, class rule id)

_SCHEMA = "http://schema.org/"
_URL_RANGES = frozenset({_SCHEMA + "URL", "URL"})
_WEB_IRI = re.compile(r"^https?://[^\s/?#]+", re.IGNORECASE)
_NO_DEPS: frozenset[Key] = frozenset()
_NEAR_MISS_LIMIT = 5


class PropertyOutcome(NamedTuple):
    class_id: str
    entity_id: str
    property_rule_id: str
    passed: bool
    severity: str | None


class CardinalityOutcome(NamedTuple):
    class_id: str
    passed: bool
    valid_count: int


class _Result(NamedTuple):
    ok: bool
    assumed: frozenset[Key]


@dataclass(frozen=True)
class _Check:
    """One property rule's outcome on one entity."""

    rule: PropertyRule
    passed: bool
    severity: str | None
    reason: str | None
    assumed: bool  # the pass rested on an assumption still open at the time


@dataclass(frozen=True)
class _Record:
    ok: bool
    checks: tuple[_Check, ...]

    def reasons(self) -> list[str]:
        return [
            f"property `{_property_name(c.rule)}`: {c.reason}" for c in self.checks if not c.passed
        ]


def _property_name(rule: PropertyRule) -> str:
    return rule.name or rule.id


def _js_string(value: Any) -> str:
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


class ValidationRun:
    """One validation of *crate* against *profile*.

    ``run()`` returns the rows in emission order; afterwards ``outcomes``
    and ``cardinalities`` hold the structured results for the parity test.
    """

    def __init__(self, profile: Profile, crate: CrateDocument) -> None:
        self.profile = profile
        self.crate = crate
        self._reset()

    def _reset(self) -> None:
        self.outcomes: list[PropertyOutcome] = []
        self.cardinalities: list[CardinalityOutcome] = []
        self._final: dict[Key, _Record] = {}
        self._in_progress: set[Key] = set()
        self._order: list[tuple[Node, ClassRule]] = []
        self._seen: set[Key] = set()

    def run(self) -> list[dict]:
        self._reset()
        rows = self._regex_flag_warnings()
        for class_rule in self.profile.classes.values():
            if not class_rule.type_iris:
                continue  # warned at parse time
            valid, near_misses = 0, []
            for node in self.crate.nodes.values():
                if not self._types_match(node, class_rule):
                    continue
                if self.evaluate(node, class_rule).ok:
                    valid += 1
                else:
                    near_misses.append(node.id)
            rows.append(self._cardinality_row(class_rule, valid, near_misses))
        rows.extend(self._property_rows())
        return rows

    # -- entities -----------------------------------------------------------

    def _types_match(self, node: Node, class_rule: ClassRule) -> bool:
        # The JS rejects an entity with no @type even for a rule with no types.
        return bool(node.types) and class_rule.type_iris <= self.crate.type_iris(node)

    def evaluate(self, node: Node, class_rule: ClassRule) -> _Result:
        """Greatest-fixed-point check of *node* against *class_rule* (difference 4).

        A pair already in progress is assumed to pass. ``False`` is always
        final; ``True`` is final only when it rests on no open assumption,
        otherwise it is evaluated again once that assumption has settled.
        """
        if not self._types_match(node, class_rule):
            return _Result(False, _NO_DEPS)
        key = (node.id, class_rule.id)
        record = self._final.get(key)
        if record is not None:
            return _Result(record.ok, _NO_DEPS)
        if key in self._in_progress:
            return _Result(True, frozenset({key}))
        if key not in self._seen:
            self._seen.add(key)
            self._order.append((node, class_rule))

        self._in_progress.add(key)
        checks: list[_Check] = []
        assumed: set[Key] = set()
        for prule in class_rule.property_rules:
            passed, severity, reason, deps = self.check_property(node, prule)
            checks.append(_Check(prule, passed, severity, reason, bool(deps)))
            assumed |= deps
        self._in_progress.discard(key)
        assumed.discard(key)

        ok = all(check.passed for check in checks)
        if not ok or not assumed:
            self._final[key] = _Record(ok, tuple(checks))
        return _Result(ok, frozenset(assumed))

    # -- properties ---------------------------------------------------------

    def check_property(
        self, node: Node, prule: PropertyRule
    ) -> tuple[bool, str | None, str | None, frozenset[Key]]:
        """Port of ``validatePropertyConstraints`` (JS l.375-543).

        Returns ``(passed, severity, reason, assumptions)``.
        """
        if prule.name is None:
            return False, "warning", f"property rule {prule.id} does not have a name", _NO_DEPS
        values = self.crate.values_for(node, prule.name, prule.iri)
        if not values:
            # Difference 14: an empty list counts as missing.
            if prule.min_count > 0:
                return False, "info", "missing required property", _NO_DEPS
            return True, None, None, _NO_DEPS
        count = len(values)
        if count < prule.min_count:
            reason = f"has {count} value(s), requires at least {prule.min_count}"
            return False, "info", reason, _NO_DEPS
        if prule.max_count is not None and count > prule.max_count:
            # Difference 2: an error tied to the entity and property.
            reason = f"has {count} value(s), allows at most {prule.max_count}"
            return False, "error", reason, _NO_DEPS
        if not prule.ranges:
            return True, None, None, _NO_DEPS

        value_rules = [
            self.profile.property_values[r]
            for r in prule.ranges
            if r in self.profile.property_values
        ]
        other_ranges = [r for r in prule.ranges if r not in self.profile.property_values]
        for rule in value_rules:
            matched = sum(1 for value in values if matches_property_value(value, rule))
            if matched < rule.min_count:
                reason = (
                    f"value constraint {rule.id} requires at least {rule.min_count} "
                    f"match(es), found {matched}"
                )
                return False, "info", reason, _NO_DEPS
            if rule.max_count is not None and matched > rule.max_count:
                reason = (
                    f"value constraint {rule.id} allows at most {rule.max_count} "
                    f"match(es), found {matched}"
                )
                return False, "info", reason, _NO_DEPS
        if not other_ranges:
            return True, None, None, _NO_DEPS

        deps: set[Key] = set()
        for value in values:
            if any(matches_property_value(value, rule) for rule in value_rules):
                continue  # JS l.503-514
            reason, value_deps = self.check_value(value, other_ranges)
            if reason is not None:
                return False, "info", reason, _NO_DEPS
            deps |= value_deps
        return True, None, None, frozenset(deps)

    def check_value(self, value: Any, ranges: list[str]) -> tuple[str | None, frozenset[Key]]:
        """Port of ``validatePropertyValue`` (JS l.1866-1986).

        Returns ``(None, assumptions)`` when *value* fits a range, else
        ``(reason, ∅)``.
        """
        range_desc = ", ".join(ranges)
        ref_id = value.get("@id") if isinstance(value, dict) else None
        if not ref_id:
            for range_id in ranges:
                if any(check_literal(value, form) for form in self._range_forms(range_id)):
                    return None, _NO_DEPS
            return (
                f'value "{_js_string(value)}" did not match any of the expected ranges: '
                f"{range_desc}",
                _NO_DEPS,
            )

        target = self.crate.get(ref_id) if isinstance(ref_id, str) else None
        if target is None:
            # Difference 12: an external http(s) IRI satisfies a URL range.
            if (
                isinstance(ref_id, str)
                and _WEB_IRI.match(ref_id)
                and any(self._is_url_range(r) for r in ranges)
            ):
                return None, _NO_DEPS
            return (
                f'value "{_js_string(ref_id)}" references an entity that does not exist '
                "in the crate",
                _NO_DEPS,
            )

        chains: list[str] = []
        for range_id in ranges:
            if self.profile.is_enumeration_class(
                range_id
            ) and target.id in self.profile.enumeration_value_ids(range_id):
                return None, _NO_DEPS
            class_rule = self.profile.classes.get(range_id)
            if class_rule is not None:
                result = self.evaluate(target, class_rule)
                if result.ok:
                    return None, result.assumed
                record = self._final.get((target.id, class_rule.id))
                if record is not None:  # the types matched, so the failure has reasons
                    chains.append(
                        f"value `{target.id}` is not a valid {class_rule.name}: "
                        + "; ".join(record.reasons())
                    )
            elif range_id in self.profile.item_lists:
                if matches_item_list(target, self.profile.item_lists[range_id]):
                    return None, _NO_DEPS
            else:
                template = self.profile.document.get(range_id)
                if template is not None and matches_template(target, template):
                    return None, _NO_DEPS
        if chains:
            return " or ".join(chains), _NO_DEPS
        types = ", ".join(target.types) or "none"
        return (
            f'value "{target.id}" (types: {types}) did not match any of the expected '
            f"ranges: {range_desc}",
            _NO_DEPS,
        )

    def _range_forms(self, range_id: str) -> tuple[str, ...]:
        """The range as expanded by the profile context, then as written (JS l.1913-1925)."""
        expanded = self.profile.document.expander.expand(range_id)
        if expanded and expanded != range_id:
            return (expanded, range_id)
        return (range_id,)

    def _is_url_range(self, range_id: str) -> bool:
        for form in self._range_forms(range_id):
            iri = normalise_iri(form)
            if iri.startswith("https:"):
                iri = "http:" + iri[len("https:") :]
            if iri in _URL_RANGES:
                return True
        return False

    # -- rows ---------------------------------------------------------------

    def _regex_flag_warnings(self) -> list[dict]:
        """One warning per PropertyValue rule whose regexes use unsupported flags."""
        rows = []
        for rule in self.profile.property_values.values():
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
                        source=self.profile.source,
                    )
                )
        return rows

    def _cardinality_row(self, rule: ClassRule, valid: int, near_misses: list[str]) -> dict:
        types = ", ".join(sorted(_compact(t) for t in rule.type_iris))
        label = f"{rule.name} ({types})"
        passed = False
        if valid < rule.min_count:
            # Difference 1: explain each candidate that matched the types and failed.
            message = (
                f"Expected at least {rule.min_count} instances of {label}, found {valid} valid."
            )
            if near_misses:
                entries = [
                    f"{node_id}: {'; '.join(self._final[(node_id, rule.id)].reasons())}"
                    for node_id in near_misses[:_NEAR_MISS_LIMIT]
                ]
                message += " Near misses: " + " | ".join(entries)
                if len(near_misses) > _NEAR_MISS_LIMIT:
                    message += f" (+{len(near_misses) - _NEAR_MISS_LIMIT} more)"
        elif rule.max_count is not None and valid > rule.max_count:
            message = (
                f"Expected at most {rule.max_count} instances of {label}, found {valid} valid."
            )
        else:
            passed = True
            maximum = "unbounded" if rule.max_count is None else rule.max_count
            message = (
                f"Found {valid} valid instances of {label} "
                f"(expected between {rule.min_count} and {maximum})"
            )
        self.cardinalities.append(CardinalityOutcome(rule.id, passed, valid))
        return make_row(
            passed=passed,
            severity=None if passed else "error",
            rule=rule.id,
            entity_id=None,
            property=None,
            message=message,
            source=self.crate.source,
        )

    def _property_rows(self) -> list[dict]:
        """Rows for every evaluated pair, once each, in first-evaluation order."""
        rows = []
        index = 0
        while index < len(self._order):  # settling a pair may evaluate new ones
            node, class_rule = self._order[index]
            index += 1
            key = (node.id, class_rule.id)
            if key not in self._final:
                self.evaluate(node, class_rule)  # top level, so the result is final
            record = self._final[key]
            for check in record.checks:
                if not record.ok and check.passed and check.assumed:
                    # The pair failed for another reason while this check rested
                    # on an assumption; recheck it now that every pair has settled.
                    passed, severity, reason, _ = self.check_property(node, check.rule)
                    check = _Check(check.rule, passed, severity, reason, False)
                rows.append(self._property_row(class_rule, node, check))
        return rows

    def _property_row(self, class_rule: ClassRule, node: Node, check: _Check) -> dict:
        name = _property_name(check.rule)
        self.outcomes.append(
            PropertyOutcome(class_rule.id, node.id, check.rule.id, check.passed, check.severity)
        )
        message = (
            f"Property `{name}` is valid" if check.passed else f"Property `{name}`: {check.reason}"
        )
        return make_row(
            passed=check.passed,
            severity=check.severity,
            rule=class_rule.id,
            entity_id=node.id,
            property=name,
            message=message,
            source=self.crate.source,
        )
