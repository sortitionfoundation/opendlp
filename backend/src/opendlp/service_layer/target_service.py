"""ABOUTME: Target category and value service layer for stratified selection quotas
ABOUTME: Provides CRUD, CSV import and percentage-driven min/max for assembly targets"""

import csv as csv_module
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO
from typing import Any, NamedTuple, cast

from sortition_algorithms.adapters import SelectionData
from sortition_algorithms.features import FeatureCollection, read_in_features
from sqlalchemy.orm.attributes import flag_modified

from opendlp.adapters.sortition_data_adapter import OpenDLPDataAdapter
from opendlp.domain.assembly import Assembly
from opendlp.domain.targets import (
    TargetCategory,
    TargetValue,
    validate_comment,
    validate_source_url,
)
from opendlp.translations import gettext as _

from .constants import MAX_DISTINCT_VALUES_FOR_AUTO_ADD, SORT_ORDER_STEP
from .exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    NotFoundError,
    UserNotFoundError,
)
from .permissions import can_manage_assembly, can_view_assembly
from .respondent_service import get_respondent_attribute_columns, get_respondent_attribute_value_counts
from .unit_of_work import AbstractUnitOfWork

# Distinguishes "not submitted, leave alone" from a submitted None, which for a
# percentage legitimately means "clear it".
UNSET: Any = object()

# How much of a conflicting CSV cell to echo back in a warning.
WARNING_VALUE_CHARS = 60


@dataclass(frozen=True)
class TargetValueChange:
    """A value whose min/max moved, with the numbers before and after."""

    category_id: uuid.UUID
    value_id: uuid.UUID
    value: str
    old_min: int
    old_max: int
    new_min: int
    new_max: int


class TargetImportResult(NamedTuple):
    """Imported categories, plus non-fatal warnings worth showing the user."""

    categories: list[TargetCategory]
    warnings: list[str]


@dataclass
class TargetValueEdit:
    """One value in a bulk save. `value_id` of None means a new value."""

    value: str
    value_id: uuid.UUID | None = None
    percentage: float | None = None
    min: int | None = None
    max: int | None = None
    comment: str = ""
    deleted: bool = False
    relink: bool = False


@dataclass
class TargetCategoryEdit:
    """One category in a bulk save, with all of its submitted values.

    A `category_id` of None means a category the user added in the form and that
    does not exist yet.
    """

    category_id: uuid.UUID | None
    name: str
    comment: str = ""
    source_url: str = ""
    values: list[TargetValueEdit] = field(default_factory=list)
    deleted: bool = False
    sort_order: int | None = None


def _load_user_and_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    action: str,
) -> Assembly:
    """Load the assembly, checking the user may manage it."""
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action=action,
            required_role="assembly-manager, global-organiser or admin",
        )
    return cast("Assembly", assembly)


def _get_category(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
) -> TargetCategory:
    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")
    return category


def _get_value(category: TargetCategory, value_id: uuid.UUID) -> TargetValue:
    existing = next((v for v in category.values if v.value_id == value_id), None)
    if not existing:
        raise NotFoundError(f"Target value {value_id} not found")
    return existing


def create_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    name: str,
    sort_order: int | None = None,
    comment: str = "",
    source_url: str = "",
) -> TargetCategory:
    """Create a new target category for an assembly.

    When `sort_order` is not supplied the category is placed after the existing
    ones. That is policy, so it belongs here rather than in the entrypoint.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="create target category",
            required_role="assembly-manager, global-organiser or admin",
        )

    existing = uow.target_categories.get_by_assembly_id(assembly_id)
    if any(c.name.lower() == name.lower() for c in existing):
        raise ValueError(f"A category named '{name}' already exists")

    if sort_order is None:
        sort_order = max((c.sort_order for c in existing), default=0) + SORT_ORDER_STEP

    category = TargetCategory(
        assembly_id=assembly_id,
        name=name,
        sort_order=sort_order,
        comment=comment,
        source_url=source_url,
    )

    # Auto-add values if category name matches a low-cardinality respondent column
    attribute_columns = get_respondent_attribute_columns(uow, assembly_id)
    columns_lower = {col.lower(): col for col in attribute_columns}
    matched_col = columns_lower.get(name.lower())
    if matched_col is not None:
        value_counts = get_respondent_attribute_value_counts(uow, assembly_id, matched_col)
        if 0 < len(value_counts) < MAX_DISTINCT_VALUES_FOR_AUTO_ADD:
            for value_name in sorted(value_counts.keys()):
                category.add_value(TargetValue(value=value_name, min=0, max=0))

    uow.target_categories.add(category)
    return category.create_detached_copy()


def get_targets_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> list[TargetCategory]:
    """Get all target categories for an assembly.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(
            action="view targets",
            required_role="assembly role or global privileges",
        )

    categories = uow.target_categories.get_by_assembly_id(assembly_id)
    return [c.create_detached_copy() for c in categories]


