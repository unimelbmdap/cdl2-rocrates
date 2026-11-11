"""Validation report: a ``Records`` list of check rows with a summary."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any

from crategraph.core.records import _TITLE_STYLE, _WRAP_STYLE, Records

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

# A validator names its own severities; these are MASP's, most serious first.
DEFAULT_SEVERITIES = ("error", "warning", "info")
_PLURALS = {"error": "errors", "warning": "warnings"}


def make_row(
    *,
    passed: bool,
    severity: str | None,
    rule: str | None,
    entity_id: str | None,
    property: str | None,
    message: str,
    source: str | None,
    graph_entity: str | None = None,
) -> dict[str, Any]:
    """Build one report row with columns in the fixed order.

    *severity* must be ``None`` for a passed check and set for a failed one.
    *entity_id* is the entity's id as written in *source*; *graph_entity* is
    its id in the validated graph, when there is one.
    """
    if passed and severity is not None:
        raise ValueError("A passed row must have severity None")
    if not passed and severity is None:
        raise ValueError("A failed row must have a severity")
    return {
        "severity": severity,
        "passed": passed,
        "rule": rule,
        "entity_id": entity_id,
        "graph_entity": graph_entity,
        "property": property,
        "message": message,
        "source": source,
    }


def _phrase(count: int, name: str) -> str:
    return f"{count} {name if count == 1 else _PLURALS.get(name, name)}"


class ValidationReport(Records):
    """Rows from a validation run, most serious first and passes last.

    *severities* names the validator's severities, most serious first, and
    *failing* those that make :attr:`is_valid` false. *entities* lists the ids
    of the graph that was validated, when there was one; it is what
    :meth:`entity_status` reports on.
    """

    def __init__(
        self,
        rows: Iterable[dict[str, Any]] = (),
        *,
        profile: str | None = None,
        sources: Sequence[str] = (),
        severities: Sequence[str] = DEFAULT_SEVERITIES,
        failing: Iterable[str] = ("error",),
        entities: Iterable[str] | None = None,
    ) -> None:
        self.severities = tuple(severities)
        super().__init__(sorted(rows, key=self._group))  # sorted() is stable
        self.profile = profile
        self.sources = tuple(sources)
        self.failing = frozenset(failing)
        self.entities = None if entities is None else tuple(entities)

    def _rank(self, severity: str | None) -> int:
        """Position of *severity* in :attr:`severities`; unknown ones come after."""
        try:
            return self.severities.index(severity)
        except ValueError:
            return len(self.severities)

    def _group(self, row: dict[str, Any]) -> int:
        return len(self.severities) + 1 if row["passed"] else self._rank(row["severity"])

    @property
    def is_valid(self) -> bool:
        """``True`` unless a failed row has one of the :attr:`failing` severities."""
        return not any(not r["passed"] and r["severity"] in self.failing for r in self)

    def counts(self) -> dict[str, int]:
        """Return the number of rows for each severity, and of ``passed`` rows."""
        tally = dict.fromkeys(self.severities, 0)
        tally["passed"] = 0
        for row in self:
            key = "passed" if row["passed"] else row["severity"]
            tally[key] = tally.get(key, 0) + 1
        return tally

    def summary(self) -> str:
        """One-line description of what was validated and the outcome."""
        counts = self.counts()
        what = ", ".join(self.sources) if self.sources else "crate"
        target = f" against {self.profile}" if self.profile else ""
        outcome = ", ".join(_phrase(n, name) for name, n in counts.items() if name != "passed")
        return (
            f"Validated {what} (raw source, not the filtered graph){target}: "
            f"{outcome}, {counts['passed']} passed."
        )

    def entity_status(self) -> dict[str, dict[str, Any]]:
        """Map every entity of the validated graph to the outcome of its checks.

        Each entity gets ``validation_status`` and ``validation_messages``.
        The status is the most serious severity among its failed checks,
        ``"passed"`` if all its checks passed, or ``"unchecked"`` if no
        check looked at it. The messages are its failed checks, most serious
        first, each as ``"severity · message"``. Rows about the
        crate as a whole, such as a missing class, belong to no entity. To
        colour or filter the graph by the result::

            view = crate.annotate_entities(report.entity_status())
            view.visualise(colour_by="validation_status")

        Raises ``ValueError`` for a report not made from a graph, such as one
        from ``MaspValidator.validate_files``.
        """
        if self.entities is None:
            msg = (
                "This report was not made from a graph, so it has no entities to map "
                "to; validate with crate.validate(...) to use entity_status()."
            )
            raise ValueError(msg)
        worst: dict[str, str] = {}
        messages: dict[str, list[str]] = {}
        checked: set[str] = set()
        for row in self:  # most serious first
            entity = row.get("graph_entity")
            if entity is None:
                continue
            checked.add(entity)
            if row["passed"]:
                continue
            messages.setdefault(entity, []).append(f"{row['severity']} · {row['message']}")
            current = worst.get(entity)
            if current is None or self._rank(row["severity"]) < self._rank(current):
                worst[entity] = row["severity"]
        return {
            entity: {
                "validation_status": worst.get(
                    entity, "passed" if entity in checked else "unchecked"
                ),
                "validation_messages": messages.get(entity, []),
            }
            for entity in self.entities
        }

    def _repr_html_(self) -> str:
        head = (
            f'<div style="{_WRAP_STYLE}"><div style="{_TITLE_STYLE}">'
            f"{html.escape(self.summary())}</div></div>"
        )
        return head + super()._repr_html_()

    def __repr__(self) -> str:
        return self.summary()
