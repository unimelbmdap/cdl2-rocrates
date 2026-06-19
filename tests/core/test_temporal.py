"""Tests for the temporal coercion engine (crategraph/core/_temporal.py)."""

from __future__ import annotations

from datetime import date

import pytest

from crategraph.core._temporal import (
    entity_temporal,
    has_temporal_field,
    matches_time_range,
    parse_temporal,
)


class TestParseFormats:
    """Every shape that occurs in real crates parses to the right point/precision."""

    @pytest.mark.parametrize(
        ("text", "year", "precision", "start", "end"),
        [
            # ISO datetime with Z + fractional seconds.
            ("1994-07-15T00:00:00.000Z", 1994, "day", date(1994, 7, 15), date(1994, 7, 15)),
            # ISO datetime with a space separator.
            ("2017-03-12 00:00:00", 2017, "day", date(2017, 3, 12), date(2017, 3, 12)),
            # Plain ISO date.
            ("2017-03-12", 2017, "day", date(2017, 3, 12), date(2017, 3, 12)),
            # Human, full month name.
            ("12 March 2017", 2017, "day", date(2017, 3, 12), date(2017, 3, 12)),
            # Leading whitespace is tolerated.
            (" 1 July 1935", 1935, "day", date(1935, 7, 1), date(1935, 7, 1)),
            # Abbreviated month.
            ("1 Feb 1886", 1886, "day", date(1886, 2, 1), date(1886, 2, 1)),
            # Non-standard "Sept" abbreviation (dateutil handles it).
            ("1 Sept 1990", 1990, "day", date(1990, 9, 1), date(1990, 9, 1)),
            # Month + year only → month precision, no fabricated day.
            ("Dec 1914", 1914, "month", date(1914, 12, 1), date(1914, 12, 31)),
            ("March 2017", 2017, "month", date(2017, 3, 1), date(2017, 3, 31)),
            # ISO year-month partial is a single month, not a range.
            ("2017-03", 2017, "month", date(2017, 3, 1), date(2017, 3, 31)),
            # Bare year.
            ("1607", 1607, "year", date(1607, 1, 1), date(1607, 12, 31)),
        ],
    )
    def test_point_formats(self, text, year, precision, start, end):
        result = parse_temporal(text)
        assert result is not None
        assert result.year == year
        assert result.precision == precision
        assert result.start == start
        assert result.end == end
        assert result.is_range is False


class TestParseRanges:
    def test_two_digit_suffix_range(self):
        r = parse_temporal("1870-71")
        assert (r.year, r.is_range, r.precision) == (1870, True, "year")
        assert r.start == date(1870, 1, 1)
        assert r.end == date(1871, 12, 31)

    def test_full_year_range(self):
        r = parse_temporal("1945-1947")
        assert (r.year, r.is_range) == (1945, True)
        assert r.end == date(1947, 12, 31)

    def test_iso_year_month_is_not_a_backwards_range(self):
        # "1945-12" must read as Dec 1945, not the impossible range 1945->1912.
        r = parse_temporal("1945-12")
        assert r.is_range is False
        assert (r.year, r.precision) == (1945, "month")


class TestEdgeCases:
    """The uncertainty / decade / circa table pinned in the plan."""

    def test_uncertain_year(self):
        r = parse_temporal("1995?")
        assert (r.year, r.precision, r.uncertain) == (1995, "year", True)

    def test_uncertain_year_onwards_drops_suffix(self):
        r = parse_temporal("1995? Onwards")
        assert (r.year, r.uncertain) == (1995, True)

    def test_three_digit_qmark_is_a_decade(self):
        r = parse_temporal("192?")
        assert (r.year, r.precision, r.uncertain) == (1920, "decade", True)
        assert r.start == date(1920, 1, 1)
        assert r.end == date(1929, 12, 31)

    def test_decade_s_suffix(self):
        r = parse_temporal("1920s")
        assert (r.year, r.precision, r.uncertain) == (1920, "decade", False)

    @pytest.mark.parametrize("text", ["19?", "1?", "see notes", "President", "", "   "])
    def test_ambiguous_or_junk_is_none(self, text):
        assert parse_temporal(text) is None

    @pytest.mark.parametrize("text", ["c.1966", "circa 1966", "c 1966", "ca. 1966"])
    def test_circa_markers(self, text):
        r = parse_temporal(text)
        assert r is not None
        assert r.year == 1966
        assert r.circa is True

    def test_non_string_input_is_none(self):
        assert parse_temporal(1900) is None  # type: ignore[arg-type]