VALUE_PERCENTAGE_COLUMN = "percentage"
VALUE_COMMENT_COLUMN = "comment"
CATEGORY_COMMENT_COLUMN = "category_comment"
CATEGORY_SOURCE_URL_COLUMN = "source_url"


def _truncate(text: str) -> str:
    if len(text) <= WARNING_VALUE_CHARS:
        return text
    return text[: WARNING_VALUE_CHARS - 1] + "\u2026"


def _cell(row: dict[str, str], columns: dict[str, str], name: str) -> str:
    """Read one of our optional columns from a raw CSV row, case-insensitively."""
    header = columns.get(name)
    if header is None:
        return ""
    return (row.get(header) or "").strip()


def _parse_percentage(raw: str, feature: str, value: str) -> float | None:
    if not raw:
        return None
    try:
        percentage = float(raw.rstrip("%").strip())
    except ValueError as e:
        raise InvalidSelection(f"Invalid percentage '{raw}' for {feature} / {value}") from e
    if not 0 <= percentage <= 100:
        raise InvalidSelection(f"Percentage '{raw}' for {feature} / {value} must be between 0 and 100")
    return percentage


def _collect_csv_extras(
    body: list[dict[str, str]],
    columns: dict[str, str],
    feature_col: str,
    value_col: str,
) -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, dict[str, list[str]]]]:
    """Index our optional columns out of the raw rows.

    Value-level extras are keyed by (feature, value). Category-level extras are
    keyed by feature and keep *every* distinct non-empty value seen, so a
    disagreement between rows can be reported rather than silently resolved.
    """
    value_extras: dict[tuple[str, str], dict[str, str]] = {}
    category_extras: dict[str, dict[str, list[str]]] = {}

    for row in body:
        feature = (row.get(feature_col) or "").strip()
        value = (row.get(value_col) or "").strip()
        if not feature or not value:
            continue

        value_extras[(feature, value)] = {
            VALUE_PERCENTAGE_COLUMN: _cell(row, columns, VALUE_PERCENTAGE_COLUMN),
            VALUE_COMMENT_COLUMN: _cell(row, columns, VALUE_COMMENT_COLUMN),
        }

        seen = category_extras.setdefault(feature, {CATEGORY_COMMENT_COLUMN: [], CATEGORY_SOURCE_URL_COLUMN: []})
        for column in (CATEGORY_COMMENT_COLUMN, CATEGORY_SOURCE_URL_COLUMN):
            cell = _cell(row, columns, column)
            if cell and cell not in seen[column]:
                seen[column].append(cell)

    return value_extras, category_extras


def _resolve_category_column(
    feature: str,
    column: str,
    category_extras: dict[str, dict[str, list[str]]],
    warnings: list[str],
) -> str:
    """First non-empty value wins; a disagreement between rows is reported."""
    seen = category_extras.get(feature, {}).get(column, [])
    if not seen:
        return ""
    if len(seen) > 1:
        warnings.append(
            _(
                'Rows for "%(category)s" gave different values for %(column)s. '
                'Using "%(used)s" and ignoring %(count)s other value(s).',
                category=feature,
                column=column,
                used=_truncate(seen[0]),
                count=len(seen) - 1,
            )
        )
    return seen[0]


