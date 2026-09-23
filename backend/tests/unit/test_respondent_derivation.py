"""ABOUTME: Unit tests for the derivation rule value objects.
ABOUTME: Covers age-bracket arithmetic, mapping rules, config round-trips and lookup-key normalisation."""

from datetime import date

import pytest

from opendlp.domain.respondent_derivation import (
    MAX_SANE_AGE,
    AgeBracket,
    AgeBracketRule,
    LargeMappingRule,
    SmallMappingRule,
    match_age_brackets,
    normalise_lookup_key,
    output_options,
    rule_from_field,
)
from opendlp.domain.respondent_field_schema import ChoiceOption, DerivationType

AS_OF = date(2026, 5, 13)


BRACKETS = (
    AgeBracket(16, "16-21"),
    AgeBracket(22, "22-29"),
    AgeBracket(30, "30-54"),
    AgeBracket(55, "55+"),
)


def _age_rule(**kwargs) -> AgeBracketRule:
    defaults = {"as_of_date": AS_OF, "brackets": BRACKETS}
    defaults.update(kwargs)
    return AgeBracketRule(**defaults)


class TestAgeBracketRuleValidation:
    def test_brackets_are_required(self) -> None:
        with pytest.raises(ValueError, match="at least one age range"):
            _age_rule(brackets=())

    def test_zero_is_a_valid_start(self) -> None:
        rule = _age_rule(brackets=(AgeBracket(0, "0-15"), AgeBracket(16, "16+")))
        assert rule.labels() == ["0-15", "16+"]

    def test_negative_start_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="cannot start below zero"):
            _age_rule(brackets=(AgeBracket(-1, "young"), AgeBracket(16, "16+")))

    def test_two_brackets_cannot_share_a_start(self) -> None:
        with pytest.raises(ValueError, match="cannot start at the same age"):
            _age_rule(brackets=(AgeBracket(16, "a"), AgeBracket(16, "b")))

    def test_labels_must_be_unique(self) -> None:
        with pytest.raises(ValueError, match="only be one age range"):
            _age_rule(brackets=(AgeBracket(16, "a"), AgeBracket(30, "a")))

    def test_labels_cannot_be_blank(self) -> None:
        with pytest.raises(ValueError, match="needs a target value"):
            _age_rule(brackets=(AgeBracket(16, " "),))

    def test_a_label_cannot_be_the_fallback(self) -> None:
        with pytest.raises(ValueError, match="cannot use the value 'UNKNOWN'"):
            _age_rule(brackets=(AgeBracket(16, "16+"), AgeBracket(30, "UNKNOWN")))

    def test_fallback_cannot_be_blank(self) -> None:
        with pytest.raises(ValueError, match="fallback cannot be blank"):
            _age_rule(fallback="  ")

    def test_brackets_are_kept_youngest_first(self) -> None:
        rule = _age_rule(brackets=(AgeBracket(60, "60+"), AgeBracket(16, "16-59")))
        assert rule.labels() == ["16-59", "60+"]


class TestDeriveFromDate:
    def test_exact_boundary_ages(self) -> None:
        rule = _age_rule()
        # Born 22 years to the day before as_of_date: exactly 22 today.
        assert rule.derive_from_date(date(2004, 5, 13)) == "22-29"
        # A day later: still 21.
        assert rule.derive_from_date(date(2004, 5, 14)) == "16-21"

    def test_younger_than_the_lowest_bracket_takes_the_fallback(self) -> None:
        assert _age_rule().derive_from_date(date(2015, 1, 1)) == "UNKNOWN"

    def test_a_bracket_from_zero_holds_the_young(self) -> None:
        rule = _age_rule(brackets=(AgeBracket(0, "under 16"), *BRACKETS))
        assert rule.derive_from_date(date(2015, 1, 1)) == "under 16"

    def test_the_top_bracket_is_open_ended(self) -> None:
        assert _age_rule().derive_from_date(date(1926, 5, 13)) == "55+"

    def test_birthday_not_yet_reached_this_year(self) -> None:
        rule = _age_rule()
        # Born December 2004: 21 on 2026-05-13, not 22.
        assert rule.derive_from_date(date(2004, 12, 1)) == "16-21"

    def test_leap_year_birthday(self) -> None:
        rule = _age_rule()
        # Born 29 Feb 2008: turns 18 on 1 March in non-leap years; by May they are 18.
        assert rule.derive_from_date(date(2008, 2, 29)) == "16-21"

    def test_future_birth_date_takes_the_fallback(self) -> None:
        assert _age_rule().derive_from_date(date(2027, 1, 1)) == "UNKNOWN"

    def test_implausibly_old_takes_the_fallback(self) -> None:
        assert _age_rule().derive_from_date(date(1899, 1, 1)) == "UNKNOWN"

    def test_exactly_max_sane_age_is_still_a_person(self) -> None:
        """MAX_SANE_AGE is inclusive: 120 brackets, 121 is read as a typo."""
        rule = _age_rule()
        oldest = date(AS_OF.year - MAX_SANE_AGE, AS_OF.month, AS_OF.day)
        assert rule.derive_from_date(oldest) == "55+"
        assert rule.derive_from_date(oldest.replace(year=oldest.year - 1)) == "UNKNOWN"

    def test_born_on_the_as_of_date_is_age_zero(self) -> None:
        """Age 0 is a real age, not a data error - it lands in a bracket from 0."""
        rule = _age_rule(brackets=(AgeBracket(0, "0-15"), AgeBracket(16, "16+")))
        assert rule.derive_from_date(AS_OF) == "0-15"


