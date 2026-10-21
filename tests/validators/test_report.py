import pytest

from crategraph.core.records import Records
from crategraph.validators.report import ValidationReport, make_row


def _row(**kw):
    base = dict(
        passed=False,
        severity="info",
        rule="#r",
        entity_id="#e",
        property="p",
        message="m",
        source="/c/ro-crate-metadata.json",
    )
    base.update(kw)
    return make_row(**base)


def test_rows_sorted_errors_warnings_info_then_passes_stably():
    rows = [
        _row(passed=True, severity=None, message="p1"),
        _row(severity="info", message="i1"),
        _row(severity="error", message="e1"),
        _row(severity="warning", message="w1"),
        _row(severity="error", message="e2"),
    ]
    report = ValidationReport(rows)
    assert [r["message"] for r in report] == ["e1", "e2", "w1", "i1", "p1"]


def test_columns_in_fixed_order():
    assert list(_row()) == [
        "severity",
        "passed",
        "rule",
        "entity_id",
        "property",
        "message",
        "source",
    ]


def test_pass_rows_must_have_no_severity():
    with pytest.raises(ValueError):
        make_row(
            passed=True,
            severity="info",
            rule=None,
            entity_id=None,
            property=None,
            message="x",
            source=None,
        )


def test_failed_rows_must_have_severity():
    with pytest.raises(ValueError):
        make_row(
            passed=False,
            severity=None,
            rule=None,
            entity_id=None,
            property=None,
            message="x",
            source=None,
        )


def test_is_valid_only_false_with_error_rows():
    assert ValidationReport([_row(severity="warning")]).is_valid is True
    assert ValidationReport([_row(severity="error")]).is_valid is False
    assert ValidationReport().is_valid is True


def test_counts():
    report = ValidationReport(
        [_row(severity="error"), _row(severity="info"), _row(passed=True, severity=None)]
    )
    assert report.counts() == {"error": 1, "warning": 0, "info": 1, "passed": 1}


def test_summary_names_raw_source_and_profile():
    report = ValidationReport(
        [_row(severity="error")],
        profile="ldac/ro-crate-metadata.json",
        sources=["/x/NT1/ro-crate-metadata.json"],
    )
    assert report.summary() == (
        "Validated /x/NT1/ro-crate-metadata.json (raw source, not the filtered graph) "
        "against ldac/ro-crate-metadata.json: 1 error, 0 warnings, 0 info, 0 passed."
    )


def test_html_has_summary_above_table():
    html = ValidationReport([_row()], profile="p.json", sources=["/s.json"])._repr_html_()
    assert html.index("raw source, not the filtered graph") < html.index("<table")


def test_repr_is_summary():
    report = ValidationReport([_row()], sources=["/a.json", "/b.json"])
    assert repr(report) == report.summary()
    assert "/a.json, /b.json" in repr(report)


def test_is_a_records_list():
    pd = pytest.importorskip("pandas")
    report = ValidationReport([_row()])
    assert isinstance(report, Records) and isinstance(report, list)
    assert pd.DataFrame(report).columns.tolist()[0] == "severity"
