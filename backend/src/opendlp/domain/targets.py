"""ABOUTME: Target categories and values for stratified selection configuration
ABOUTME: Contains TargetCategory and TargetValue for defining selection quotas"""

import math
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sortition_algorithms.features import MAX_FLEX_UNSET

MAX_COMMENT_LENGTH = 2000
MAX_SOURCE_URL_LENGTH = 2048

# How far a category's percentages may sum from 100 before we warn. A constant
# we revise on feedback, deliberately not a per-assembly setting.
PERCENTAGE_TOLERANCE = 1.0

# Seats added to the top of a range when the percentage divides exactly. Honest
# at 1 and misleading above it - to widen further, express it as a minimum range
# instead: high = min(max(high, low + MIN_SEAT_RANGE), number_to_select).
SLACK_SEATS = 1

ALLOWED_URL_SCHEMES = ("http", "https")


def min_max_for_percentage(percentage: float, number_to_select: int) -> tuple[int, int]:
    """Min/max seats implied by a percentage of the assembly.

    floor/ceil of the exact share. An exact division would otherwise give
    min == max, so those are widened at the top by SLACK_SEATS.
    """
    exact = percentage * number_to_select / 100
    low, high = math.floor(exact), math.ceil(exact)
    if low == high and high > 0:
        high = min(high + SLACK_SEATS, number_to_select)
    return low, high


def percentages_from_minmax(min_max_pairs: Sequence[tuple[int, int]]) -> list[float]:
    """Percentages implied by a set of min/max target bands, normalised within the set.

    Uses (min + max) / sum(min + max), which is the ratio of midpoints with the
    halves cancelled, so it needs no seat count and totals 100. Every percentage
    is zero when every band is, since there is nothing to infer from.
    """
    denominator = sum(low + high for low, high in min_max_pairs)
    if denominator == 0:
        return [0.0] * len(min_max_pairs)
    return [round((low + high) / denominator * 100, 1) for low, high in min_max_pairs]


def percentage_of(numerator: int, denominator: int) -> float:
    """One count as a percentage of a total, to one decimal place.

    The shared rounding convention for every reported percentage, so the
    selection report and the dashboard cannot drift apart on the arithmetic.
    """
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, 1)


def validate_comment(comment: str) -> str:
    """Strip a free-text comment and reject one that is implausibly long."""
    stripped = comment.strip()
    if len(stripped) > MAX_COMMENT_LENGTH:
        raise ValueError(f"comment must be {MAX_COMMENT_LENGTH} characters or fewer")
    return stripped


def validate_source_url(source_url: str) -> str:
    """Strip and validate a source URL, allowing only http(s).

    Restricting the scheme here is a security invariant, not a formatting nicety:
    it is what makes the value safe to render as an `<a href>` later, ruling out
    `javascript:` and `data:` at the point of entry rather than trusting the
    template to do it.
    """
    stripped = source_url.strip()
    if not stripped:
        return ""
    if len(stripped) > MAX_SOURCE_URL_LENGTH:
        raise ValueError(f"source URL must be {MAX_SOURCE_URL_LENGTH} characters or fewer")
    parts = urlsplit(stripped)
    if parts.scheme not in ALLOWED_URL_SCHEMES or not parts.netloc:
        raise ValueError("source URL must be a full http:// or https:// address")
    return stripped


@dataclass
class TargetValue:
    """Target value with min/max quotas for a category"""

    value: str
    min: int
    max: int
    min_flex: int = 0
    max_flex: int = MAX_FLEX_UNSET  # Unset means library will calculate safe default
    percentage_target: float | None = None
    comment: str = ""
    minmax_manual: bool = False
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
        self.comment = validate_comment(self.comment)

    def _reset_flex(self) -> None:
        """Reset flex to defaults after any write to min/max.

        The sortition library recalculates safe defaults at selection time, and
        a stale min_flex would fail validation once min drops below it.
        """
        self.min_flex = 0
        self.max_flex = MAX_FLEX_UNSET

    def apply_percentage(self, number_to_select: int) -> bool:
        """Recalculate min/max from the percentage. Returns True if anything moved.

        No-op when there is no percentage, or when the auto-calculate link has been
        broken. When number_to_select is not yet agreed, min and max are both zero.
        """
        if self.percentage_target is None:
            return False
        if self.minmax_manual:
            return False

        if number_to_select <= 0:
            new_min, new_max = 0, 0
        else:
            new_min, new_max = min_max_for_percentage(self.percentage_target, number_to_select)

        if (new_min, new_max) == (self.min, self.max):
            return False

        self.min = new_min
        self.max = new_max
        self._reset_flex()
        self._validate()
        return True

    def set_manual_min_max(self, min_count: int, max_count: int) -> None:
        """Set min/max directly, breaking the auto-calculate link."""
        if min_count < 0:
            raise ValueError("min cannot be negative")
        if max_count < min_count:
            raise ValueError("max must be >= min")

        self.min = min_count
        self.max = max_count
        self.minmax_manual = True
        self._reset_flex()
        self._validate()

    def relink_to_percentage(self, number_to_select: int) -> None:
        """Restore auto-calculation and immediately recalculate.

        Raises ValueError if there is no percentage to link back to.
        """
        if self.percentage_target is None:
            raise ValueError("cannot relink a value with no percentage")
        self.minmax_manual = False
        self.apply_percentage(number_to_select)

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
        sort_order: int = 0,
        values: list[TargetValue] | None = None,
        category_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        comment: str = "",
        source_url: str = "",
    ):
        if not name.strip():
            raise ValueError("Category name is required")

        self.id = category_id or uuid.uuid4()
        self.assembly_id = assembly_id
        self.name = name.strip()
        self.sort_order = sort_order
        self.values = values or []
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)
        self.comment = validate_comment(comment)
        self.source_url = validate_source_url(source_url)

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

    def percentage_total(self) -> float | None:
        """Sum of the percentages across this category's values.

        Returns None if no value has a percentage set - an unset category is not
        a category that sums to zero.
        """
        percentages = [v.percentage_target for v in self.values if v.percentage_target is not None]
        if not percentages:
            return None
        return round(sum(percentages), 2)

    def percentage_total_is_plausible(self, tolerance: float = PERCENTAGE_TOLERANCE) -> bool:
        """True if the percentages sum to within `tolerance` of 100."""
        total = self.percentage_total()
        if total is None:
            return True
        return abs(total - 100.0) <= tolerance

    def percentages_from_minmax(self) -> list[float]:
        """The percentages this category's min/max bands imply, in value order."""
        return percentages_from_minmax([(v.min, v.max) for v in self.values])

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
            sort_order=self.sort_order,
            values=[TargetValue(**vars(v)) for v in self.values],
            category_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            comment=self.comment,
            source_url=self.source_url,
        )


def target_categories_to_snapshot(categories: list[TargetCategory]) -> list[dict[str, Any]]:
    """Serialise target categories for storage on a SelectionRunRecord.

    Excludes UUIDs and timestamps so the snapshot only carries the
    category/value data the algorithm consumed at selection time.
    """
    return [
        {
            "name": cat.name,
            "sort_order": cat.sort_order,
            "comment": cat.comment,
            "source_url": cat.source_url,
            "values": [
                {
                    "value": v.value,
                    "min": v.min,
                    "max": v.max,
                    "min_flex": v.min_flex,
                    "max_flex": v.max_flex,
                    "percentage_target": v.percentage_target,
                    "comment": v.comment,
                    "minmax_manual": v.minmax_manual,
                }
                for v in cat.values
            ],
        }
        for cat in categories
    ]