def import_targets_from_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    csv_content: str,
    replace_existing: bool = False,
) -> TargetImportResult:
    """
    Import target categories from CSV using sortition-algorithms library.

    CSV format matches sortition-algorithms feature files with columns:
    feature, value, min, max, min_flex, max_flex

    Four optional columns are read by us rather than the library, which ignores
    headers it does not recognise: `percentage` and `comment` per value,
    `category_comment` and `source_url` per category.

    Every imported value is marked `minmax_manual`. The CSV format makes min and
    max mandatory, so imported numbers are always deliberate; leaving the link
    intact would let a later change to number_to_select silently narrow every
    imported range from the derived percentage.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = _load_user_and_assembly(uow, user_id, assembly_id, "import targets")

    # Parse and validate CSV using sortition-algorithms
    # Note: read_in_features() already calls set_default_max_flex() and check_min_max()
    csv_file = StringIO(csv_content)
    reader = csv_module.DictReader(csv_file)

    if not reader.fieldnames:
        raise InvalidSelection("CSV file is empty or malformed")

    headers = list(reader.fieldnames)
    body = list(reader)

    try:
        feature_collection, feature_col, value_col = read_in_features(headers, body)
    except Exception as e:
        raise InvalidSelection(f"Failed to parse CSV: {e!s}") from e

    columns = {h.strip().lower(): h for h in headers}
    value_extras, category_extras = _collect_csv_extras(body, columns, feature_col, value_col)
    warnings: list[str] = []

    # Replace existing if requested
    if replace_existing:
        uow.target_categories.delete_all_for_assembly(assembly_id)

    # Convert to TargetCategory objects
    categories = []
    for idx, (feature_name, feature_values) in enumerate(feature_collection.items(), start=1):
        category = TargetCategory(
            assembly_id=assembly_id,
            name=feature_name,
            sort_order=idx * SORT_ORDER_STEP,
            comment=_resolve_category_column(feature_name, CATEGORY_COMMENT_COLUMN, category_extras, warnings),
            source_url=_resolve_category_column(feature_name, CATEGORY_SOURCE_URL_COLUMN, category_extras, warnings),
        )

        # Add target values
        for value_name, fv_minmax in feature_values.items():
            extras = value_extras.get((feature_name, value_name), {})
            target_val = TargetValue(
                value=value_name,
                min=fv_minmax.min,
                max=fv_minmax.max,
                min_flex=fv_minmax.min_flex,
                max_flex=fv_minmax.max_flex,
                percentage_target=_parse_percentage(extras.get(VALUE_PERCENTAGE_COLUMN, ""), feature_name, value_name),
                comment=extras.get(VALUE_COMMENT_COLUMN, ""),
                minmax_manual=True,
            )
            category.add_value(target_val)

        _fill_missing_percentages(category, assembly.number_to_select)

        uow.target_categories.add(category)
        categories.append(category)

    return TargetImportResult(
        categories=[c.create_detached_copy() for c in categories],
        warnings=warnings,
    )


def _fill_missing_percentages(category: TargetCategory, number_to_select: int) -> None:
    """Derive percentages for imported values that did not carry one.

    With a seat count, use midpoint/number_to_select - deliberately the same
    formula the selection report uses, so an imported percentage and the report
    agree by construction, and a CSV whose midpoints do not sum to the assembly
    size still trips the sum-to-100 warning.

    Without one, normalise within the category instead, which needs no seat count
    but always totals 100 and so can never trip that warning.
    """
    missing = [v for v in category.values if v.percentage_target is None]
    if not missing:
        return

    if number_to_select > 0:
        for target_value in missing:
            target_value.percentage_target = round(
                (target_value.min + target_value.max) / 2 / number_to_select * 100, 1
            )
        return

    denominator = sum(v.min + v.max for v in category.values)
    if denominator == 0:
        return
    for target_value in missing:
        target_value.percentage_target = round((target_value.min + target_value.max) / denominator * 100, 1)


def update_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str,
    comment: str = "",
    source_url: str = "",
) -> TargetCategory:
    """Update a target category's name, comment and source URL.

    An invalid `source_url` raises ValueError from the domain; the route turns
    that into a field error rather than a 500.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="update target category",
            required_role="assembly-manager, global-organiser or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    category.name = name.strip()
    category.comment = validate_comment(comment)
    category.source_url = validate_source_url(source_url)
    category.updated_at = datetime.now(UTC)

    return category.create_detached_copy()


