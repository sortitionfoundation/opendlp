"""ABOUTME: Unit tests for the target data sources set-up form's config parsers
ABOUTME: Covers age-range, as-of date and mapping parsing"""

from datetime import UTC, datetime

import pytest

from opendlp.domain.respondent_derivation import AgeBracket, AgeBracketRule, SmallMappingRule
from opendlp.domain.respondent_field_schema import ChoiceOption
from opendlp.entrypoints.derivation_form_parser import (
    parse_age_brackets,
    parse_age_rule,
    parse_answer_options,
    parse_as_of_date,
    parse_small_mapping_rule,
)

# The as-of year is validated against the current year, so the fixtures track it.
THIS_YEAR = datetime.now(UTC).date().year


def _age_values(**overrides):
    values = {
        "as_of_day": "13",
        "as_of_month": "5",
        "as_of_year": str(THIS_YEAR),
        "bracket_label": ["16-29", "30-59", "60+"],
        "bracket_from": ["16", "30", "60"],
    }
    values.update(overrides)
    return values


class TestParseAgeBrackets:
    def test_pairs_each_target_value_with_its_start(self):
        assert parse_age_brackets(_age_values()) == (
            AgeBracket(16, "16-29"),
            AgeBracket(30, "30-59"),
            AgeBracket(60, "60+"),
        )

    def test_surrounding_spaces_are_ignored(self):
        brackets = parse_age_brackets(_age_values(bracket_label=["all"], bracket_from=[" 18 "]))
        assert brackets == (AgeBracket(18, "all"),)

    def test_zero_is_accepted(self):
        brackets = parse_age_brackets(_age_values(bracket_label=["0-15", "16+"], bracket_from=["0", "16"]))
        assert brackets[0] == AgeBracket(0, "0-15")

    def test_every_target_value_needs_a_start(self):
        with pytest.raises(ValueError, match="Enter the age where '30-59' starts"):
            parse_age_brackets(_age_values(bracket_from=["16", "", "60"]))

    def test_a_missing_input_counts_as_blank(self):
        with pytest.raises(ValueError, match="Enter the age where '60\\+' starts"):
            parse_age_brackets(_age_values(bracket_from=["16", "30"]))

    def test_a_start_must_be_a_whole_number(self):
        with pytest.raises(ValueError, match="'30-59' starts must be a whole number"):
            parse_age_brackets(_age_values(bracket_from=["16", "thirty", "60"]))

    def test_a_negative_start_is_refused(self):
        with pytest.raises(ValueError, match="cannot start below zero"):
            parse_age_brackets(_age_values(bracket_from=["-1", "30", "60"]))

    def test_two_values_cannot_start_at_the_same_age(self):
        with pytest.raises(ValueError, match="cannot start at the same age"):
            parse_age_brackets(_age_values(bracket_from=["16", "30", "30"]))


class TestParseAsOfDate:
    def test_reads_day_month_and_year(self):
        assert parse_as_of_date(_age_values()).isoformat() == f"{THIS_YEAR}-05-13"

    def test_invalid_date_raises_a_readable_error(self):
        with pytest.raises(ValueError, match="valid date to calculate respondent age on"):
            parse_as_of_date(_age_values(as_of_month="13"))

    def test_missing_date_raises_a_readable_error(self):
        with pytest.raises(ValueError, match="valid date to calculate respondent age on"):
            parse_as_of_date(_age_values(as_of_year=""))

    def test_a_two_digit_year_is_rejected(self):
        with pytest.raises(ValueError, match="year to calculate respondent age on"):
            parse_as_of_date(_age_values(as_of_year="99"))

    def test_a_year_well_in_the_past_is_rejected(self):
        with pytest.raises(ValueError, match="year to calculate respondent age on"):
            parse_as_of_date(_age_values(as_of_year=str(THIS_YEAR - 2)))

    def test_a_year_well_in_the_future_is_rejected(self):
        with pytest.raises(ValueError, match="year to calculate respondent age on"):
            parse_as_of_date(_age_values(as_of_year=str(THIS_YEAR + 2)))

    def test_last_year_and_next_year_are_accepted(self):
        """An assembly's first date can sit either side of the new year, so allow one year of slack."""
        assert parse_as_of_date(_age_values(as_of_year=str(THIS_YEAR - 1))).year == THIS_YEAR - 1
        assert parse_as_of_date(_age_values(as_of_year=str(THIS_YEAR + 1))).year == THIS_YEAR + 1


class TestParseAgeRule:
    def test_builds_the_rule_from_form_values(self):
        rule = parse_age_rule(_age_values())
        assert isinstance(rule, AgeBracketRule)
        assert rule.as_of_date.isoformat() == f"{THIS_YEAR}-05-13"
        assert rule.labels() == ["16-29", "30-59", "60+"]

    def test_bracket_errors_come_before_date_errors(self):
        """The ranges sit above the date in the dialog, so their problem is reported first."""
        with pytest.raises(ValueError, match="Enter the age"):
            parse_age_rule(_age_values(bracket_from=["", "", ""], as_of_year=""))


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


class TestParseAnswerOptions:
    def test_typed_answers_become_options_in_order(self):
        options = parse_answer_options({"map_source": ["16-29", "30-44"], "map_target": ["Younger", "Older"]})
        assert options == [ChoiceOption(value="16-29"), ChoiceOption(value="30-44")]

    def test_blank_rows_are_dropped_and_values_stripped(self):
        """The table starts with spare blank rows, and a stray space is not part of an answer."""
        options = parse_answer_options({"map_source": [" 16-29 ", "", "  "], "map_target": []})
        assert options == [ChoiceOption(value="16-29")]

    def test_no_answers_at_all_is_refused(self):
        with pytest.raises(ValueError, match="Enter at least one answer"):
            parse_answer_options({"map_source": ["", ""], "map_target": []})

    def test_a_repeated_answer_is_refused_by_name(self):
        with pytest.raises(ValueError, match="'16-29' appears more than once"):
            parse_answer_options({"map_source": ["16-29", "30-44", "16-29"], "map_target": []})
