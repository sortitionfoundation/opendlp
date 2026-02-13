"""Unit tests for TargetCategory and TargetValue domain models."""

import uuid

import pytest
from sortition_algorithms.features import MAX_FLEX_UNSET

from opendlp.domain.targets import TargetCategory, TargetValue


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
            TargetValue(value="Male", min=10, max=15, percentage_target=50)

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
        cat = TargetCategory(assembly_id=assembly_id, name="Gender", description="Test")
        cat.add_value(TargetValue(value="Male", min=10, max=15))

        copy = cat.create_detached_copy()
        assert copy.id == cat.id
        assert copy.assembly_id == assembly_id
        assert copy.name == "Gender"
        assert len(copy.values) == 1
        assert copy is not cat  # Different instance