def delete_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
) -> None:
    """Delete a target category.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="delete target category",
            required_role="assembly-manager, global-organiser or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    uow.target_categories.delete(category)


def add_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value: str,
    min_count: int = 0,
    max_count: int = 0,
    percentage: float | None = None,
    comment: str = "",
) -> TargetCategory:
    """Add a value to a target category. Returns the updated category.

    A percentage drives min/max on construction; explicit min/max without a
    percentage are left exactly as given.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="add target value",
            required_role="assembly-manager, global-organiser or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    target_val = TargetValue(
        value=value,
        min=min_count,
        max=max_count,
        percentage_target=percentage,
        comment=comment,
    )
    target_val.apply_percentage(assembly.number_to_select if assembly else 0)
    category.add_value(target_val)
    flag_modified(category, "values")

    return category.create_detached_copy()


def update_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
    value: str,
    min_count: int | None = None,
    max_count: int | None = None,
    percentage: float | None = UNSET,
    comment: str | None = None,
) -> TargetCategory:
    """Update a value within a target category. Returns the updated category.

    Every optional parameter means "not submitted, leave alone" when omitted.
    `percentage` uses the UNSET sentinel rather than None, because a submitted
    None legitimately means "clear the percentage".

    The rules that matter:

    - min/max supplied and *different* from the stored values breaks the
      auto-calculate link, via `set_manual_min_max`.
    - min/max supplied and *identical* to the stored values changes nothing and
      does **not** break the link. Without this a bulk save that round-trips
      every field would break every link in the assembly on first use.
    - A percentage is applied first, so an explicit min/max in the same
      submission wins and breaks the link.
    - Clearing the percentage leaves min/max and `minmax_manual` alone.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="update target value",
            required_role="assembly-manager, global-organiser or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    existing = _get_value(category, value_id)

    if value != existing.value and any(v.value == value for v in category.values):
        raise ValueError(f"Value '{value}' already exists in category '{category.name}'")

    assembly = uow.assemblies.get(assembly_id)
    number_to_select = assembly.number_to_select if assembly else 0

    existing.value = value.strip()
    if comment is not None:
        existing.comment = comment
    _apply_value_numbers(existing, min_count, max_count, percentage, number_to_select)
    existing._validate()
    category.updated_at = datetime.now(UTC)
    flag_modified(category, "values")

    return category.create_detached_copy()


def _apply_value_numbers(
    target_value: TargetValue,
    min_count: int | None,
    max_count: int | None,
    percentage: float | None,
    number_to_select: int,
) -> None:
    """Apply a submitted percentage and min/max to one value, in that order.

    Shared by `update_target_value` and `save_all_targets` so there is exactly
    one implementation of the link-breaking rules.
    """
    # Captured before the percentage is applied. Comparing against the
    # recalculated numbers instead would break the link every time a form
    # round-tripped the min/max it had displayed, which is the whole thing the
    # "identical means leave it alone" rule exists to prevent.
    submitted_against = (target_value.min, target_value.max)

    if percentage is not UNSET:
        target_value.percentage_target = percentage
        target_value.apply_percentage(number_to_select)

    if min_count is None and max_count is None:
        return

    new_min = submitted_against[0] if min_count is None else min_count
    new_max = submitted_against[1] if max_count is None else max_count
    if (new_min, new_max) != submitted_against:
        target_value.set_manual_min_max(new_min, new_max)


def delete_target_value(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
) -> TargetCategory:
    """Delete a value from a target category. Returns the updated category.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="delete target value",
            required_role="assembly-manager, global-organiser or admin",
        )

    category = cast("TargetCategory | None", uow.target_categories.get(category_id))
    if not category or category.assembly_id != assembly_id:
        raise NotFoundError(f"Target category {category_id} not found")

    if not category.remove_value(value_id):
        raise NotFoundError(f"Target value {value_id} not found")
    flag_modified(category, "values")

    return category.create_detached_copy()


def get_feature_collection_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> tuple[FeatureCollection, str]:
    """
    Load target categories as FeatureCollection using sortition-algorithms.
    Used internally for selection operations.

    Returns: (FeatureCollection, report_text)

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(
            action="get feature collection",
            required_role="assembly role or global privileges",
        )

    # Use SelectionData with our custom adapter
    adapter = OpenDLPDataAdapter(uow, assembly_id)
    select_data = SelectionData(adapter)

    # Load features using sortition-algorithms
    features, report = select_data.load_features(assembly.number_to_select)

    return features, report.as_text()


def delete_targets_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> int:
    """Delete all target categories for an assembly.

    Returns the number of categories deleted.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="delete targets",
            required_role="assembly-manager, global-organiser or admin",
        )

    return uow.target_categories.delete_all_for_assembly(assembly_id)


