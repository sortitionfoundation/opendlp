"""ABOUTME: Target category and value service layer for stratified selection quotas
ABOUTME: Provides CRUD, CSV import and percentage-driven min/max for assembly targets"""

import csv as csv_module
import uuid
from datetime import UTC, datetime
from io import StringIO
from typing import cast

from sortition_algorithms.adapters import SelectionData
from sortition_algorithms.features import MAX_FLEX_UNSET, FeatureCollection, read_in_features
from sqlalchemy.orm.attributes import flag_modified

from opendlp.adapters.sortition_data_adapter import OpenDLPDataAdapter
from opendlp.domain.targets import TargetCategory, TargetValue

from .constants import MAX_DISTINCT_VALUES_FOR_AUTO_ADD
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


def create_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    name: str,
    description: str = "",
    sort_order: int = 0,
) -> TargetCategory:
    """Create a new target category for an assembly.

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

    category = TargetCategory(
        assembly_id=assembly_id,
        name=name,
        description=description,
        sort_order=sort_order,
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


def import_targets_from_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    csv_content: str,
    replace_existing: bool = False,
) -> list[TargetCategory]:
    """
    Import target categories from CSV using sortition-algorithms library.

    CSV format matches sortition-algorithms feature files with columns:
    feature, value, min, max, min_flex, max_flex

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
            action="import targets",
            required_role="assembly-manager, global-organiser or admin",
        )

    # Parse and validate CSV using sortition-algorithms
    # Note: read_in_features() already calls set_default_max_flex() and check_min_max()
    csv_file = StringIO(csv_content)
    reader = csv_module.DictReader(csv_file)

    if not reader.fieldnames:
        raise InvalidSelection("CSV file is empty or malformed")

    headers = list(reader.fieldnames)
    body = list(reader)

    try:
        feature_collection, _, __ = read_in_features(headers, body)
    except Exception as e:
        raise InvalidSelection(f"Failed to parse CSV: {e!s}") from e

    # Replace existing if requested
    if replace_existing:
        uow.target_categories.delete_all_for_assembly(assembly_id)

    # Convert to TargetCategory objects
    categories = []
    for idx, (feature_name, feature_values) in enumerate(feature_collection.items()):
        category = TargetCategory(
            assembly_id=assembly_id,
            name=feature_name,
            description="",
            sort_order=idx,
        )

        # Add target values
        for value_name, fv_minmax in feature_values.items():
            target_val = TargetValue(
                value=value_name,
                min=fv_minmax.min,
                max=fv_minmax.max,
                min_flex=fv_minmax.min_flex,
                max_flex=fv_minmax.max_flex,
            )
            category.add_value(target_val)

        uow.target_categories.add(category)
        categories.append(category)

    return [c.create_detached_copy() for c in categories]


def update_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    category_id: uuid.UUID,
    name: str,
    description: str = "",
) -> TargetCategory:
    """Update a target category's name and description.

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
    category.description = description.strip()
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
    min_count: int,
    max_count: int,
) -> TargetCategory:
    """Add a value to a target category. Returns the updated category.

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

    target_val = TargetValue(value=value, min=min_count, max=max_count)
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
    min_count: int,
    max_count: int,
) -> TargetCategory:
    """Update a value within a target category. Returns the updated category.

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

    existing = next((v for v in category.values if v.value_id == value_id), None)
    if not existing:
        raise NotFoundError(f"Target value {value_id} not found")

    if value != existing.value and any(v.value == value for v in category.values):
        raise ValueError(f"Value '{value}' already exists in category '{category.name}'")

    existing.value = value.strip()
    existing.min = min_count
    existing.max = max_count
    # Reset flex values since the form doesn't expose them;
    # the sortition library recalculates safe defaults at selection time
    existing.min_flex = 0
    existing.max_flex = MAX_FLEX_UNSET
    existing._validate()
    category.updated_at = datetime.now(UTC)
    flag_modified(category, "values")

    return category.create_detached_copy()


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