class TestEntityTemporal:
    def test_prefers_isostring_pair(self):
        et = entity_temporal(
            {
                "startDateISOString": "2017-03-12 00:00:00",
                "endDateISOString": "2018-08-03 00:00:00",
                "startDate": "garbage",
            }
        )
        assert et.start_date == date(2017, 3, 12)
        assert et.end_date == date(2018, 8, 3)
        assert et.year == 2017

    def test_falls_back_to_human_pair_when_iso_blank(self):
        et = entity_temporal(
            {
                "startDateISOString": "",
                "endDateISOString": "   ",
                "startDate": "12 March 2017",
                "endDate": "1 July 1935",
            }
        )
        assert et.start_date == date(2017, 3, 12)
        assert et.year == 2017

    def test_point_key_fallback(self):
        et = entity_temporal({"recordAppendDate": "1994-07-15T00:00:00.000Z"})
        assert et.year == 1994
        assert et.start_date == date(1994, 7, 15)

    def test_int_year_property(self):
        et = entity_temporal({"year": 1900})
        assert et.year == 1900
        assert et.start_date == date(1900, 1, 1)

    def test_modifier_circa_start_only(self):
        et = entity_temporal({"startDate": "1966", "startDateModifier": "c"})
        assert et.circa is True

    def test_modifier_circa_end_only(self):
        et = entity_temporal({"endDate": "1966", "endDateModifier": "c"})
        assert et.circa is True

    def test_misspelt_end_modifier_is_read(self):
        et = entity_temporal({"endDate": "1966", "endDateModifer": "c"})
        assert et.circa is True

    def test_modifier_uncertain(self):
        et = entity_temporal({"startDate": "1966", "endDateModifier": "?"})
        assert et.uncertain is True

    def test_modifier_s_makes_decade(self):
        et = entity_temporal({"startDate": "1920", "startDateModifier": "s", "endDate": "1929"})
        assert et.precision == "decade"
        assert et.start_date == date(1920, 1, 1)
        assert et.end_date == date(1929, 12, 31)

    def test_range_with_one_qualified_endpoint(self):
        # Only the end is circa; the entity-level flag is the OR of both ends.
        et = entity_temporal({"startDate": "1900", "endDate": "1910", "endDateModifier": "c"})
        assert et.circa is True
        assert (et.year, et.start_date, et.end_date) == (
            1900,
            date(1900, 1, 1),
            date(1910, 12, 31),
        )

    def test_no_temporal_fields(self):
        et = entity_temporal({"name": "Alice"})
        assert et == entity_temporal({})
        assert et.year is None and et.start_date is None


class TestHasTemporalField:
    def test_true_when_a_date_field_parses(self):
        assert has_temporal_field({"startDate": "1966"}) is True

    def test_false_for_modifier_only(self):
        # A modifier with no value field must not register as temporal.
        assert has_temporal_field({"startDateModifier": "c"}) is False

    def test_false_for_qualifier_free_text(self):
        assert has_temporal_field({"dateQualifier": "President"}) is False

    def test_false_for_unparseable_value(self):
        assert has_temporal_field({"startDate": "see notes"}) is False


class TestMatchesTimeRange:
    """Behaviour parity with the retired filtering._entity_matches_time_range."""

    def test_int_year_property(self):
        assert matches_time_range({"year": 1900}, low=1800, high=1950) is True
        assert matches_time_range({"year": 2000}, low=1800, high=1950) is False

    def test_float_year_property(self):
        assert matches_time_range({"year": 1900.0}, low=1800, high=1950) is True

    def test_overlapping_start_end_dates(self):
        props = {"startDate": "1910-01-01", "endDate": "1920-12-31"}
        assert matches_time_range(props, low=1915, high=1925) is True

    def test_non_overlapping_start_end_dates(self):
        props = {"startDate": "1930-01-01", "endDate": "1940-12-31"}
        assert matches_time_range(props, low=1915, high=1925) is False

    def test_list_value_recurses(self):
        assert matches_time_range({"date": ["n/a", "1899"]}, low=1850, high=1900) is True

    def test_arbitrary_date_key_heuristic(self):
        assert matches_time_range({"birthDate": "1888"}, low=1880, high=1890) is True