class TestDeriveFromYear:
    def test_assumes_first_of_january(self) -> None:
        rule = _age_rule()
        # Born December 2010 is actually 15 on 2026-05-13, but year arithmetic
        # treats everyone born in 2010 as already 16.
        assert rule.derive_from_date(date(2010, 12, 1)) == "UNKNOWN"
        assert rule.derive_from_year(2010) == "16-21"

    def test_matches_date_arithmetic_for_january_births(self) -> None:
        rule = _age_rule()
        assert rule.derive_from_year(1990) == rule.derive_from_date(date(1990, 1, 1))

    def test_out_of_range_years_take_the_fallback(self) -> None:
        rule = _age_rule()
        assert rule.derive_from_year(1899) == "UNKNOWN"
        assert rule.derive_from_year(2027) == "UNKNOWN"

    def test_custom_fallback_is_used(self) -> None:
        rule = _age_rule(fallback="not-known")
        assert rule.derive_from_year(1850) == "not-known"


class TestAgeBracketConfigRoundTrip:
    def test_to_config_and_back(self) -> None:
        rule = _age_rule()
        config = rule.to_config()
        assert config == {
            "as_of_date": "2026-05-13",
            "brackets": [
                {"from_age": 16, "label": "16-21"},
                {"from_age": 22, "label": "22-29"},
                {"from_age": 30, "label": "30-54"},
                {"from_age": 55, "label": "55+"},
            ],
            "fallback": "UNKNOWN",
        }
        assert AgeBracketRule.from_config(config) == rule

    def test_from_config_rejects_missing_as_of_date(self) -> None:
        with pytest.raises(ValueError, match="as_of_date"):
            AgeBracketRule.from_config({"brackets": [{"from_age": 16, "label": "16+"}]})

    def test_from_config_rejects_missing_brackets(self) -> None:
        with pytest.raises(ValueError, match="brackets"):
            AgeBracketRule.from_config({"as_of_date": "2026-05-13"})

    def test_from_config_rejects_bad_date(self) -> None:
        with pytest.raises(ValueError):
            AgeBracketRule.from_config({"as_of_date": "not-a-date", "brackets": [{"from_age": 16, "label": "16+"}]})


class TestSmallMappingRule:
    def test_maps_known_values(self) -> None:
        rule = SmallMappingRule(mapping={"White British": "White", "White Irish": "White"})
        assert rule.derive("White British") == "White"
        assert rule.derive("  White Irish  ") == "White"

    def test_unknown_value_takes_the_fallback(self) -> None:
        rule = SmallMappingRule(mapping={"a": "b"})
        assert rule.derive("zzz") == "UNKNOWN"
        assert rule.derive("") == "UNKNOWN"

    def test_empty_mapping_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="mapping cannot be empty"):
            SmallMappingRule(mapping={})

    def test_fallback_cannot_be_blank(self) -> None:
        with pytest.raises(ValueError, match="fallback cannot be blank"):
            SmallMappingRule(mapping={"a": "b"}, fallback="")

    def test_config_round_trip(self) -> None:
        rule = SmallMappingRule(mapping={"a": "b"}, fallback="other")
        config = rule.to_config()
        assert config == {"mapping": {"a": "b"}, "fallback": "other"}
        assert SmallMappingRule.from_config(config) == rule


