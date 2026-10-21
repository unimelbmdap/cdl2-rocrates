"""Tests for MaspValidator and the crate.validate wiring."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("rdflib")
pytest.importorskip("validators")

from crategraph import Crate
from crategraph.validators.masp import MaspValidator
from crategraph.validators.masp import context as context_module
from crategraph.validators.report import ValidationReport

from .conftest import make_crate, make_profile

REPO = Path(__file__).resolve().parents[3]
LDAC_PROFILE = REPO / "tests/fixtures/masp/upstream/ldac/ro-crate-metadata.json"
NT1 = REPO / "docs/tutorials/data/paradisec/NT1"
PROFILE_URI = "https://example.org/profile/v1"


def _write(directory: Path, data: dict) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "ro-crate-metadata.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _profile_data() -> dict:
    data = make_profile()
    data["@graph"][1]["@id"] = PROFILE_URI
    data["@graph"][0]["about"] = {"@id": PROFILE_URI}
    return data


def _crate_data(conforms: str | None = None) -> dict:
    data = make_crate()
    if conforms is not None:
        data["@graph"][1]["conformsTo"] = {"@id": conforms}
    return data


@pytest.fixture
def profile_dir(tmp_path: Path) -> Path:
    _write(tmp_path / "profile", _profile_data())
    return tmp_path / "profile"


def test_crate_validate_end_to_end_on_tutorial_nt1():
    report = Crate(str(NT1)).validate(LDAC_PROFILE)
    assert isinstance(report, ValidationReport)
    contexts = [r for r in report if r["rule"] == "context" and not r["passed"]]
    urls = sorted(next(u for u in r["message"].split() if u.startswith("http")) for r in contexts)
    assert urls == [
        "http://purl.archive.org/language-data-commons/context.json",
        "https://w3id.org/ldac/context",
    ]
    assert any(str(NT1) in s for s in report.sources)
    assert "raw source" in report.summary()


def test_missing_profile_raises_type_error():
    with pytest.raises(TypeError, match="needs a MASP profile"):
        MaspValidator(None)


def test_missing_profile_path_raises_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        MaspValidator(tmp_path / "nope")
    with pytest.raises(FileNotFoundError):
        MaspValidator(tmp_path)  # a directory without metadata


def test_profile_directory_or_file_both_accepted(profile_dir: Path):
    by_dir = MaspValidator(profile_dir)
    by_file = MaspValidator(profile_dir / "ro-crate-metadata.json")
    assert by_dir.profile_path == by_file.profile_path


def test_conformance_row_pass_and_info_failure_lists_uris(profile_dir: Path, tmp_path: Path):
    validator = MaspValidator(profile_dir)
    good = _write(tmp_path / "good", _crate_data(PROFILE_URI))
    bad = _write(tmp_path / "bad", _crate_data("https://other.example/p"))
    bare = _crate_data()
    del bare["@graph"][0]["conformsTo"]
    none = _write(tmp_path / "none", bare)

    ok = [r for r in validator.validate_files([good]) if r["rule"] == "conformance"]
    assert len(ok) == 1 and ok[0]["passed"] and ok[0]["entity_id"] is None

    for path, declared in (
        (bad, "https://other.example/p, https://w3id.org/ro/crate/1.2"),
        (none, "nothing"),
    ):
        row = next(r for r in validator.validate_files([path]) if r["rule"] == "conformance")
        assert not row["passed"] and row["severity"] == "info"
        assert row["message"] == (
            f"Crate declares conformance to {declared}; this profile accepts {PROFILE_URI}."
        )


def test_validator_reusable_across_crates(profile_dir: Path, tmp_path: Path):
    validator = MaspValidator(profile_dir)
    a = _write(tmp_path / "a", _crate_data(PROFILE_URI))
    b = _write(tmp_path / "b", _crate_data())
    first = list(validator.validate_files([a]))
    validator.validate_files([b])
    assert list(validator.validate_files([a])) == first


def test_multi_crate_graph_rows_carry_each_source(profile_dir: Path, tmp_path: Path):
    validator = MaspValidator(profile_dir)
    a = _write(tmp_path / "a", _crate_data(PROFILE_URI))
    b = _write(tmp_path / "b", _crate_data())
    report = validator.validate_files([a, b])
    assert report.sources == (str(a), str(b))
    sources = {r["source"] for r in report if r["rule"] == "conformance"}
    assert sources == {str(a), str(b)}


def test_profile_level_rows_emitted_once(tmp_path: Path):
    data = _profile_data()
    data["@context"] = [*data["@context"], "https://example.org/unbundled.json"]
    _write(tmp_path / "profile", data)
    validator = MaspValidator(tmp_path / "profile")
    a = _write(tmp_path / "a", _crate_data())
    b = _write(tmp_path / "b", _crate_data())
    report = validator.validate_files([a, b])
    rows = [r for r in report if r["rule"] == "context"]
    assert len(rows) == 1 and rows[0]["source"] == validator.profile.source


def test_crate_context_row_has_fetch_hint(profile_dir: Path, tmp_path: Path):
    data = _crate_data()
    data["@context"] = [*data["@context"], "https://example.org/unbundled.json"]
    path = _write(tmp_path / "c", data)
    report = MaspValidator(profile_dir).validate_files([path])
    row = next(r for r in report if r["rule"] == "context")
    assert "https://example.org/unbundled.json" in row["message"]
    assert "could not be resolved" in row["message"]
    assert "pass fetch_contexts=True to fetch it" in row["message"]
    assert row["source"] == str(path)


def test_fetch_contexts_forwarded_from_graph_validate(profile_dir: Path, monkeypatch):
    seen: list[bool] = []
    real = context_module.resolve_context

    def spy(context, *, fetch=False):
        seen.append(fetch)
        return real(context, fetch=False)  # stay offline

    import crategraph.validators.masp.document as document_module

    monkeypatch.setattr(document_module, "resolve_context", spy)
    Crate(str(NT1)).validate(profile_dir, fetch_contexts=True)
    assert seen and all(seen)


def test_no_rdflib_gives_install_message(monkeypatch, profile_dir: Path):
    monkeypatch.setitem(sys.modules, "rdflib", None)
    with pytest.raises(ImportError, match=r"crategraph\[validate\]"):
        MaspValidator(profile_dir)


def _ordered_case(tmp_path: Path):
    from .test_engine import cls, prop, pv

    profile = make_profile(
        cls("#Person", {"@id": "Person"}),
        prop("#kind", "kind", "#Person", ["#pv"]),
        pv("#pv", "/a/x"),
        context=[*make_profile()["@context"], "https://example.org/profile-ctx.json"],
    )
    profile["@graph"][1]["@id"] = PROFILE_URI
    profile["@graph"][0]["about"] = {"@id": PROFILE_URI}
    _write(tmp_path / "profile", profile)
    crate = _crate_data(PROFILE_URI)
    crate["@context"] = [*crate["@context"], "https://example.org/crate-ctx.json"]
    crate["@graph"].extend(
        [
            {"@id": "#p", "@type": "Person", "kind": "a"},
            {"@id": "#p", "@type": "Person", "kind": "a"},
        ]
    )
    path = _write(tmp_path / "crate", crate)
    return MaspValidator(tmp_path / "profile"), path


def test_warning_rows_keep_emission_order(tmp_path: Path):
    validator, path = _ordered_case(tmp_path)
    report = validator.validate_files([path])
    warnings = [r for r in report if not r["passed"] and r["severity"] == "warning"]
    assert [r["rule"] for r in warnings] == ["context", "context", "duplicate-id", "profile"]
    assert "crate-ctx" in warnings[0]["message"] and warnings[0]["source"] == str(path)
    assert "profile-ctx" in warnings[1]["message"]
    assert warnings[1]["source"] == validator.profile.source


def test_profile_rows_are_copied_per_report(tmp_path: Path):
    validator, path = _ordered_case(tmp_path)
    first = validator.validate_files([path])
    for row in first:
        if row["rule"] in ("context", "profile"):
            row["message"] = "mutated"
    second = validator.validate_files([path])
    assert all(r["message"] != "mutated" for r in second)
    assert not any(r is s for r in first for s in validator.profile.warnings)


def test_duplicate_id_warning_says_values_are_merged(tmp_path: Path):
    validator, path = _ordered_case(tmp_path)
    report = validator.validate_files([path])
    (row,) = [r for r in report if r["rule"] == "duplicate-id"]
    assert "merged and validated together" in row["message"]
    assert "first is used" not in row["message"]
