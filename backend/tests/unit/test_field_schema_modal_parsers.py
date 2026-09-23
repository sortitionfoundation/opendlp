"""ABOUTME: Unit tests for the option-value checks shared by the question and target set-up dialogs
ABOUTME: Covers spotting a repeated option value, compared exactly as everywhere else"""

from opendlp.domain.respondent_field_schema import ChoiceOption, duplicate_option_value


class TestDuplicateOptionValue:
    def test_distinct_values_report_no_duplicate(self):
        options = [ChoiceOption(value="Yes"), ChoiceOption(value="No")]
        assert duplicate_option_value(options) == ""

    def test_a_repeated_value_is_named(self):
        options = [ChoiceOption(value="Yes"), ChoiceOption(value="No"), ChoiceOption(value="Yes")]
        assert duplicate_option_value(options) == "Yes"

    def test_comparison_is_exact_so_case_differences_are_distinct_values(self):
        """Option values are matched exactly everywhere else, so "yes" and "Yes" are two values."""
        assert duplicate_option_value([ChoiceOption(value="Yes"), ChoiceOption(value="yes")]) == ""