class TestLargeMappingRule:
    def test_derives_via_the_injected_lookup_after_normalising(self) -> None:
        rule = LargeMappingRule()
        table = {"SW1A1AA": "London"}
        assert rule.derive("sw1a 1aa", table.get) == "London"
        assert rule.derive("SW1A  1AA", table.get) == "London"

    def test_no_match_takes_the_fallback(self) -> None:
        rule = LargeMappingRule()
        assert rule.derive("ZZ99 9ZZ", lambda key: None) == "UNKNOWN"

    def test_blank_input_takes_the_fallback_without_calling_the_lookup(self) -> None:
        rule = LargeMappingRule()

        def exploding_lookup(key: str) -> str | None:
            raise AssertionError("lookup must not be called for blank input")

        assert rule.derive("   ", exploding_lookup) == "UNKNOWN"

    def test_config_round_trip(self) -> None:
        rule = LargeMappingRule(fallback="outside-area")
        config = rule.to_config()
        assert config == {"fallback": "outside-area"}
        assert LargeMappingRule.from_config(config) == rule


class TestNormaliseLookupKey:
    @pytest.mark.parametrize(
        "messy",
        [
            "SW1A 1AA",
            "sw1a1aa",
            "SW1A  1AA",
            " sw1a 1aa ",
            "SW1A\t1AA",
            "SW1A\u00a01AA",
            "Sw1a 1Aa\n",
        ],
    )
    def test_messy_postcode_variants_collapse_to_one_key(self, messy: str) -> None:
        assert normalise_lookup_key(messy) == "SW1A1AA"

    def test_blank_normalises_to_empty(self) -> None:
        assert normalise_lookup_key("   ") == ""
        assert normalise_lookup_key("") == ""


class TestRuleFromField:
    def test_builds_each_rule_type(self) -> None:
        age = rule_from_field(
            DerivationType.AGE_BRACKET, {"as_of_date": "2026-05-13", "brackets": [{"from_age": 16, "label": "16+"}]}
        )
        assert isinstance(age, AgeBracketRule)
        small = rule_from_field(DerivationType.SMALL_MAPPING, {"mapping": {"a": "b"}})
        assert isinstance(small, SmallMappingRule)
        large = rule_from_field(DerivationType.LARGE_MAPPING, {})
        assert isinstance(large, LargeMappingRule)

    def test_invalid_config_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            rule_from_field(DerivationType.AGE_BRACKET, {})
        with pytest.raises(ValueError):
            rule_from_field(DerivationType.SMALL_MAPPING, {})


class TestOutputOptions:
    def test_age_rule_options_are_its_labels_plus_fallback(self) -> None:
        options = output_options(_age_rule())
        assert [o.value for o in options] == ["16-21", "22-29", "30-54", "55+", "UNKNOWN"]
        assert all(isinstance(o, ChoiceOption) for o in options)

    def test_small_mapping_uses_distinct_outputs_in_first_seen_order(self) -> None:
        rule = SmallMappingRule(mapping={"White British": "White", "White Irish": "White", "Other": "Other"})
        options = output_options(rule)
        assert [o.value for o in options] == ["White", "Other", "UNKNOWN"]

    def test_declared_outputs_override_mapping_values(self) -> None:
        rule = SmallMappingRule(mapping={"a": "b"})
        options = output_options(rule, declared_outputs=["North", "South"])
        assert [o.value for o in options] == ["North", "South", "UNKNOWN"]

    def test_large_mapping_requires_declared_outputs(self) -> None:
        with pytest.raises(ValueError, match="declared_outputs"):
            output_options(LargeMappingRule())

    def test_large_mapping_with_declared_outputs(self) -> None:
        options = output_options(LargeMappingRule(), declared_outputs=["London", "North"])
        assert [o.value for o in options] == ["London", "North", "UNKNOWN"]

    def test_fallback_is_not_duplicated_when_already_declared(self) -> None:
        options = output_options(LargeMappingRule(), declared_outputs=["London", "UNKNOWN"])
        assert [o.value for o in options] == ["London", "UNKNOWN"]


GENERIC_PROBLEM = "Could not work out age ranges"


