"""ABOUTME: Assembly management service layer for handling assembly operations
ABOUTME: Provides functions for assembly creation, updates, permissions, and lifecycle management"""

import csv as csv_module
import uuid
from datetime import UTC, date, datetime
from io import StringIO
from typing import Any, cast

from sortition_algorithms.adapters import SelectionData
from sortition_algorithms.features import FeatureCollection, read_in_features

from opendlp.adapters.sortition_data_adapter import OpenDLPDataAdapter
from opendlp.domain.assembly import VALID_TEAMS, Assembly, AssemblyGSheet, Teams
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import AssemblyStatus

from .exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    UserNotFoundError,
)
from .permissions import can_manage_assembly, can_view_assembly, has_global_organiser
from .unit_of_work import AbstractUnitOfWork
from .user_service import get_user_assemblies


def create_assembly(
    uow: AbstractUnitOfWork,
    title: str,
    created_by_user_id: uuid.UUID,
    question: str = "",
    first_assembly_date: date | None = None,
    number_to_select: int = 0,
) -> Assembly:
    """
    Create a new assembly.

    Args:
        uow: Unit of Work for database operations
        title: Assembly title (required)
        created_by_user_id: ID of user creating the assembly
        question: Assembly question (optional, defaults to empty string)
        first_assembly_date: Date of first assembly meeting (optional)
        number_to_select: Number of participants to select (optional)

    Returns:
        Created Assembly instance

    Raises:
        InsufficientPermissions: If user cannot create assemblies
        UserNotFoundError: If user not found or invalid data
    """
    with uow:
        user = uow.users.get(created_by_user_id)
        if not user:
            raise UserNotFoundError(f"User {created_by_user_id} not found")

        # Check permissions - only global organisers and admins can create assemblies
        if not has_global_organiser(user):
            raise InsufficientPermissions(action="create assembly", required_role="global-organiser or admin")

        # Create the assembly
        assembly = Assembly(
            title=title,
            question=question,
            first_assembly_date=first_assembly_date,
            number_to_select=number_to_select,
        )

        uow.assemblies.add(assembly)
        uow.commit()
        detached_assembly = assembly.create_detached_copy()
        return detached_assembly


def update_assembly(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
    **updates: Any,
) -> Assembly:
    """
    Update an assembly with new data.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to update
        user_id: ID of user performing the update

    Returns:
        Updated Assembly instance

    Raises:
        UserNotFoundError, AssemblyNotFoundError: If assembly or user not found
        InsufficientPermissions: If user cannot manage this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="update assembly", required_role="assembly-manager, global-organiser or admin"
            )

        # Apply updates
        for field, value in updates.items():
            if hasattr(assembly, field):
                setattr(assembly, field, value)

        uow.commit()
        # Explicit typing to satisfy mypy
        updated_assembly: Assembly = assembly
        return updated_assembly


def get_assembly_with_permissions(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Assembly:
    """
    Get an assembly if user has permission to view it.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to retrieve
        user_id: ID of user requesting the assembly

    Returns:
        Assembly instance

    Raises:
        NotFoundError: If assembly or user not found
        InsufficientPermissions: If user cannot view this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view assembly", required_role="assembly role or global privileges")

        # Explicit typing to satisfy mypy
        retrieved_assembly: Assembly = assembly.create_detached_copy()
        return retrieved_assembly


def archive_assembly(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Assembly:
    """
    Archive an assembly.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to archive
        user_id: ID of user performing the archival

    Returns:
        Archived Assembly instance

    Raises:
        NotFoundError: If assembly or user not found
        InsufficientPermissions: If user cannot manage this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="archive assembly", required_role="assembly-manager, global-organiser or admin"
            )

        # Archive the assembly
        assembly.status = AssemblyStatus.ARCHIVED

        uow.commit()
        # Explicit typing to satisfy mypy
        archived_assembly: Assembly = assembly
        return archived_assembly


def get_user_accessible_assemblies(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
) -> list[Assembly]:
    """
    Get all assemblies that a user has access to.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of user to get assemblies for

    Returns:
        List of assemblies user can access

    Raises:
        UserNotFoundError: If user not found
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        # Use existing user_service function for consistency

        return get_user_assemblies(uow, user_id)


def add_assembly_gsheet(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
    url: str,
    team: str = "other",
    **gsheet_options: Any,
) -> AssemblyGSheet:
    """
    Add a Google Spreadsheet configuration to an assembly.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to add the gsheet to
        user_id: ID of user performing the operation
        url: Google Spreadsheet URL
        team: Team configuration to use (uk, eu, aus)
        **gsheet_options: Additional options to override team defaults

    Returns:
        Created AssemblyGSheet instance

    Raises:
        UserNotFoundError: If user not found
        AssemblyNotFoundError: If assembly not found
        InsufficientPermissions: If user cannot manage this assembly
        ValueError: If assembly already has a gsheet
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="add gsheet to assembly", required_role="assembly-manager, global-organiser or admin"
            )

        # Check if assembly already has a gsheet
        existing_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
        if existing_gsheet:
            raise ValueError(f"Assembly {assembly_id} already has a Google Spreadsheet configuration")

        # Create the AssemblyGSheet with team defaults
        assembly_gsheet = AssemblyGSheet(
            assembly_id=assembly_id, url=url, **AssemblyGSheet.convert_str_kwargs(**gsheet_options)
        )
        if team in VALID_TEAMS:
            assembly_gsheet.update_team_settings(cast(Teams, team))

        uow.assembly_gsheets.add(assembly_gsheet)
        uow.commit()

        return assembly_gsheet.create_detached_copy()


def update_assembly_gsheet(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
    **updates: Any,
) -> AssemblyGSheet:
    """
    Update a Google Spreadsheet configuration for an assembly.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly whose gsheet to update
        user_id: ID of user performing the operation
        **updates: Fields to update

    Returns:
        Updated AssemblyGSheet instance

    Raises:
        UserNotFoundError: If user not found
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet not found
        InsufficientPermissions: If user cannot manage this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="update assembly gsheet", required_role="assembly-manager, global-organiser or admin"
            )

        # Get the existing gsheet
        assembly_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
        if not assembly_gsheet:
            raise GoogleSheetConfigNotFoundError(
                f"Assembly {assembly_id} does not have a Google Spreadsheet configuration"
            )

        # Apply updates
        assembly_gsheet.update_values(**AssemblyGSheet.convert_str_kwargs(**updates))

        uow.commit()

        return assembly_gsheet.create_detached_copy()


