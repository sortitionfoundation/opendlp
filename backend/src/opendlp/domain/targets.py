"""ABOUTME: Target categories and values for stratified selection configuration
ABOUTME: Contains TargetCategory and TargetValue for defining selection quotas"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sortition_algorithms.features import MAX_FLEX_UNSET


@dataclass
class TargetValue:
    """Target value with min/max quotas for a category"""

    value: str
    min: int
    max: int
    min_flex: int = 0
    max_flex: int = MAX_FLEX_UNSET  # Unset means library will calculate safe default
    percentage_target: float | None = None
    description: str = ""
    value_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if self.value_id is None:
            self.value_id = uuid.uuid4()
        self._validate()

    def _validate(self) -> None:
        """Validate target value constraints"""
        if self.min < 0:
            raise ValueError("min cannot be negative")
        if self.max < self.min:
            raise ValueError("max must be >= min")
        if self.min_flex < 0:
            raise ValueError("min_flex cannot be negative")
        if self.min_flex > self.min:
            raise ValueError("min_flex must be <= min")
        if self.max_flex != MAX_FLEX_UNSET and self.max_flex < self.max:
            raise ValueError(f"max_flex must be {MAX_FLEX_UNSET} (unset) or >= max")
        if self.percentage_target is not None:
            if not isinstance(self.percentage_target, int | float):
                raise TypeError("percentage_target must be a number or None")
            if not 0 <= self.percentage_target <= 100:
                raise ValueError("percentage_target must be between 0 and 100")
        if not self.value.strip():
            raise ValueError("value cannot be empty")

    def to_feature_value_minmax(self) -> dict[str, Any]:
        """Convert to sortition-algorithms FeatureValueMinMax dict format"""
        return {
            "min": self.min,
            "max": self.max,
            "min_flex": self.min_flex,
            "max_flex": self.max_flex,
        }


class TargetCategory:
    """Target category for stratified selection (e.g., Gender, Age)"""

    def __init__(
        self,
        assembly_id: uuid.UUID,
        name: str,
        description: str = "",
        sort_order: int = 0,
        values: list[TargetValue] | None = None,
        category_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        if not name.strip():
            raise ValueError("Category name is required")

        self.id = category_id or uuid.uuid4()
        self.assembly_id = assembly_id
        self.name = name.strip()
        self.description = description.strip()
        self.sort_order = sort_order
        self.values = values or []
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    def add_value(self, target_value: TargetValue) -> None:
        """Add a target value to this category"""
        if any(v.value == target_value.value for v in self.values):
            raise ValueError(f"Value '{target_value.value}' already exists in category '{self.name}'")
        self.values.append(target_value)
        self.updated_at = datetime.now(UTC)

    def remove_value(self, value_id: uuid.UUID) -> bool:
        """Remove a target value by ID. Returns True if found and removed."""
        original_len = len(self.values)
        self.values = [v for v in self.values if v.value_id != value_id]
        if len(self.values) < original_len:
            self.updated_at = datetime.now(UTC)
            return True
        return False

    def get_value(self, value_str: str) -> TargetValue | None:
        """Get a target value by its value string"""
        for v in self.values:
            if v.value == value_str:
                return v
        return None

    def to_feature_dict(self) -> dict[str, dict[str, Any]]:
        """Convert to sortition-algorithms Feature dict format (value -> FeatureValueMinMax)"""
        return {v.value: v.to_feature_value_minmax() for v in self.values}

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TargetCategory):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "TargetCategory":
        """Create a detached copy for use outside SQLAlchemy sessions"""
        return TargetCategory(
            assembly_id=self.assembly_id,
            name=self.name,
            description=self.description,
            sort_order=self.sort_order,
            values=[TargetValue(**vars(v)) for v in self.values],
            category_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