class TestMatchAgeBrackets:
    """Target values name their own ages; the numbers in them give each one's start."""

    @pytest.mark.parametrize(
        "labels",
        [
            ["16-29", "30-44", "45-59", "60+"],
            ["16 - 29", "30 - 44", "45 - 59", "60 or higher"],
            ["16\u201329", "30\u201344", "45\u201359", ">59"],
            ["16\u201429", "30\u201444", "45\u201459", "over 59"],
            ["16 to 29", "30 to 44", "45 to 59", "60 and over"],
            ["16 bis 29", "30 bis 44", "45 bis 59", "60+"],
            ["16-29 \u00e9v", "30-44 \u00e9v", "45-59 \u00e9v", "60+ \u00e9v"],
            ["Aged 16 to 29", "Aged 30 to 44", "Aged 45 to 59", "Aged 60 or over"],
        ],
    )
    def test_ranges_in_any_wording(self, labels) -> None:
        match = match_age_brackets(labels)
        assert match.problem == ""
        assert list(match.from_ages.values()) == [16, 30, 45, 60]
        assert set(match.from_ages) == set(labels)

    @pytest.mark.parametrize("top", ["60-99", "60-100", "60-120"])
    def test_the_highest_range_is_open_ended(self, top) -> None:
        match = match_age_brackets(["16-29", "30-59", top])
        assert match.problem == ""
        assert match.from_ages[top] == 60

    @pytest.mark.parametrize("bottom", ["under 16", "under-16", "<16", "15 and under", "Under 16s"])
    def test_a_one_number_value_below_the_ranges_starts_at_zero(self, bottom) -> None:
        match = match_age_brackets([bottom, "16-29", "30+"])
        assert match.problem == ""
        assert match.from_ages == {bottom: 0, "16-29": 16, "30+": 30}

    def test_a_range_can_start_at_zero(self) -> None:
        match = match_age_brackets(["0-15", "16-29", "30+"])
        assert match.problem == ""
        assert match.from_ages == {"0-15": 0, "16-29": 16, "30+": 30}

    def test_the_order_of_the_values_does_not_matter(self) -> None:
        match = match_age_brackets(["60+", "30-59", "16-29"])
        assert match.problem == ""
        assert match.from_ages == {"60+": 60, "30-59": 30, "16-29": 16}

    def test_a_single_range_is_enough(self) -> None:
        match = match_age_brackets(["16-99"])
        assert match.from_ages == {"16-99": 16}
        assert match.problem == ""

    def test_a_one_year_gap_is_named(self) -> None:
        match = match_age_brackets(["16-29", "31-44", "45+"])
        assert match.problem == "The target values leave out age 30"
        assert match.from_ages == {"16-29": 16, "31-44": 31, "45+": 45}

    def test_a_longer_gap_is_named(self) -> None:
        match = match_age_brackets(["16-29", "35-44", "45+"])
        assert match.problem == "The target values leave out ages 30 to 34"

    def test_an_overlap_is_named(self) -> None:
        match = match_age_brackets(["16-30", "30-44", "45+"])
        assert match.problem == "Age 30 is in more than one target value"

    @pytest.mark.parametrize(
        "labels",
        [
            ["Young", "Old"],
            ["under 30", "30+"],
            ["16-29", "30-44", "Prefer not to say"],
            ["16-29", "30-44", "1 2 3"],
            ["29-16", "30+"],
            ["16-29", "30-44", "70+"],
            [],
        ],
    )
    def test_values_that_cannot_be_placed_give_the_general_problem(self, labels) -> None:
        match = match_age_brackets(labels)
        assert match.problem.startswith(GENERIC_PROBLEM)
        assert "16-29, 30-44, 45-59, 60+" in match.problem

    def test_what_could_be_placed_is_still_returned(self) -> None:
        match = match_age_brackets(["16-29", "30-44", "Prefer not to say"])
        assert match.from_ages == {"16-29": 16, "30-44": 30}

    def test_a_full_match_builds_a_valid_rule(self) -> None:
        match = match_age_brackets(["under 16", "16-29", "30-59", "60+"])
        rule = AgeBracketRule(
            as_of_date=AS_OF,
            brackets=tuple(AgeBracket(from_age, label) for label, from_age in match.from_ages.items()),
        )
        assert rule.derive_from_year(AS_OF.year - 70) == "60+"
        assert rule.derive_from_year(AS_OF.year - 5) == "under 16"
