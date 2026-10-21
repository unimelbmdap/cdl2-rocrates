"""Validation engine: check a crate document against a parsed MASP profile.

Ports the class, property and value checks of ``masp-validator.js``
(``ClassRule.validate``, ``validateCardinality``,
``validatePropertyConstraints``, ``validateEntity`` and
``validatePropertyValue``), with the deliberate differences numbered as in
the user docs.

Entity checks that follow references run on an explicit stack: the property
and value checks are generators that yield an ``(entity, class rule)`` request
whenever a value must be checked against a class rule, so a long chain of
references never deepens the Python call stack.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, NamedTuple

from crategraph.validators.masp.context import normalise_iri
from crategraph.validators.masp.rows import (
    cardinality_row,
    js_string,
    property_row,
    regex_flag_warnings,
)
from crategraph.validators.masp.values import (
    check_literal,
    matches_item_list,
    matches_property_value,
    matches_template,
)

if TYPE_CHECKING:
    from crategraph.validators.masp.document import CrateDocument, Node
    from crategraph.validators.masp.profile import ClassRule, Profile, PropertyRule

Key = tuple[str, str]  # (entity id, class rule id)

_URL_RANGES = frozenset({"http://schema.org/URL", "URL"})
_WEB_IRI = re.compile(r"^https?://[^\s/?#]+", re.IGNORECASE)
_FREE = sys.maxsize  # "rests on no assumption" (see ``_Result.low``)
_MAX_DETAIL = 500  # longest nested reason kept in a reference chain


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
    # Discovery index of the earliest still-open pair this result assumed
    # valid, or ``_FREE`` when it rests on no assumption.
    low: int


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


# A property or value check: yields (entity, class rule) requests, receives
# each one's ``_Result``, and returns its own outcome.
_Steps = Generator[tuple["Node", "ClassRule"], _Result, Any]


def _property_name(rule: PropertyRule) -> str:
    return rule.name or rule.id


def _is_empty(value: Any) -> bool:
    """JSON ``null`` and ``""`` count as no value (difference 14); ``0`` and ``false`` do not."""
    return value is None or (isinstance(value, str) and value == "")


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
        # Pairs assumed valid for now: in progress, or provisionally valid and
        # waiting on their strongly connected component. Maps to discovery index.
        self._open: dict[Key, int] = {}
        self._pending: list[tuple[Key, _Record]] = []
        self._discovered = 0
        self._order: list[tuple[Node, ClassRule]] = []
        self._seen: set[Key] = set()

    def run(self) -> list[dict]:
        self._reset()
        try:
            rows = regex_flag_warnings(self.profile)
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
                        reasons = self._final[(node.id, class_rule.id)].reasons()
                        near_misses.append((node.id, reasons))
                row = cardinality_row(class_rule, valid, near_misses, self.crate.source)
                self.cardinalities.append(CardinalityOutcome(class_rule.id, row["passed"], valid))
                rows.append(row)
            rows.extend(self._property_rows())
        except RecursionError as exc:
            raise ValueError(f"{self.crate.source}: entities nest too deeply to validate") from exc
        return rows

    # -- entities -----------------------------------------------------------

    def _types_match(self, node: Node, class_rule: ClassRule) -> bool:
        # The JS rejects an entity with no @type even for a rule with no types.
        return bool(node.types) and class_rule.type_iris <= self.crate.type_iris(node)

    def _lookup(self, node: Node, class_rule: ClassRule) -> _Result | None:
        """The pair's result if known without checking it, else ``None``."""
        if not self._types_match(node, class_rule):
            return _Result(False, _FREE)
        key = (node.id, class_rule.id)
        record = self._final.get(key)
        if record is not None:
            return _Result(record.ok, _FREE)
        index = self._open.get(key)
        if index is not None:  # optimistic assumption (difference 4)
            return _Result(True, index)
        return None

    def evaluate(self, node: Node, class_rule: ClassRule) -> _Result:
        """Greatest-fixed-point check of *node* against *class_rule* (difference 4).

        A pair already open is assumed valid. ``False`` is always final, and
        the provisionally valid pairs that its check created are dropped and
        checked again later. ``True`` becomes final when the strongly connected
        component it belongs to completes (Tarjan's algorithm), so each pair
        of a cycle is checked once rather than once per path.
        """
        result = self._lookup(node, class_rule)
        return result if result is not None else self._drive(self._evaluate(node, class_rule))

    def _drive(self, steps: _Steps) -> Any:
        """Run *steps* to completion, checking requested pairs on an explicit stack."""
        stack = [steps]
        reply: _Result | None = None
        while True:
            try:
                node, class_rule = stack[-1].send(reply)  # type: ignore[arg-type]
            except StopIteration as done:
                stack.pop()
                if not stack:
                    return done.value
                reply = done.value
                continue
            reply = self._lookup(node, class_rule)
            if reply is None:
                stack.append(self._evaluate(node, class_rule))

    def _evaluate(self, node: Node, class_rule: ClassRule) -> _Steps:
        key = (node.id, class_rule.id)
        if key not in self._seen:
            self._seen.add(key)
            self._order.append((node, class_rule))
        index = self._discovered
        self._discovered += 1
        self._open[key] = index
        mark = len(self._pending)

        checks: list[_Check] = []
        low = _FREE
        for prule in class_rule.property_rules:
            passed, severity, reason, dep_low = yield from self.check_property(node, prule)
            checks.append(_Check(prule, passed, severity, reason, dep_low != _FREE))
            low = min(low, dep_low)
        record = _Record(all(check.passed for check in checks), tuple(checks))

        if record.ok and low < index:
            # Valid so far, but resting on a pair opened earlier: wait for it.
            self._pending.append((key, record))
            return _Result(True, low)
        settled = self._pending[mark:]
        del self._pending[mark:]
        for pending_key, pending_record in settled:
            del self._open[pending_key]
            if record.ok:  # the component is valid as a whole
                self._final[pending_key] = pending_record
        del self._open[key]
        self._final[key] = record
        return _Result(record.ok, _FREE)

    # -- properties ---------------------------------------------------------

    def check_property(self, node: Node, prule: PropertyRule) -> _Steps:
        """Port of ``validatePropertyConstraints`` (JS l.375-543).

        A generator (see ``_Steps``) returning ``(passed, severity, reason,
        low)``, where *low* is as in ``_Result``.
        """
        if prule.name is None:
            return False, "warning", f"property rule {prule.id} does not have a name", _FREE
        values = self.crate.values_for(node, prule.name, prule.iri)
        if not values or all(_is_empty(value) for value in values):
            # Difference 14: an empty list, null or "" counts as missing.
            # Difference 15: 0 and false count as present.
            if prule.min_count > 0:
                return False, "info", "missing required property", _FREE
            return True, None, None, _FREE
        count = len(values)
        if count < prule.min_count:
            reason = f"has {count} value(s), requires at least {prule.min_count}"
            return False, "info", reason, _FREE
        if prule.max_count is not None and count > prule.max_count:
            # Difference 2: an error tied to the entity and property.
            reason = f"has {count} value(s), allows at most {prule.max_count}"
            return False, "error", reason, _FREE
        if not prule.ranges:
            return True, None, None, _FREE

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
                return False, "info", reason, _FREE
            if rule.max_count is not None and matched > rule.max_count:
                reason = (
                    f"value constraint {rule.id} allows at most {rule.max_count} "
                    f"match(es), found {matched}"
                )
                return False, "info", reason, _FREE
        if not other_ranges:
            return True, None, None, _FREE

        low = _FREE
        for value in values:
            if any(matches_property_value(value, rule) for rule in value_rules):
                continue  # JS l.503-514
            reason, value_low = yield from self.check_value(value, other_ranges)
            if reason is not None:
                return False, "info", reason, _FREE
            low = min(low, value_low)
        return True, None, None, low

    def check_value(self, value: Any, ranges: list[str]) -> _Steps:
        """Port of ``validatePropertyValue`` (JS l.1866-1986).

        A generator (see ``_Steps``) returning ``(None, low)`` when *value*
        fits a range, else ``(reason, _FREE)``.
        """
        range_desc = ", ".join(ranges)
        ref_id = value.get("@id") if isinstance(value, dict) else None
        if not ref_id:
            for range_id in ranges:
                if any(check_literal(value, form) for form in self._range_forms(range_id)):
                    return None, _FREE
            return (
                f'value "{js_string(value)}" did not match any of the expected ranges: '
                f"{range_desc}",
                _FREE,
            )

        target = self.crate.get(ref_id) if isinstance(ref_id, str) else None
        if target is None:
            # Difference 12: an external http(s) IRI satisfies a URL range,
            # provided it passes the same check as a URL literal.
            if (
                isinstance(ref_id, str)
                and _WEB_IRI.match(ref_id)
                and any(self._is_url_range(r) for r in ranges)
                and check_literal(ref_id, "URL")
            ):
                return None, _FREE
            return (
                f'value "{js_string(ref_id)}" references an entity that does not exist '
                "in the crate",
                _FREE,
            )

        chains: list[str] = []
        for range_id in ranges:
            if self.profile.is_enumeration_class(
                range_id
            ) and target.id in self.profile.enumeration_value_ids(range_id):
                return None, _FREE
            class_rule = self.profile.classes.get(range_id)
            if class_rule is not None:
                result = yield (target, class_rule)
                if result.ok:
                    return None, result.low
                record = self._final.get((target.id, class_rule.id))
                if record is not None:  # the types matched, so the failure has reasons
                    detail = "; ".join(record.reasons())
                    if len(detail) > _MAX_DETAIL:
                        detail = detail[:_MAX_DETAIL] + "..."
                    chains.append(
                        f"value `{target.id}` is not a valid {class_rule.name}: {detail}"
                    )
            elif range_id in self.profile.item_lists:
                if matches_item_list(target, self.profile.item_lists[range_id]):
                    return None, _FREE
            else:
                template = self.profile.document.get(range_id)
                if template is not None and matches_template(target, template):
                    return None, _FREE
        if chains:
            return " or ".join(chains), _FREE
        types = ", ".join(target.types) or "none"
        return (
            f'value "{target.id}" (types: {types}) did not match any of the expected '
            f"ranges: {range_desc}",
            _FREE,
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
                    passed, severity, reason, _ = self._drive(
                        self.check_property(node, check.rule)
                    )
                    check = _Check(check.rule, passed, severity, reason, False)
                name = _property_name(check.rule)
                self.outcomes.append(
                    PropertyOutcome(
                        class_rule.id, node.id, check.rule.id, check.passed, check.severity
                    )
                )
                rows.append(
                    property_row(
                        class_rule.id,
                        node.id,
                        name,
                        check.passed,
                        check.severity,
                        check.reason,
                        self.crate.source,
                    )
                )
        return rows
