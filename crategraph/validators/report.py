"""Validation report: a ``Records`` list of check rows with a summary."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Any, Literal

from crategraph.core.records import _TITLE_STYLE, _WRAP_STYLE, Records

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

Severity = Literal["error", "warning", "info"]

_GROUPS = {"error": 0, "warning": 1, "info": 2}
_PASSED_GROUP = 3


def make_row(
    *,
    passed: bool,
    severity: Severity | None,
    rule: str | None,
    entity_id: str | None,
    property: str | None,
    message: str,
    source: str | None,
) -> dict[str, Any]:
    """Build one report row with columns in the fixed order.

    *severity* must be ``None`` for a passed check and set for a failed one.
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
        "property": property,
        "message": message,
        "source": source,
    }


def _group(row: dict[str, Any]) -> int:
    if row["passed"]:
        return _PASSED_GROUP
    return _GROUPS[row["severity"]]


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


class ValidationReport(Records):
    """Rows from a validation run, errors first, then warnings, info and passes."""

    def __init__(
        self,
        rows: Iterable[dict[str, Any]] = (),
        *,
        profile: str | None = None,
        sources: Sequence[str] = (),
    ) -> None:
        super().__init__(sorted(rows, key=_group))  # sorted() is stable
        self.profile = profile
        self.sources = tuple(sources)

    @property
    def is_valid(self) -> bool:
        """``True`` unless at least one error row is present."""
        return not any(not r["passed"] and r["severity"] == "error" for r in self)

    def counts(self) -> dict[str, int]:
        """Return the number of ``error``, ``warning``, ``info`` and ``passed`` rows."""
        tally = {"error": 0, "warning": 0, "info": 0, "passed": 0}
        for row in self:
            tally["passed" if row["passed"] else row["severity"]] += 1
        return tally

    def summary(self) -> str:
        """One-line description of what was validated and the outcome."""
        c = self.counts()
        what = ", ".join(self.sources) if self.sources else "crate"
        target = f" against {self.profile}" if self.profile else ""
        return (
            f"Validated {what} (raw source, not the filtered graph){target}: "
            f"{_plural(c['error'], 'error')}, {_plural(c['warning'], 'warning')}, "
            f"{c['info']} info, {c['passed']} passed."
        )

    def _repr_html_(self) -> str:
        head = (
            f'<div style="{_WRAP_STYLE}"><div style="{_TITLE_STYLE}">'
            f"{html.escape(self.summary())}</div></div>"
        )
        return head + super()._repr_html_()

    def __repr__(self) -> str:
        return self.summary()
