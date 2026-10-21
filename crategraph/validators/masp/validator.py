"""MaspValidator: validate raw RO-Crate files against a MASP profile."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from crategraph.core.interfaces import Validator
from crategraph.validators._extra import require_validate_extra
from crategraph.validators.masp.document import CrateDocument, is_reference
from crategraph.validators.masp.engine import ValidationRun
from crategraph.validators.masp.profile import Profile
from crategraph.validators.report import ValidationReport, make_row
from crategraph.validators.sources import crate_metadata_paths

if TYPE_CHECKING:
    from collections.abc import Sequence

    from crategraph.core.graph import Graph

_METADATA_NAME = "ro-crate-metadata.json"
_CONFORMS_TO_IRI = "http://purl.org/dc/terms/conformsTo"


class MaspValidator(Validator):
    """Validate crates against a MASP profile, reading the raw files on disk."""

    def __init__(self, profile: str | Path | None = None, *, fetch_contexts: bool = False) -> None:
        require_validate_extra()
        if profile is None:
            raise TypeError("kind='masp' needs a MASP profile: crate.validate('path/to/profile')")
        path = Path(profile)
        if path.is_dir():
            path = path / _METADATA_NAME
        if not path.is_file():
            msg = f"MASP profile not found: {profile}"
            raise FileNotFoundError(msg)
        self.fetch_contexts = fetch_contexts
        self.profile_path = path
        self.profile = Profile.load(path, fetch_contexts=fetch_contexts)

    def validate(self, graph: Graph) -> ValidationReport:
        """Validate the crate files *graph* was loaded from."""
        return self.validate_files(crate_metadata_paths(graph))

    def validate_files(self, paths: Sequence[str | Path]) -> ValidationReport:
        """Validate each ``ro-crate-metadata.json`` in *paths*."""
        profile_context = [r for r in self.profile.warnings if r["rule"] == "context"]
        profile_other = [r for r in self.profile.warnings if r["rule"] != "context"]
        rows: list[dict[str, Any]] = []
        for index, path in enumerate(paths):
            crate = CrateDocument.load(Path(path), fetch_contexts=self.fetch_contexts)
            engine_rows = ValidationRun(self.profile, crate).run()
            leading = 0
            while leading < len(engine_rows) and engine_rows[leading]["rule"] == "profile":
                leading += 1
            first = index == 0
            rows.extend(self._context_rows(crate))
            if first:
                rows.extend(dict(r) for r in profile_context)
            rows.extend(self._duplicate_rows(crate))
            if first:
                rows.extend(dict(r) for r in profile_other)
                rows.extend(dict(r) for r in engine_rows[:leading])
            rows.extend(engine_rows[leading:])
            rows.append(self._conformance_row(crate))
        return ValidationReport(
            rows,
            profile=str(self.profile_path),
            sources=[str(p) for p in paths],
        )

    def _context_rows(self, crate: CrateDocument) -> list[dict[str, Any]]:
        hint = "" if self.fetch_contexts else "; pass fetch_contexts=True to fetch it"
        return [
            make_row(
                passed=False,
                severity="warning",
                rule="context",
                entity_id=None,
                property=None,
                message=f"The terms of context {url} could not be resolved{hint}",
                source=crate.source,
            )
            for url in crate.unresolved_contexts
        ]

    @staticmethod
    def _duplicate_rows(crate: CrateDocument) -> list[dict[str, Any]]:
        return [
            make_row(
                passed=False,
                severity="warning",
                rule="duplicate-id",
                entity_id=entity_id,
                property=None,
                message=f"More than one entity has the @id {entity_id}; the first is used",
                source=crate.source,
            )
            for entity_id in crate.duplicate_ids
        ]

    def _conformance_row(self, crate: CrateDocument) -> dict[str, Any]:
        declared: list[str] = []
        for node in (crate.root(), crate.descriptor()):
            if node is None:
                continue
            for value in crate.values_for(node, "conformsTo", _CONFORMS_TO_IRI) or []:
                if is_reference(value):
                    declared.append(value["@id"])
                elif isinstance(value, str):
                    declared.append(value)
        accepted = self.profile.accepted_conformance_uris()
        passed = any(uri in accepted for uri in declared)
        if passed:
            message = "Crate declares conformance to this profile"
        else:
            message = (
                f"Crate declares conformance to {', '.join(declared) or 'nothing'}; "
                f"this profile accepts {', '.join(accepted) or 'nothing'}."
            )
        return make_row(
            passed=passed,
            severity=None if passed else "info",
            rule="conformance",
            entity_id=None,
            property=None,
            message=message,
            source=crate.source,
        )
