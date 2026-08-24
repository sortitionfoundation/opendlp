"""ABOUTME: Unit tests for TargetCategory and TargetValue domain models
ABOUTME: Tests validation, add/remove operations, and in-place value updates"""

import uuid

import pytest
from sortition_algorithms.features import MAX_FLEX_UNSET

from opendlp.domain.targets import (
    MAX_COMMENT_LENGTH,
    MAX_SOURCE_URL_LENGTH,
    TargetCategory,
    TargetValue,
    min_max_for_percentage,
    target_categories_to_snapshot,
    validate_source_url,
)


class TestTargetValue:
    def test_create_target_value_with_valid_data(self):
        tv = TargetValue(value="Male", min=10, max=15)
        assert tv.value == "Male"
        assert tv.min == 10
        assert tv.max == 15
        assert tv.min_flex == 0
        assert tv.max_flex == MAX_FLEX_UNSET
        assert tv.percentage_target is None
        assert tv.value_id is not None

    def test_validate_min_less_than_max(self):
        with pytest.raises(ValueError, match="max must be >= min"):
            TargetValue(value="Male", min=15, max=10)

    def test_validate_negative_min(self):
        with pytest.raises(ValueError, match="min cannot be negative"):
            TargetValue(value="Male", min=-1, max=10)

    def test_validate_min_flex_greater_than_min(self):
        with pytest.raises(ValueError, match="min_flex must be <= min"):
            TargetValue(value="Male", min=10, max=15, min_flex=12)

    def test_validate_max_flex_less_than_max(self):
        with pytest.raises(ValueError, match=f"max_flex must be {MAX_FLEX_UNSET}"):
            TargetValue(value="Male", min=10, max=15, max_flex=12)

    def test_validate_percentage_target_type(self):
        with pytest.raises(TypeError, match="percentage_target must be a number"):
            TargetValue(value="Male", min=10, max=15, percentage_target="50")  # type: ignore[arg-type]

    def test_validate_percentage_target_range(self):
        with pytest.raises(ValueError, match="percentage_target must be between 0 and 100"):
            TargetValue(value="Male", min=10, max=15, percentage_target=150.0)

    def test_percentage_target_none_is_valid(self):
        tv = TargetValue(value="Male", min=10, max=15, percentage_target=None)
        assert tv.percentage_target is None

    def test_validate_empty_value(self):
        with pytest.raises(ValueError, match="value cannot be empty"):
            TargetValue(value="", min=10, max=15)

    def test_to_feature_value_minmax(self):
        tv = TargetValue(value="Male", min=10, max=15, min_flex=8, max_flex=18)
        result = tv.to_feature_value_minmax()
        assert result == {"min": 10, "max": 15, "min_flex": 8, "max_flex": 18}


