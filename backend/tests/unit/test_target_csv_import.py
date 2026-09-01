"""ABOUTME: Unit tests for importing targets from a CSV, without a database
ABOUTME: The derived percentages - midpoint, ratio, and the clamp that keeps them loadable"""

import uuid

import pytest

from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.service_layer.target_csv_import import _clamp_percentage, _fill_missing_percentages


def _category(values: list[TargetValue]) -> TargetCategory:
    category = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
    for value in values:
        category.add_value(value)
    return category


class TestClampPercentage:
    """The domain refuses anything outside 0-100, on load as well as on construction."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [(183.33, 100.0), (100.0, 100.0), (50.04, 50.0), (0.0, 0.0), (-5.0, 0.0)],
    )
    def test_holds_the_value_inside_the_range(self, raw, expected):
        assert _clamp_percentage(raw) == expected


class TestFillMissingPercentages:
    def test_derives_from_the_midpoint_when_seats_are_known(self):
        category = _category([TargetValue(value="Male", min=10, max=15)])

        _fill_missing_percentages(category, number_to_select=100)

        assert category.get_value("Male").percentage_target == 12.5

    def test_normalises_within_the_category_when_seats_are_unknown(self):
        category = _category([TargetValue(value="Male", min=10, max=20), TargetValue(value="Female", min=30, max=40)])

        _fill_missing_percentages(category, number_to_select=0)

        assert category.get_value("Male").percentage_target == 30.0
        assert category.get_value("Female").percentage_target == 70.0

    def test_a_midpoint_above_the_seat_count_is_clamped(self):
        """Otherwise the row is written once and then raises on every read of it."""
        category = _category([TargetValue(value="Male", min=50, max=60)])

        _fill_missing_percentages(category, number_to_select=10)

        assert category.get_value("Male").percentage_target == 100.0

    def test_leaves_an_explicit_percentage_alone(self):
        category = _category([TargetValue(value="Male", min=1, max=2, percentage_target=42.0)])

        _fill_missing_percentages(category, number_to_select=10)

        assert category.get_value("Male").percentage_target == 42.0

    def test_all_zero_minmax_with_no_seats_leaves_them_unset(self):
        category = _category([TargetValue(value="Male", min=0, max=0)])

        _fill_missing_percentages(category, number_to_select=0)

        assert category.get_value("Male").percentage_target is None