def reorder_target_categories(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    ordered_category_ids: list[uuid.UUID],
) -> None:
    """Re-issue sort_order for every target category in an assembly.

    ``ordered_category_ids`` must contain all category ids currently on the
    assembly, in the desired display order. Requiring the complete set stops a
    stale page silently dropping a category from the ordering.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _load_user_and_assembly(uow, user_id, assembly_id, "reorder target categories")

    existing = uow.target_categories.get_by_assembly_id(assembly_id)
    existing_by_id = {c.id: c for c in existing}
    if set(ordered_category_ids) != set(existing_by_id.keys()):
        raise ValueError("reorder_target_categories requires the complete set of category ids for the assembly")

    now = datetime.now(UTC)
    for i, category_id in enumerate(ordered_category_ids, start=1):
        category = existing_by_id[category_id]
        category.sort_order = i * SORT_ORDER_STEP
        category.updated_at = now


def set_target_value_percentage(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
    percentage: float | None,
) -> TargetCategory:
    """Set a value's percentage and recalculate its min/max.

    The recalculation no-ops if the auto-calculate link has been broken.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = _load_user_and_assembly(uow, user_id, assembly_id, "set target percentage")
    category = _get_category(uow, assembly_id, category_id)
    target_value = _get_value(category, value_id)

    target_value.percentage_target = percentage
    target_value.apply_percentage(assembly.number_to_select)
    target_value._validate()
    category.updated_at = datetime.now(UTC)
    flag_modified(category, "values")

    return category.create_detached_copy()


def relink_target_value_to_percentage(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    value_id: uuid.UUID,
) -> TargetCategory:
    """Restore auto-calculation for one value and recalculate it now.

    Refuses when the value has no percentage: re-linking is meaningless without
    one, and silently clearing the flag would leave a value claiming to be
    linked while showing hand-typed numbers.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = _load_user_and_assembly(uow, user_id, assembly_id, "relink target value")
    category = _get_category(uow, assembly_id, category_id)
    target_value = _get_value(category, value_id)

    target_value.relink_to_percentage(assembly.number_to_select)
    category.updated_at = datetime.now(UTC)
    flag_modified(category, "values")

    return category.create_detached_copy()


def recalculate_minmax_for_assembly(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
) -> list[TargetValueChange]:
    """Re-derive min/max for every value with an intact auto-calculate link.

    Returns the values that moved, with their old and new min/max. No permission
    check: this is an internal consequence of an already-authorised change, not a
    user action.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    changes: list[TargetValueChange] = []
    for category in uow.target_categories.get_by_assembly_id(assembly_id):
        touched = False
        for target_value in category.values:
            old_min, old_max = target_value.min, target_value.max
            if not target_value.apply_percentage(assembly.number_to_select):
                continue
            touched = True
            changes.append(
                TargetValueChange(
                    category_id=category.id,
                    value_id=cast("uuid.UUID", target_value.value_id),
                    value=target_value.value,
                    old_min=old_min,
                    old_max=old_max,
                    new_min=target_value.min,
                    new_max=target_value.max,
                )
            )
        if touched:
            category.updated_at = datetime.now(UTC)
            flag_modified(category, "values")

    return changes