class TestTargetCategory:
    def test_create_category_with_valid_data(self):
        assembly_id = uuid.uuid4()
        cat = TargetCategory(assembly_id=assembly_id, name="Gender")
        assert cat.name == "Gender"
        assert cat.assembly_id == assembly_id
        assert cat.id is not None
        assert cat.values == []

    def test_validate_empty_name(self):
        with pytest.raises(ValueError, match="Category name is required"):
            TargetCategory(assembly_id=uuid.uuid4(), name="")

    def test_add_value(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        tv = TargetValue(value="Male", min=10, max=15)
        cat.add_value(tv)
        assert len(cat.values) == 1
        assert cat.values[0] == tv

    def test_add_duplicate_value_raises_error(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        cat.add_value(TargetValue(value="Male", min=10, max=15))

        with pytest.raises(ValueError, match="Value 'Male' already exists"):
            cat.add_value(TargetValue(value="Male", min=12, max=18))

    def test_remove_value(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        tv = TargetValue(value="Male", min=10, max=15)
        cat.add_value(tv)

        result = cat.remove_value(tv.value_id)
        assert result is True
        assert len(cat.values) == 0

    def test_remove_nonexistent_value(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        result = cat.remove_value(uuid.uuid4())
        assert result is False

    def test_get_value(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        tv = TargetValue(value="Male", min=10, max=15)
        cat.add_value(tv)

        found = cat.get_value("Male")
        assert found == tv

        not_found = cat.get_value("Other")
        assert not_found is None

    def test_to_feature_dict(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        cat.add_value(TargetValue(value="Male", min=10, max=15))
        cat.add_value(TargetValue(value="Female", min=10, max=15))

        result = cat.to_feature_dict()
        assert "Male" in result
        assert "Female" in result
        assert result["Male"]["min"] == 10
        assert result["Female"]["max"] == 15

    def test_create_detached_copy(self):
        assembly_id = uuid.uuid4()
        cat = TargetCategory(assembly_id=assembly_id, name="Gender", comment="Test")
        cat.add_value(TargetValue(value="Male", min=10, max=15))

        copy = cat.create_detached_copy()
        assert copy.id == cat.id
        assert copy.assembly_id == assembly_id
        assert copy.name == "Gender"
        assert len(copy.values) == 1
        assert copy is not cat  # Different instance


class TestTargetValueInPlaceUpdate:
    def test_update_target_value_in_place(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        val = TargetValue(value="Male", min=5, max=10)
        cat.add_value(val)

        val.value = "Male (updated)"
        val.min = 6
        val.max = 12
        val._validate()

        assert val.value == "Male (updated)"
        assert val.min == 6
        assert val.max == 12
        assert val.min_flex == 0
        assert val.max_flex == MAX_FLEX_UNSET

    def test_update_target_value_invalid_min_max(self):
        val = TargetValue(value="Male", min=5, max=10)
        val.min = 15
        with pytest.raises(ValueError, match="max must be >= min"):
            val._validate()


class TestTargetCategoriesToSnapshot:
    def test_empty_list(self):
        assert target_categories_to_snapshot([]) == []

    def test_single_category_single_value(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender", comment="Gender split", sort_order=2)
        cat.add_value(TargetValue(value="Man", min=29, max=31, percentage_target=48.5, comment="men"))

        snapshot = target_categories_to_snapshot([cat])

        assert snapshot == [
            {
                "name": "Gender",
                "sort_order": 2,
                "comment": "Gender split",
                "source_url": "",
                "values": [
                    {
                        "value": "Man",
                        "min": 29,
                        "max": 31,
                        "min_flex": 0,
                        "max_flex": MAX_FLEX_UNSET,
                        "percentage_target": 48.5,
                        "comment": "men",
                        "minmax_manual": False,
                    },
                ],
            },
        ]

    def test_multi_category_multi_value(self):
        a = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        a.add_value(TargetValue(value="Man", min=10, max=12))
        a.add_value(TargetValue(value="Woman", min=10, max=12))
        b = TargetCategory(assembly_id=uuid.uuid4(), name="Age")
        b.add_value(TargetValue(value="18-29", min=5, max=7, min_flex=3, max_flex=10))

        snapshot = target_categories_to_snapshot([a, b])

        assert [c["name"] for c in snapshot] == ["Gender", "Age"]
        assert [v["value"] for v in snapshot[0]["values"]] == ["Man", "Woman"]
        assert snapshot[1]["values"][0]["min_flex"] == 3
        assert snapshot[1]["values"][0]["max_flex"] == 10

    def test_snapshot_excludes_uuids_and_timestamps(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        cat.add_value(TargetValue(value="Man", min=1, max=2))

        snapshot = target_categories_to_snapshot([cat])

        assert "id" not in snapshot[0]
        assert "category_id" not in snapshot[0]
        assert "assembly_id" not in snapshot[0]
        assert "created_at" not in snapshot[0]
        assert "updated_at" not in snapshot[0]
        assert "value_id" not in snapshot[0]["values"][0]


class TestMinMaxForPercentage:
    @pytest.mark.parametrize(
        ("percentage", "number_to_select", "expected"),
        [
            # Exact divisions are widened by one seat - the case that would
            # otherwise pin min and max to the same number.
            (50, 100, (50, 51)),
            (99, 100, (99, 100)),
            (25, 4, (1, 2)),
            # Non-exact divisions already span a seat, so they are left alone.
            (33.3, 100, (33, 34)),
            (50, 101, (50, 51)),
            (1, 20, (0, 1)),
        ],
    )
    def test_widens_only_exact_divisions(self, percentage, number_to_select, expected):
        assert min_max_for_percentage(percentage, number_to_select) == expected

    def test_zero_percent_is_never_widened(self):
        """A deliberate zero target must not be given a seat."""
        assert min_max_for_percentage(0, 100) == (0, 0)

    def test_max_is_clamped_to_assembly_size(self):
        """100% must not produce a max above the number of seats available."""
        assert min_max_for_percentage(100, 100) == (100, 100)
        assert min_max_for_percentage(100, 1) == (1, 1)

    def test_range_is_never_wider_than_one_seat(self):
        """The single sentence describing what this function guarantees."""
        for number_to_select in range(1, 120):
            for percentage in (0, 0.4, 1, 12.5, 25, 33.3, 50, 66.7, 99, 99.5, 100):
                low, high = min_max_for_percentage(percentage, number_to_select)
                assert 0 <= high - low <= 1, f"{percentage}% of {number_to_select} gave ({low}, {high})"

    def test_category_totals_stay_feasible(self):
        """sum(mins) <= number_to_select <= sum(maxes), which the library requires."""
        for percentages, number_to_select in [
            ([50, 50], 100),
            ([33.3, 33.3, 33.4], 100),
            ([25, 25, 25, 25], 4),
            ([1, 99], 20),
            ([20, 20, 20, 20, 20], 100),
            ([100], 100),
        ]:
            pairs = [min_max_for_percentage(p, number_to_select) for p in percentages]
            assert sum(low for low, _ in pairs) <= number_to_select
            assert sum(high for _, high in pairs) >= number_to_select


class TestApplyPercentage:
    def test_no_percentage_leaves_minmax_untouched(self):
        """The guard that protects every pre-existing hand-entered target."""
        tv = TargetValue(value="Man", min=10, max=15)
        assert tv.apply_percentage(100) is False
        assert (tv.min, tv.max) == (10, 15)

    def test_manual_minmax_is_a_no_op(self):
        tv = TargetValue(value="Man", min=10, max=15, percentage_target=50.0)
        tv.set_manual_min_max(20, 25)
        assert tv.apply_percentage(100) is False
        assert (tv.min, tv.max) == (20, 25)

    def test_zero_number_to_select_zeroes_minmax(self):
        tv = TargetValue(value="Man", min=10, max=15, percentage_target=50.0)
        assert tv.apply_percentage(0) is True
        assert (tv.min, tv.max) == (0, 0)

    def test_recalculates_from_percentage(self):
        tv = TargetValue(value="Man", min=0, max=0, percentage_target=50.0)
        assert tv.apply_percentage(100) is True
        assert (tv.min, tv.max) == (50, 51)

    def test_returns_false_when_nothing_moves(self):
        tv = TargetValue(value="Man", min=50, max=51, percentage_target=50.0)
        assert tv.apply_percentage(100) is False

    def test_large_min_flex_survives_min_dropping_to_zero(self):
        """The flex reset is what keeps min_flex <= min satisfied."""
        tv = TargetValue(value="Man", min=40, max=50, min_flex=40, percentage_target=50.0)
        tv.apply_percentage(0)
        assert (tv.min, tv.max) == (0, 0)
        assert tv.min_flex == 0
        assert tv.max_flex == MAX_FLEX_UNSET


class TestManualMinMaxAndRelink:
    def test_set_manual_min_max_breaks_the_link(self):
        tv = TargetValue(value="Man", min=0, max=0, percentage_target=50.0)
        tv.set_manual_min_max(30, 40)
        assert tv.minmax_manual is True
        tv.apply_percentage(100)
        assert (tv.min, tv.max) == (30, 40)

    def test_relink_restores_auto_calculation(self):
        tv = TargetValue(value="Man", min=0, max=0, percentage_target=50.0)
        tv.set_manual_min_max(30, 40)
        tv.relink_to_percentage(100)
        assert tv.minmax_manual is False
        assert (tv.min, tv.max) == (50, 51)

    def test_relink_without_a_percentage_raises(self):
        tv = TargetValue(value="Man", min=10, max=15)
        with pytest.raises(ValueError, match="no percentage"):
            tv.relink_to_percentage(100)

    def test_invalid_pair_leaves_the_object_unmodified(self):
        """max < min must be rejected before either field is assigned."""
        tv = TargetValue(value="Man", min=10, max=15)
        with pytest.raises(ValueError, match="max must be >= min"):
            tv.set_manual_min_max(20, 5)
        assert (tv.min, tv.max) == (10, 15)
        assert tv.minmax_manual is False


class TestPercentageTotals:
    def test_returns_none_when_no_value_has_a_percentage(self):
        """An unset category is not a category that sums to zero."""
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        cat.add_value(TargetValue(value="Man", min=0, max=0))
        assert cat.percentage_total() is None
        assert cat.percentage_total_is_plausible() is True

    def test_sums_the_percentages(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        cat.add_value(TargetValue(value="Man", min=0, max=0, percentage_target=51.0))
        cat.add_value(TargetValue(value="Woman", min=0, max=0, percentage_target=49.0))
        assert cat.percentage_total() == pytest.approx(100.0)

    @pytest.mark.parametrize(
        ("percentages", "plausible"),
        [
            ([50.0, 49.9], True),
            ([50.0, 50.1], True),
            ([50.0, 49.0], True),
            ([50.0, 51.0], True),
            ([50.0, 48.9], False),
            ([50.0, 51.1], False),
            ([50.0, 45.0], False),
        ],
    )
    def test_tolerance_boundaries_are_inclusive(self, percentages, plausible):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        for i, percentage in enumerate(percentages):
            cat.add_value(TargetValue(value=f"v{i}", min=0, max=0, percentage_target=percentage))
        assert cat.percentage_total_is_plausible() is plausible

    def test_half_filled_category_warns(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        cat.add_value(TargetValue(value="Man", min=0, max=0, percentage_target=50.0))
        cat.add_value(TargetValue(value="Woman", min=0, max=0))
        assert cat.percentage_total_is_plausible() is False


class TestDerivePercentagesFromMinMax:
    def test_normalises_within_the_category(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        cat.add_value(TargetValue(value="Man", min=10, max=20))
        cat.add_value(TargetValue(value="Woman", min=30, max=40))
        cat.derive_percentages_from_minmax()
        assert [v.percentage_target for v in cat.values] == [30.0, 70.0]
        assert cat.percentage_total() == pytest.approx(100.0)

    def test_all_zero_derives_nothing(self):
        """The create_target_category case, where auto-added values arrive at 0/0."""
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Gender")
        cat.add_value(TargetValue(value="Man", min=0, max=0))
        cat.derive_percentages_from_minmax()
        assert cat.values[0].percentage_target is None

    def test_rounding_drift_stays_within_tolerance(self):
        cat = TargetCategory(assembly_id=uuid.uuid4(), name="Age")
        for name in ("a", "b", "c"):
            cat.add_value(TargetValue(value=name, min=10, max=10))
        cat.derive_percentages_from_minmax()
        assert [v.percentage_target for v in cat.values] == [33.3, 33.3, 33.3]
        assert cat.percentage_total() == pytest.approx(99.9)
        assert cat.percentage_total_is_plausible() is True


class TestSourceUrlValidation:
    @pytest.mark.parametrize(
        "url",
        ["https://www.ons.gov.uk/dataset", "http://example.com", "https://example.com/a?b=c#d"],
    )
    def test_accepts_http_and_https(self, url):
        assert validate_source_url(url) == url

    def test_empty_is_valid(self):
        assert validate_source_url("") == ""
        assert validate_source_url("   ") == ""

    @pytest.mark.parametrize(
        "url",
        ["javascript:alert(1)", "data:text/html,<script>", "example.com", "ftp://example.com", "https://"],
    )
    def test_rejects_anything_else(self, url):
        with pytest.raises(ValueError, match="http"):
            validate_source_url(url)

    def test_rejects_an_over_long_url(self):
        with pytest.raises(ValueError, match="2048"):
            validate_source_url("https://example.com/" + "a" * MAX_SOURCE_URL_LENGTH)

    def test_category_validates_its_source_url(self):
        with pytest.raises(ValueError, match="http"):
            TargetCategory(assembly_id=uuid.uuid4(), name="Gender", source_url="javascript:alert(1)")


class TestComments:
    def test_comment_is_stripped(self):
        tv = TargetValue(value="Man", min=0, max=0, comment="  boosted by 2  ")
        assert tv.comment == "boosted by 2"

    def test_over_long_value_comment_raises(self):
        with pytest.raises(ValueError, match="2000"):
            TargetValue(value="Man", min=0, max=0, comment="x" * (MAX_COMMENT_LENGTH + 1))

    def test_over_long_category_comment_raises(self):
        with pytest.raises(ValueError, match="2000"):
            TargetCategory(assembly_id=uuid.uuid4(), name="Gender", comment="x" * (MAX_COMMENT_LENGTH + 1))


class TestDetachedCopyCarriesNewFields:
    def test_carries_every_field(self):
        cat = TargetCategory(
            assembly_id=uuid.uuid4(),
            name="Gender",
            comment="from the census",
            source_url="https://www.ons.gov.uk/dataset",
        )
        cat.add_value(
            TargetValue(value="Man", min=30, max=40, percentage_target=50.0, comment="boosted", minmax_manual=True)
        )

        copy = cat.create_detached_copy()

        assert copy.comment == "from the census"
        assert copy.source_url == "https://www.ons.gov.uk/dataset"
        value = copy.values[0]
        assert value.percentage_target == 50.0
        assert value.comment == "boosted"
        assert value.minmax_manual is True
