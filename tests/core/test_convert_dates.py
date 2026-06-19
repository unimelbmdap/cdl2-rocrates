"""Tests for Graph.convert_dates — materialising parsed date columns."""

from __future__ import annotations

from crategraph.core._temporal import TemporalValue
from crategraph.core.graph import Graph
from crategraph.core.models import Entity

_DATE_COLUMNS = (
    "start_date",
    "end_date",
    "year",
    "date_precision",
    "date_circa",
    "date_uncertain",
)


def _graph(*entities: Entity) -> Graph:
    g = Graph()
    for entity in entities:
        g._add_node(entity)
    return g


class TestMaterialisation:
    def test_columns_are_iso_strings_and_native_scalars(self):
        g = _graph(Entity(id="#a", properties={"startDateISOString": "2017-03-12 00:00:00"}))
        out = g.convert_dates(report=False).get("#a").properties
        assert out["start_date"] == "2017-03-12"  # ISO string, not a date object
        assert out["end_date"] == "2017-03-12"
        assert out["year"] == 2017
        assert out["date_precision"] == "day"
        assert out["date_circa"] is False
        assert out["date_uncertain"] is False

    def test_year_only_brackets_and_decade(self):
        g = _graph(Entity(id="#a", properties={"startDate": "1920s"}))
        out = g.convert_dates(report=False).get("#a").properties
        assert out["start_date"] == "1920-01-01"
        assert out["end_date"] == "1929-12-31"
        assert out["date_precision"] == "decade"

    def test_circa_and_uncertain_surfaced(self):
        g = _graph(
            Entity(
                id="#a",
                properties={"startDate": "1966", "startDateModifier": "c", "endDate": "1970?"},
            )
        )
        out = g.convert_dates(report=False).get("#a").properties
        assert out["date_circa"] is True
        assert out["date_uncertain"] is True

    def test_entity_without_date_field_is_untouched(self):
        g = _graph(Entity(id="#a", properties={"name": "Alice"}))
        out = g.convert_dates(report=False).get("#a").properties
        assert not any(col in out for col in _DATE_COLUMNS)

    def test_modifier_only_entity_gets_no_columns(self):
        g = _graph(Entity(id="#a", properties={"startDateModifier": "c"}))
        out = g.convert_dates(report=False).get("#a").properties
        assert not any(col in out for col in _DATE_COLUMNS)

    def test_unparseable_value_gets_no_columns(self):
        g = _graph(Entity(id="#a", properties={"startDate": "see notes"}))
        out = g.convert_dates(report=False).get("#a").properties
        assert not any(col in out for col in _DATE_COLUMNS)


class TestGraphContract:
    def test_returns_new_graph_and_leaves_original_unchanged(self):
        original = Entity(id="#a", properties={"startDate": "1966"})
        g = _graph(original)
        g2 = g.convert_dates(report=False)
        assert g2 is not g
        assert "year" not in g.get("#a").properties  # original untouched
        assert g2.get("#a").properties["year"] == 1966

    def test_registers_derived_fields(self):
        g = _graph(Entity(id="#a", properties={"startDate": "1966"}))
        g2 = g.convert_dates(report=False)
        for col in _DATE_COLUMNS:
            assert g2.derived_fields.get(col) == "convert_dates"

    def test_result_is_its_own_expansion_root(self):
        g = _graph(Entity(id="#a", properties={"startDate": "1966"}))
        g2 = g.convert_dates(report=False)
        assert g2._root is g2

    def test_columns_appear_in_entity_records(self):
        g = _graph(Entity(id="#a", properties={"startDate": "1966"}))
        records = g.convert_dates(report=False).entity_records()
        assert records[0]["year"] == 1966


class TestParserOverride:
    def test_custom_parser_is_used(self):
        def always_1800(_text: str) -> TemporalValue | None:
            from datetime import date

            return TemporalValue(
                start=date(1800, 1, 1),
                end=date(1800, 12, 31),
                year=1800,
                precision="year",
            )

        g = _graph(Entity(id="#a", properties={"startDate": "anything at all"}))
        out = g.convert_dates(parser=always_1800, report=False).get("#a").properties
        assert out["year"] == 1800


class TestCoverageReport:
    def test_reports_parsed_count_and_unparseable_sample(self, capsys):
        g = _graph(
            Entity(id="#a", properties={"startDate": "1966"}),
            Entity(id="#b", properties={"startDate": "see notes"}),
            Entity(id="#c", properties={"name": "no dates here"}),  # out of scope
        )
        g.convert_dates()
        out = capsys.readouterr().out
        assert "parsed 1/2 entities with date fields" in out
        assert "1 unparseable" in out
        assert "#b" in out and "see notes" in out

    def test_report_false_is_silent(self, capsys):
        g = _graph(Entity(id="#a", properties={"startDate": "1966"}))
        g.convert_dates(report=False)
        assert capsys.readouterr().out == ""

    def test_no_date_fields_message(self, capsys):
        g = _graph(Entity(id="#a", properties={"name": "Alice"}))
        g.convert_dates()
        assert "no entities have date fields" in capsys.readouterr().out
