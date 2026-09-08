"""ABOUTME: Unit tests for the derivation rule value objects.
ABOUTME: Covers age-bracket arithmetic, mapping rules, config round-trips and lookup-key normalisation."""

from datetime import date

import pytest

from opendlp.domain.respondent_derivation import (
    AgeBracketRule,
    LargeMappingRule,
    SmallMappingRule,
    normalise_lookup_key,
    output_options,
    rule_from_field,
)
from opendlp.domain.respondent_field_schema import ChoiceOption, DerivationType

AS_OF = date(2026, 5, 13)


def _age_rule(**kwargs) -> AgeBracketRule:
    defaults = {"as_of_date": AS_OF, "min_age": 16, "max_age": 100, "boundaries": (22, 30, 55)}
    defaults.update(kwargs)
    return AgeBracketRule(**defaults)


class TestAgeBracketRuleValidation:
    def test_min_age_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="min_age must be greater than zero"):
            _age_rule(min_age=0)
        with pytest.raises(ValueError, match="min_age must be greater than zero"):
            _age_rule(min_age=-5)

    def test_max_age_must_exceed_min_age(self) -> None:
        with pytest.raises(ValueError, match="max_age must be greater than min_age"):
            _age_rule(min_age=50, max_age=50)

    def test_boundaries_must_be_sorted(self) -> None:
        with pytest.raises(ValueError, match="boundaries must be sorted"):
            _age_rule(boundaries=(30, 22))

    def test_boundaries_must_be_unique(self) -> None:
        with pytest.raises(ValueError, match="boundaries must be sorted"):
            _age_rule(boundaries=(22, 22, 30))

    def test_boundaries_must_be_strictly_between_min_and_max(self) -> None:
        with pytest.raises(ValueError, match="strictly between"):
            _age_rule(boundaries=(16, 30))
        with pytest.raises(ValueError, match="strictly between"):
            _age_rule(boundaries=(30, 100))

    def test_fallback_cannot_be_blank(self) -> None:
        with pytest.raises(ValueError, match="fallback cannot be blank"):
            _age_rule(fallback="  ")

    def test_no_boundaries_is_valid(self) -> None:
        rule = _age_rule(boundaries=())
        assert rule.bracket_labels() == ["under-16", "16-99", "100+"]


class TestBracketLabels:
    def test_worked_example_from_the_research(self) -> None:
        assert _age_rule().bracket_labels() == ["under-16", "16-21", "22-29", "30-54", "55-99", "100+"]

    def test_single_boundary(self) -> None:
        rule = _age_rule(min_age=18, max_age=75, boundaries=(40,))
        assert rule.bracket_labels() == ["under-18", "18-39", "40-74", "75+"]


class TestDeriveFromDate:
    def test_exact_boundary_ages(self) -> None:
        rule = _age_rule()
        # Born 22 years to the day before as_of_date: exactly 22 today.
        assert rule.derive_from_date(date(2004, 5, 13)) == "22-29"
        # A day later: still 21.
        assert rule.derive_from_date(date(2004, 5, 14)) == "16-21"

    def test_under_min_age_is_a_real_bracket(self) -> None:
        assert _age_rule().derive_from_date(date(2015, 1, 1)) == "under-16"

    def test_max_age_and_over_lands_in_the_top_bracket(self) -> None:
        assert _age_rule().derive_from_date(date(1926, 5, 13)) == "100+"
        assert _age_rule().derive_from_date(date(1920, 1, 1)) == "100+"

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


class TestDeriveFromYear:
    def test_assumes_first_of_january(self) -> None:
        rule = _age_rule()
        # Born December 2010 is actually 15 on 2026-05-13, but year arithmetic
        # treats everyone born in 2010 as already 16.
        assert rule.derive_from_date(date(2010, 12, 1)) == "under-16"
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


class TestEligibilitySentence:
    def test_names_the_minimum_age_and_the_date(self) -> None:
        sentence = _age_rule().eligibility_sentence()
        assert "16" in sentence
        assert "2026-05-13" in sentence


class TestAgeBracketConfigRoundTrip:
    def test_to_config_and_back(self) -> None:
        rule = _age_rule()
        config = rule.to_config()
        assert config == {
            "as_of_date": "2026-05-13",
            "min_age": 16,
            "max_age": 100,
            "boundaries": [22, 30, 55],
            "fallback": "UNKNOWN",
        }
        assert AgeBracketRule.from_config(config) == rule

    def test_from_config_rejects_missing_as_of_date(self) -> None:
        with pytest.raises(ValueError, match="as_of_date"):
            AgeBracketRule.from_config({"min_age": 16})

    def test_from_config_rejects_bad_date(self) -> None:
        with pytest.raises(ValueError):
            AgeBracketRule.from_config({"as_of_date": "not-a-date"})


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
        age = rule_from_field(DerivationType.AGE_BRACKET, {"as_of_date": "2026-05-13"})
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
    def test_age_rule_generates_bracket_options_plus_fallback(self) -> None:
        options = output_options(_age_rule())
        assert [o.value for o in options] == ["under-16", "16-21", "22-29", "30-54", "55-99", "100+", "UNKNOWN"]
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
