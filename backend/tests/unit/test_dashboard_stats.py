"""ABOUTME: Unit tests for the pure parts of the dashboard report derivation.
ABOUTME: Category matching, row arithmetic and the percentage fallback, with no database."""

import uuid

import pytest

from opendlp.domain.targets import TargetCategory, TargetValue, percentages_from_minmax
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.dashboard_stats import _build_category, _matching_attribute, _value_row


class _StubRespondentRepository:
    def __init__(self, by_status=None, available=None):
        self._by_status = by_status or {}
        self._available = available or {}
        self.queried_attributes: list[str] = []

    def get_attribute_value_counts_by_status(self, assembly_id, attribute_name):
        self.queried_attributes.append(attribute_name)
        return self._by_status

    def get_attribute_value_available_counts(self, assembly_id, attribute_name):
        return self._available


class _StubUnitOfWork:
    def __init__(self, respondents):
        self.respondents = respondents


def _category(*values: TargetValue) -> TargetCategory:
    return TargetCategory(assembly_id=uuid.uuid4(), name="Gender", values=list(values))


class TestMatchingAnAttributeColumn:
    def test_matches_an_exact_name(self):
        assert _matching_attribute("Gender", ["age", "Gender"]) == "Gender"

    def test_matches_loosely_across_case_and_punctuation(self):
        assert _matching_attribute("Age Range", ["age_range"]) == "age_range"
        assert _matching_attribute("age-range", ["AgeRange"]) == "AgeRange"

    def test_returns_empty_when_nothing_matches(self):
        assert _matching_attribute("Gender", ["age", "postcode"]) == ""

    def test_returns_empty_when_there_are_no_columns(self):
        assert _matching_attribute("Gender", []) == ""


class TestTheValueRow:
    def test_pool_count_is_pool_selected_and_confirmed(self):
        """Withdrawn respondents are no longer part of the pool a target is measured against."""
        row = _value_row(
            TargetValue(value="Male", min=0, max=10),
            target_pct=50.0,
            by_status={
                RespondentStatus.POOL: 5,
                RespondentStatus.SELECTED: 2,
                RespondentStatus.CONFIRMED: 1,
                RespondentStatus.WITHDRAWN: 4,
            },
            available_count=5,
        )

        assert row.pool_count == 8

    def test_selected_count_includes_the_confirmed(self):
        row = _value_row(
            TargetValue(value="Male", min=0, max=10),
            target_pct=50.0,
            by_status={RespondentStatus.SELECTED: 2, RespondentStatus.CONFIRMED: 3},
            available_count=0,
        )

        assert row.selected_count == 5
        assert row.confirmed_count == 3

    def test_shortfall_is_measured_over_the_available_count(self):
        """Not over pool_count: a selection run can only draw on who is available."""
        row = _value_row(
            TargetValue(value="Male", min=10, max=12),
            target_pct=50.0,
            by_status={RespondentStatus.POOL: 9, RespondentStatus.CONFIRMED: 6},
            available_count=4,
        )

        assert row.pool_count == 15
        assert row.shortfall == 6
        assert row.meetable is False

    def test_a_met_target_has_no_shortfall(self):
        row = _value_row(
            TargetValue(value="Male", min=3, max=5),
            target_pct=50.0,
            by_status={RespondentStatus.POOL: 4},
            available_count=4,
        )

        assert row.shortfall == 0
        assert row.meetable is True

    def test_a_surplus_never_gives_a_negative_shortfall(self):
        row = _value_row(
            TargetValue(value="Male", min=2, max=4),
            target_pct=50.0,
            by_status={RespondentStatus.POOL: 40},
            available_count=40,
        )

        assert row.shortfall == 0

    def test_a_value_nobody_holds_is_all_zeros(self):
        row = _value_row(TargetValue(value="Male", min=0, max=4), target_pct=50.0, by_status={}, available_count=0)

        assert (row.pool_count, row.available_count, row.selected_count, row.confirmed_count) == (0, 0, 0, 0)


class TestBuildingACategory:
    def _uow(self, **kwargs):
        return _StubUnitOfWork(_StubRespondentRepository(**kwargs))

    def test_uses_the_stored_percentage_when_there_is_one(self):
        category = _category(
            TargetValue(value="Male", min=1, max=1, percentage_target=40.0),
            TargetValue(value="Female", min=1, max=1, percentage_target=60.0),
        )

        result = _build_category(self._uow(), uuid.uuid4(), category, ["gender"])

        assert [row.target_pct for row in result.rows] == [40.0, 60.0]

    def test_falls_back_to_the_share_the_band_implies(self):
        category = _category(
            TargetValue(value="Male", min=1, max=3),
            TargetValue(value="Female", min=3, max=5),
        )

        result = _build_category(self._uow(), uuid.uuid4(), category, ["gender"])

        # (1 + 3) and (3 + 5) out of 12
        assert [row.target_pct for row in result.rows] == [pytest.approx(33.3), pytest.approx(66.7)]

    def test_falls_back_per_value_not_per_category(self):
        """A value with no percentage takes the band share even when its sibling has one."""
        category = _category(
            TargetValue(value="Male", min=1, max=1, percentage_target=90.0),
            TargetValue(value="Female", min=1, max=1),
        )

        result = _build_category(self._uow(), uuid.uuid4(), category, ["gender"])

        assert [row.target_pct for row in result.rows] == [90.0, 50.0]

    def test_counts_respondents_holding_a_value_the_targets_do_not_declare(self):
        category = _category(TargetValue(value="Male", min=0, max=10))
        uow = self._uow(
            by_status={
                "Male": {RespondentStatus.POOL: 3},
                "Non-binary": {RespondentStatus.POOL: 2, RespondentStatus.CONFIRMED: 1},
            },
        )

        result = _build_category(uow, uuid.uuid4(), category, ["gender"])

        assert result.rows[0].pool_count == 3
        assert result.unmatched_count == 3

    def test_withdrawn_respondents_do_not_count_as_unmatched(self):
        """Unmatched counts the same population as pool_count, so the two are comparable."""
        category = _category(TargetValue(value="Male", min=0, max=10))
        uow = self._uow(by_status={"Other": {RespondentStatus.WITHDRAWN: 5}})

        assert _build_category(uow, uuid.uuid4(), category, ["gender"]).unmatched_count == 0

    def test_a_category_matching_no_attribute_keeps_its_values_at_zero(self):
        """The targets are still set - there is just nothing to measure them against."""
        category = _category(TargetValue(value="Male", min=4, max=6))
        uow = self._uow(by_status={"Male": {RespondentStatus.POOL: 99}})

        result = _build_category(uow, uuid.uuid4(), category, ["postcode"])

        assert uow.respondents.queried_attributes == []
        assert result.rows[0].pool_count == 0
        assert result.rows[0].shortfall == 4
        assert result.unmatched_count == 0

    def test_a_category_with_no_values_has_no_rows(self):
        assert _build_category(self._uow(), uuid.uuid4(), _category(), ["gender"]).rows == []


class TestThePercentageHelper:
    def test_identical_bands_split_evenly(self):
        assert percentages_from_minmax([(1, 1), (1, 1)]) == [50.0, 50.0]

    def test_all_zero_bands_give_all_zeros_rather_than_dividing_by_zero(self):
        assert percentages_from_minmax([(0, 0), (0, 0)]) == [0.0, 0.0]

    def test_an_empty_set_gives_no_percentages(self):
        assert percentages_from_minmax([]) == []