def remove_assembly_gsheet(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """
    Remove a Google Spreadsheet configuration from an assembly.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to remove gsheet from
        user_id: ID of user performing the operation

    Raises:
        UserNotFoundError: If user not found
        AssemblyNotFoundError: If assembly not found
        GoogleSheetConfigNotFoundError: If gsheet not found
        InsufficientPermissions: If user cannot manage this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="remove assembly gsheet", required_role="assembly-manager, global-organiser or admin"
            )

        # Get the existing gsheet
        assembly_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
        if not assembly_gsheet:
            raise GoogleSheetConfigNotFoundError(
                f"Assembly {assembly_id} does not have a Google Spreadsheet configuration"
            )

        uow.assembly_gsheets.delete(assembly_gsheet)
        uow.commit()


def get_assembly_gsheet(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AssemblyGSheet | None:
    """
    Get the Google Spreadsheet configuration for an assembly.

    Args:
        uow: Unit of Work for database operations
        assembly_id: ID of assembly to get gsheet for
        user_id: ID of user requesting the gsheet

    Returns:
        AssemblyGSheet instance or None if not found

    Raises:
        UserNotFoundError: If user not found
        AssemblyNotFoundError: If assembly not found
        InsufficientPermissions: If user cannot view this assembly
    """
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        # Check permissions
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(
                action="view assembly gsheet", required_role="assembly role or global privileges"
            )

        # Get the gsheet
        assembly_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
        if assembly_gsheet:
            return assembly_gsheet.create_detached_copy()

        return None


def create_target_category(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    name: str,
    description: str = "",
    sort_order: int = 0,
) -> TargetCategory:
    """Create a new target category for an assembly."""
    with uow:
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

        category = TargetCategory(
            assembly_id=assembly_id,
            name=name,
            description=description,
            sort_order=sort_order,
        )

        uow.target_categories.add(category)
        uow.commit()
        return category.create_detached_copy()


def get_targets_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> list[TargetCategory]:
    """Get all target categories for an assembly."""
    with uow:
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
    """
    with uow:
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
            feature_collection, _, __ = read_in_features(headers, body, assembly.number_to_select)
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

        uow.commit()
        return [c.create_detached_copy() for c in categories]


def get_feature_collection_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> tuple[FeatureCollection, str]:
    """
    Load target categories as FeatureCollection using sortition-algorithms.
    Used internally for selection operations.

    Returns: (FeatureCollection, report_text)
    """
    with uow:
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


def get_or_create_csv_config(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> AssemblyCSV:
    """Get or create CSV configuration for an assembly."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(
                action="view CSV configuration",
                required_role="assembly role or global privileges",
            )

        # Create default config if doesn't exist
        if assembly.csv is None:
            assembly.csv = AssemblyCSV(assembly_id=assembly_id)
            uow.commit()

        csv_config = cast(AssemblyCSV, assembly.csv)
        return csv_config.create_detached_copy()


def update_csv_config(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    **settings: Any,
) -> AssemblyCSV:
    """Update CSV configuration for an assembly."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="update CSV configuration",
                required_role="assembly-manager, global-organiser or admin",
            )

        # Create if doesn't exist
        if assembly.csv is None:
            assembly.csv = AssemblyCSV(assembly_id=assembly_id)

        # Update settings
        csv_config = cast(AssemblyCSV, assembly.csv)
        for key, value in settings.items():
            if hasattr(csv_config, key):
                setattr(csv_config, key, value)

        csv_config.updated_at = datetime.now(UTC)
        uow.commit()

        return csv_config.create_detached_copy()
