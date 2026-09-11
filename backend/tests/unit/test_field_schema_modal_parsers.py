"""ABOUTME: Unit tests for the field-modal derivation config parsers in the schema blueprint
ABOUTME: Covers boundaries/date/mapping parsing and the age-bracket pre-fill from target values"""

import pytest

from opendlp.domain.respondent_derivation import AgeBracketRule, LargeMappingRule, SmallMappingRule
from opendlp.entrypoints.blueprints.respondent_field_schema import (
    age_prefill_from_target,
    parse_age_rule,
    parse_boundaries,
    parse_derivation_rule,
    parse_small_mapping_rule,
)


def _age_values(**overrides):
    values = {
        "as_of_day": "13",
        "as_of_month": "5",
        "as_of_year": "2026",
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
        assert rule.as_of_date.isoformat() == "2026-05-13"
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
        with pytest.raises(ValueError, match="boundaries"):
            parse_age_rule(_age_values(boundaries="10"))


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


class TestParseDerivationRule:
    def test_dispatches_on_the_method(self):
        values = _age_values()
        values["derivation_method"] = "age_bracket"
        assert isinstance(parse_derivation_rule(values), AgeBracketRule)

        assert isinstance(
            parse_derivation_rule({"derivation_method": "small_mapping", "map_source": ["A"], "map_target": ["X"]}),
            SmallMappingRule,
        )
        assert isinstance(parse_derivation_rule({"derivation_method": "large_mapping"}), LargeMappingRule)

    def test_unknown_method_is_rejected(self):
        with pytest.raises(ValueError, match="derived"):
            parse_derivation_rule({"derivation_method": "nonsense"})


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
