"""Parity with the JS MASP validator, on outputs captured by scripts/masp-parity.

Each case file holds a profile, a target crate and the JS results flattened
into comparable keys. The Python side runs the real ``MaspValidator`` on the
same files and is compared on structured data only, never on message text:

1. property outcomes ``(class_id, entity_id, property_rule_id, passed)``;
2. class cardinalities ``(class_id, passed, valid_count)``;
3. ``is_valid``, which also counts the Python-only validator rows (context,
   duplicate-id, profile and conformance), so a severity change shows up.

Deliberate differences are pinned in ``known_differences.py``.
"""

from __future__ import annotations

import json
from fnmatch import fnmatchcase
from pathlib import Path

import pytest

pytest.importorskip("rdflib")
pytest.importorskip("validators")

from crategraph.validators.masp import MaspValidator
from crategraph.validators.masp.document import CrateDocument
from crategraph.validators.masp.engine import ValidationRun

from .known_differences import KNOWN_DIFFERENCES, SPEC_DIFFERENCE_NUMBERS, KnownDifference

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tests/fixtures/masp"
COMMITTED_CASES = FIXTURES / "cases"
# Cases embedding PARADISEC and ldac_examples records stay local (gitignored).
LOCAL_CASES = REPO / "data/masp-parity/cases"


def _case_params() -> list:
    params = [pytest.param(p, id=p.stem) for p in sorted(COMMITTED_CASES.glob("*.json"))]
    if LOCAL_CASES.is_dir():
        local = sorted(LOCAL_CASES.glob("*.json"))
        params += [pytest.param(p, id=f"local-{p.stem}") for p in local]
    else:
        params.append(
            pytest.param(
                None,
                id="local",
                marks=pytest.mark.skip(reason="local parity corpus not present"),
            )
        )
    return params


def _target_file(case: dict, tmp_path: Path) -> Path:
    if "target_path" in case:
        return REPO / case["target_path"]
    path = tmp_path / "ro-crate-metadata.json"
    path.write_text(json.dumps(case["target"]), encoding="utf-8")
    return path


def _applicable(label: str) -> list[KnownDifference]:
    return [d for d in KNOWN_DIFFERENCES if any(fnmatchcase(label, glob) for glob in d.cases)]


def _describe(name: str, js_extra: set, py_extra: set) -> list[str]:
    lines = [f"{name}: JS only ({len(js_extra)})"]
    lines += [f"    {key}" for key in sorted(js_extra, key=repr)]
    lines.append(f"{name}: Python only ({len(py_extra)})")
    lines += [f"    {key}" for key in sorted(py_extra, key=repr)]
    return lines


def test_parity_corpus_present():
    assert len(list(COMMITTED_CASES.glob("*.json"))) >= 60


def test_known_differences_cite_spec_numbers():
    for difference in KNOWN_DIFFERENCES:
        assert difference.number in SPEC_DIFFERENCE_NUMBERS, difference
        assert difference.cases, difference
        assert difference.js_only or difference.py_only or difference.is_valid_flips, difference


@pytest.mark.parametrize("case_path", _case_params())
def test_matches_js(case_path: Path, tmp_path: Path):
    case = json.loads(case_path.read_text(encoding="utf-8"))
    assert "js_exception" not in case, "the JS threw; nothing to compare"

    validator = MaspValidator(FIXTURES / case["profile"])
    target = _target_file(case, tmp_path)
    run = ValidationRun(validator.profile, CrateDocument.load(target))
    run.run()
    report = validator.validate_files([target])

    js_outcomes = {
        (o["class_id"], o["entity_id"], o["property_rule_id"], o["passed"])
        for o in case["js_outcomes"]
    }
    py_outcomes = {(o.class_id, o.entity_id, o.property_rule_id, o.passed) for o in run.outcomes}
    js_cards = {(c["class_id"], c["passed"], c["valid_count"]) for c in case["js_cardinalities"]}
    py_cards = {(c.class_id, c.passed, c.valid_count) for c in run.cardinalities}
    js_valid, py_valid = case["js_is_valid"], report.is_valid

    js_extra = (js_outcomes - py_outcomes) | (js_cards - py_cards)
    py_extra = (py_outcomes - js_outcomes) | (py_cards - js_cards)
    differences = _applicable(case["label"])
    for d in differences:
        explains = (
            d.js_only & js_extra
            or d.py_only & py_extra
            or (d.is_valid_flips and js_valid != py_valid)
        )
        assert explains, f"difference {d.number} matches {case['label']!r} but explains nothing"

    js_extra -= frozenset().union(*(d.js_only for d in differences))
    py_extra -= frozenset().union(*(d.py_only for d in differences))
    flips = any(d.is_valid_flips for d in differences)

    if js_extra or py_extra or (js_valid != py_valid) != flips:
        outcome_keys = {k for k in js_extra | py_extra if len(k) == 4}
        lines = [f"{case['label']} ({case_path.name}), unexplained differences:"]
        lines += _describe("property outcomes", js_extra & outcome_keys, py_extra & outcome_keys)
        lines += _describe("cardinalities", js_extra - outcome_keys, py_extra - outcome_keys)
        lines.append(f"is_valid: JS {js_valid}, Python {py_valid} (flip expected: {flips})")
        if (js_valid != py_valid) != flips:
            lines += [
                f"    {r['rule']} {r['entity_id']}: {r['message']}"
                for r in report
                if not r["passed"] and r["severity"] == "error"
            ]
        pytest.fail("\n".join(lines), pytrace=False)
