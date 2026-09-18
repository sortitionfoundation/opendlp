"""ABOUTME: Unit tests for the target data sources set-up form's config parsers
ABOUTME: Covers boundaries/date/mapping parsing and the age-bracket pre-fill from a target's values"""

from datetime import UTC, datetime

import pytest

from opendlp.domain.respondent_derivation import AgeBracketRule, SmallMappingRule
from opendlp.entrypoints.derivation_form_parser import (
    age_prefill_from_target,
    parse_age_rule,
    parse_boundaries,
    parse_small_mapping_rule,
)

# The as-of year is validated against the current year, so the fixtures track it.
THIS_YEAR = datetime.now(UTC).date().year


def _age_values(**overrides):
    values = {
        "as_of_day": "13",
        "as_of_month": "5",
        "as_of_year": str(THIS_YEAR),
        "min_age": "16",
        "max_age": "100",
        "boundaries": "25, 40, 60",
    }
    values.update(overrides)
    return values


class TestParseBoundaries:
    def test_parses_comma_separated_ints_sorted_and_deduped(self):
        assert parse_boundaries("60; 25, 40, 25") == (25, 40, 60)

    def test_empty_string_is_no_boundaries(self):
        assert parse_boundaries("") == ()

    def test_non_numeric_input_raises_a_readable_error(self):
        with pytest.raises(ValueError, match="whole numbers"):
            parse_boundaries("25, forty")


class TestParseAgeRule:
    def test_builds_the_rule_from_form_values(self):
        rule = parse_age_rule(_age_values())
        assert isinstance(rule, AgeBracketRule)
        assert rule.as_of_date.isoformat() == f"{THIS_YEAR}-05-13"
        assert rule.boundaries == (25, 40, 60)
        assert rule.bracket_labels() == ["under-16", "16-24", "25-39", "40-59", "60-99", "100+"]

    def test_blank_min_and_max_fall_back_to_defaults(self):
        rule = parse_age_rule(_age_values(min_age="", max_age=""))
        assert rule.min_age == 16
        assert rule.max_age == 100

    def test_invalid_date_raises_a_readable_error(self):
        with pytest.raises(ValueError, match="as-of date"):
            parse_age_rule(_age_values(as_of_month="13"))

    def test_missing_date_raises_a_readable_error(self):
        with pytest.raises(ValueError, match="as-of date"):
            parse_age_rule(_age_values(as_of_year=""))

    def test_rule_validation_errors_propagate(self):
        with pytest.raises(ValueError, match="bracket boundary must be between"):
            parse_age_rule(_age_values(boundaries="10"))

    def test_a_two_digit_year_is_rejected(self):
        with pytest.raises(ValueError, match="as-of year"):
            parse_age_rule(_age_values(as_of_year="99"))

    def test_a_year_well_in_the_past_is_rejected(self):
        with pytest.raises(ValueError, match="as-of year"):
            parse_age_rule(_age_values(as_of_year=str(THIS_YEAR - 2)))

    def test_a_year_well_in_the_future_is_rejected(self):
        with pytest.raises(ValueError, match="as-of year"):
            parse_age_rule(_age_values(as_of_year=str(THIS_YEAR + 2)))

    def test_last_year_and_next_year_are_accepted(self):
        """An assembly's first date can sit either side of the new year, so allow one year of slack."""
        assert parse_age_rule(_age_values(as_of_year=str(THIS_YEAR - 1))).as_of_date.year == THIS_YEAR - 1
        assert parse_age_rule(_age_values(as_of_year=str(THIS_YEAR + 1))).as_of_date.year == THIS_YEAR + 1


class TestParseSmallMappingRule:
    def test_builds_the_mapping_from_paired_lists(self):
        rule = parse_small_mapping_rule({
            "map_source": ["White British", "White Irish"],
            "map_target": ["White", "White"],
        })
        assert isinstance(rule, SmallMappingRule)
        assert rule.mapping == {"White British": "White", "White Irish": "White"}

    def test_rows_left_on_the_fallback_entry_are_omitted(self):
        rule = parse_small_mapping_rule({"map_source": ["A", "B"], "map_target": ["X", ""]})
        assert rule.mapping == {"A": "X"}

    def test_an_entirely_unmapped_table_is_rejected(self):
        with pytest.raises(ValueError, match="at least one"):
            parse_small_mapping_rule({"map_source": ["A", "B"], "map_target": ["", ""]})


class TestAgePrefillFromTarget:
    def test_parses_a_complete_bracket_set(self):
        prefill = age_prefill_from_target(["under-16", "16-24", "25-39", "40-59", "60+"])
        assert prefill == {"min_age": "16", "max_age": "60", "boundaries": "25, 40"}

    def test_min_age_defaults_to_the_lowest_range_start_without_an_under_value(self):
        prefill = age_prefill_from_target(["16-24", "25-39", "60+"])
        assert prefill == {"min_age": "16", "max_age": "60", "boundaries": "25"}

    def test_unparsable_values_yield_no_prefill(self):
        assert age_prefill_from_target(["Young", "Old"]) is None

    def test_a_set_without_an_upper_bracket_yields_no_prefill(self):
        assert age_prefill_from_target(["16-24", "25-39"]) is None
