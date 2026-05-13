"""Unit tests for respondent field schema heuristics (pattern-based group classification)."""

import pytest

from opendlp.domain.respondent_field_schema import RespondentFieldGroup
from opendlp.service_layer.respondent_field_schema_heuristics import (
    classify_field_key,
)


class TestClassifyFieldKey:
    @pytest.mark.parametrize(
        ("field_key", "expected"),
        [
            # Eligibility
            ("eligible", RespondentFieldGroup.ELIGIBILITY),
            ("can_attend", RespondentFieldGroup.ELIGIBILITY),
            ("canAttend", RespondentFieldGroup.ELIGIBILITY),
            ("available", RespondentFieldGroup.ELIGIBILITY),
            # Name and contact
            ("first_name", RespondentFieldGroup.NAME_AND_CONTACT),
            ("FirstName", RespondentFieldGroup.NAME_AND_CONTACT),
            ("given-name", RespondentFieldGroup.NAME_AND_CONTACT),
            ("surname", RespondentFieldGroup.NAME_AND_CONTACT),
            ("family_name", RespondentFieldGroup.NAME_AND_CONTACT),
            ("full name", RespondentFieldGroup.NAME_AND_CONTACT),
            ("email", RespondentFieldGroup.NAME_AND_CONTACT),
            ("Email Address", RespondentFieldGroup.NAME_AND_CONTACT),
            ("phone_number", RespondentFieldGroup.NAME_AND_CONTACT),
            ("mobile", RespondentFieldGroup.NAME_AND_CONTACT),
            ("country_code", RespondentFieldGroup.NAME_AND_CONTACT),
            ("external_id", RespondentFieldGroup.NAME_AND_CONTACT),
            # Address
            ("address", RespondentFieldGroup.ADDRESS),
            ("address_line_1", RespondentFieldGroup.ADDRESS),
            ("address_line_2", RespondentFieldGroup.ADDRESS),
            ("addr_line_3", RespondentFieldGroup.ADDRESS),
            ("street", RespondentFieldGroup.ADDRESS),
            ("City", RespondentFieldGroup.ADDRESS),
            ("town", RespondentFieldGroup.ADDRESS),
            ("postcode", RespondentFieldGroup.ADDRESS),
            ("postal_code", RespondentFieldGroup.ADDRESS),
            ("zip", RespondentFieldGroup.ADDRESS),
            ("country", RespondentFieldGroup.ADDRESS),
            # Consent
            ("consent", RespondentFieldGroup.CONSENT),
            ("stay_on_db", RespondentFieldGroup.CONSENT),
            ("stay_on_list", RespondentFieldGroup.CONSENT),
            ("marketing_consent", RespondentFieldGroup.CONSENT),
            # About you
            ("gender", RespondentFieldGroup.ABOUT_YOU),
            ("age", RespondentFieldGroup.ABOUT_YOU),
            ("age_bracket", RespondentFieldGroup.ABOUT_YOU),
            ("dob_day", RespondentFieldGroup.ABOUT_YOU),
            ("dob_month", RespondentFieldGroup.ABOUT_YOU),
            ("dob_year", RespondentFieldGroup.ABOUT_YOU),
            ("date_of_birth", RespondentFieldGroup.ABOUT_YOU),
            ("year_of_birth", RespondentFieldGroup.ABOUT_YOU),
            ("ethnicity", RespondentFieldGroup.ABOUT_YOU),
            ("education_level", RespondentFieldGroup.ABOUT_YOU),
            ("disability", RespondentFieldGroup.ABOUT_YOU),
            ("opinion_about_climate", RespondentFieldGroup.ABOUT_YOU),
            ("attitude_to_nuclear", RespondentFieldGroup.ABOUT_YOU),
            # Other — unrecognised columns fall through
            ("q3_response", RespondentFieldGroup.OTHER),
            ("custom_field_1", RespondentFieldGroup.OTHER),
            ("something_weird", RespondentFieldGroup.OTHER),
        ],
    )
    def test_classify(self, field_key: str, expected: RespondentFieldGroup) -> None:
        assert classify_field_key(field_key) == expected

    def test_target_category_name_overrides_pattern_rules(self) -> None:
        # "occupation" would normally land in ABOUT_YOU via the pattern rule —
        # confirm the target-category route also hits ABOUT_YOU (same group,
        # but the code path exercised is the override, not the pattern).
        assert classify_field_key("occupation", target_category_names=["Occupation"]) == RespondentFieldGroup.ABOUT_YOU

    def test_target_category_override_moves_unmatched_key_into_about_you(self) -> None:
        # A weird column name that would otherwise fall into OTHER should be
        # pulled into ABOUT_YOU when a matching TargetCategory exists.
        assert classify_field_key("zz_custom") == RespondentFieldGroup.OTHER
        assert classify_field_key("zz_custom", target_category_names=["ZZ Custom"]) == RespondentFieldGroup.ABOUT_YOU

    def test_target_category_match_is_case_insensitive(self) -> None:
        assert classify_field_key("REGION", target_category_names=["region"]) == RespondentFieldGroup.ABOUT_YOU

    def test_empty_field_key_returns_other(self) -> None:
        assert classify_field_key("") == RespondentFieldGroup.OTHER
        assert classify_field_key("---") == RespondentFieldGroup.OTHER

    def test_empty_target_category_names_are_ignored(self) -> None:
        # A target category with a name that normalises to empty must not
        # swallow every empty-normalised key into ABOUT_YOU.
        assert (
            classify_field_key("first_name", target_category_names=["", "---"]) == RespondentFieldGroup.NAME_AND_CONTACT
        )