def save_all_targets(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    edits: list[TargetCategoryEdit],
) -> list[TargetCategory]:
    """Apply edits to many categories and values in one operation.

    One permission check, one pass, all-or-nothing - the entrypoint's single
    `with uow:` provides the transaction, so if any edit raises nothing commits.
    Reuses the per-value logic from `update_target_value`, so the link-breaking
    rules have exactly one implementation.

    Deletion is explicit: a category or value goes only when its edit says so.
    Absence from the payload still means "leave alone", so a partial submission
    cannot silently destroy anything.

    An edit with no `category_id` creates a category. Unlike
    `create_target_category` this does not auto-populate values from a matching
    respondent column: the user is looking at the form where they would add them,
    and rows appearing under a name they had just typed would be a surprise.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = _load_user_and_assembly(uow, user_id, assembly_id, "save targets")
    number_to_select = assembly.number_to_select
    naming = _CategoryNaming(uow, assembly_id, edits)

    saved = []
    now = datetime.now(UTC)
    for category_edit in edits:
        if category_edit.deleted:
            if category_edit.category_id is not None:
                uow.target_categories.delete(_get_category(uow, assembly_id, category_edit.category_id))
            continue

        naming.claim(category_edit.name, category_edit.category_id)
        is_new = category_edit.category_id is None
        if is_new:
            category = TargetCategory(
                assembly_id=assembly_id,
                name=category_edit.name.strip(),
                sort_order=naming.next_sort_order(),
            )
            uow.target_categories.add(category)
        else:
            category = _get_category(uow, assembly_id, cast("uuid.UUID", category_edit.category_id))

        _apply_category_edit(category, category_edit, number_to_select)
        category.updated_at = now
        if not is_new:
            # A category being inserted has no stored JSON to mark dirty.
            flag_modified(category, "values")
        saved.append(category.create_detached_copy())

    return saved


class _CategoryNaming:
    """Guards category names and hands out sort orders during a bulk save.

    `(assembly_id, name)` carries a unique index, so a clash is a database error
    rather than a mistake we can shrug at. Checking here turns it into a
    `ValueError` the route can flash.

    A name in use at the start of the save stays claimed for its own category
    even when this save deletes or renames it away. Freeing it properly would
    mean flushing the deletes before the inserts, and SQLAlchemy orders an INSERT
    ahead of the DELETE that would make room for it. So deleting "Gender" and
    adding a new "Gender" in one go is refused; do it in two saves.
    """

    def __init__(
        self,
        uow: AbstractUnitOfWork,
        assembly_id: uuid.UUID,
        edits: list[TargetCategoryEdit],
    ) -> None:
        existing = uow.target_categories.get_by_assembly_id(assembly_id)
        self._taken = {c.name.strip().lower() for c in existing}
        self._own: dict[uuid.UUID | None, str] = {c.id: c.name.strip().lower() for c in existing}
        self._next = max((c.sort_order for c in existing), default=0) + SORT_ORDER_STEP

    def claim(self, name: str, category_id: uuid.UUID | None) -> None:
        """Reserve a name, refusing one that belongs to a different category."""
        key = name.strip().lower()
        if key in self._taken and key != self._own.get(category_id):
            raise ValueError(f"A category named '{name.strip()}' already exists")
        self._taken.add(key)

    def next_sort_order(self) -> int:
        """The next free sort order, placing new categories after the existing ones."""
        value = self._next
        self._next += SORT_ORDER_STEP
        return value


def _apply_category_edit(
    category: TargetCategory,
    category_edit: TargetCategoryEdit,
    number_to_select: int,
) -> None:
    """Apply one category's own fields and every value edit beneath it."""
    category.name = category_edit.name.strip()
    category.comment = validate_comment(category_edit.comment)
    category.source_url = validate_source_url(category_edit.source_url)
    if category_edit.sort_order is not None:
        category.sort_order = category_edit.sort_order

    for value_edit in category_edit.values:
        _apply_value_edit(category, value_edit, number_to_select)


def _apply_value_edit(
    category: TargetCategory,
    value_edit: TargetValueEdit,
    number_to_select: int,
) -> None:
    """Add, update or remove one value, per its edit."""
    if value_edit.value_id is None:
        if value_edit.deleted:
            return
        target_value = TargetValue(
            value=value_edit.value,
            min=value_edit.min or 0,
            max=value_edit.max or 0,
            percentage_target=value_edit.percentage,
            comment=value_edit.comment,
        )
        target_value.apply_percentage(number_to_select)
        category.add_value(target_value)
        return

    if value_edit.deleted:
        category.remove_value(value_edit.value_id)
        return

    target_value = _get_value(category, value_edit.value_id)
    target_value.value = value_edit.value.strip()
    target_value.comment = value_edit.comment
    if value_edit.relink:
        target_value.percentage_target = value_edit.percentage
        target_value.relink_to_percentage(number_to_select)
    else:
        _apply_value_numbers(
            target_value,
            value_edit.min,
            value_edit.max,
            value_edit.percentage,
            number_to_select,
        )
    target_value._validate()
