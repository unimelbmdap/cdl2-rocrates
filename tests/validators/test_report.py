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
        "graph_entity",
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


def test_custom_severities_order_count_summarise_and_decide_validity():
    report = ValidationReport(
        [
            _row(severity="suspect", message="s"),
            _row(passed=True, severity=None, message="p"),
            _row(severity="broken", message="b"),
        ],
        severities=("broken", "suspect"),
        failing=("broken",),
    )
    assert [r["message"] for r in report] == ["b", "s", "p"]
    assert report.counts() == {"broken": 1, "suspect": 1, "passed": 1}
    assert report.summary().endswith(": 1 broken, 1 suspect, 1 passed.")
    assert report.is_valid is False
    assert ValidationReport([_row(severity="suspect")], failing=("broken",)).is_valid is True


def test_entity_status_takes_the_worst_result_per_entity():
    report = ValidationReport(
        [
            _row(severity="info", graph_entity="#a"),
            _row(severity="error", graph_entity="#a"),
            _row(passed=True, severity=None, graph_entity="#a"),
            _row(passed=True, severity=None, graph_entity="#b"),
            _row(severity="warning", graph_entity="#c"),
            _row(severity="error", graph_entity=None),  # about the crate as a whole
        ],
        entities=["#a", "#b", "#c", "#d"],
    )
    assert report.entity_status() == {
        "#a": "error",
        "#b": "passed",
        "#c": "warning",
        "#d": "unchecked",
    }


def test_entity_status_passes_custom_severities_through():
    report = ValidationReport(
        [_row(severity="suspect", graph_entity="#a"), _row(severity="broken", graph_entity="#a")],
        severities=("broken", "suspect"),
        entities=["#a"],
    )
    assert report.entity_status() == {"#a": "broken"}


def test_entity_status_needs_a_graph():
    with pytest.raises(ValueError, match="not made from a graph"):
        ValidationReport([_row()]).entity_status()
