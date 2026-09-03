"""ABOUTME: Assembly management service layer for handling assembly operations
ABOUTME: Provides functions for assembly creation, updates, permissions, and lifecycle management"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, cast

from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.selection_settings import (
    DEFAULT_ADDRESS_COLS,
    DEFAULT_COLS_TO_KEEP,
    DEFAULT_ID_COLUMN,
    OTHER_TEAM,
    VALID_TEAMS,
    SelectionSettings,
    Teams,
)
from opendlp.domain.value_objects import AssemblyStatus

from . import target_service
from .exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InsufficientPermissions,
    UserNotFoundError,
)
from .permissions import can_create_assembly, can_manage_assembly, can_view_assembly
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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(created_by_user_id)
    if not user:
        raise UserNotFoundError(f"User {created_by_user_id} not found")

    if not can_create_assembly(user):
        raise InsufficientPermissions(action="create assembly", required_role="organiser or admin")

    # Create the assembly
    assembly = Assembly(
        title=title,
        question=question,
        first_assembly_date=first_assembly_date,
        number_to_select=number_to_select,
    )

    uow.assemblies.add(assembly)
    return assembly.create_detached_copy()


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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
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
    previous_number_to_select = assembly.number_to_select
    for field, value in updates.items():
        if hasattr(assembly, field):
            setattr(assembly, field, value)

    # Targets whose min/max are derived from a percentage depend on the seat
    # count, so they have to move with it. This is the single funnel for both the
    # assembly edit form and the dedicated update_number_to_select route.
    if assembly.number_to_select != previous_number_to_select:
        target_service.recalculate_minmax_for_assembly(uow, assembly_id)

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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
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

    # Split options into gsheet-specific and selection settings
    sel_kwargs, gsheet_kwargs = _split_select_gsheet_kwargs(**gsheet_options)

    assembly_gsheet = AssemblyGSheet(assembly_id=assembly_id, url=url, **gsheet_kwargs)
    uow.assembly_gsheets.add(assembly_gsheet)

    # Create or update SelectionSettings
    sel_settings = assembly.selection_settings or SelectionSettings(assembly_id=assembly_id)
    sel_settings.update_from_str_kwargs(**sel_kwargs)
    if team in VALID_TEAMS:
        _apply_team_defaults(sel_settings, cast("Teams", team))
    assembly.selection_settings = sel_settings

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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
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
        raise GoogleSheetConfigNotFoundError(f"Assembly {assembly_id} does not have a Google Spreadsheet configuration")

    # Split updates into gsheet-specific and selection settings
    sel_kwargs, gsheet_kwargs = _split_select_gsheet_kwargs(**updates)

    # Apply gsheet-specific updates
    team = gsheet_kwargs.pop("team", OTHER_TEAM)
    assembly_gsheet.update_values(**gsheet_kwargs)

    # Apply selection settings updates
    sel_settings = assembly.selection_settings or SelectionSettings(assembly_id=assembly_id)
    sel_settings.update_from_str_kwargs(**sel_kwargs)
    if team in VALID_TEAMS:
        _apply_team_defaults(sel_settings, cast("Teams", team))
    assembly.selection_settings = sel_settings

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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
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
        raise GoogleSheetConfigNotFoundError(f"Assembly {assembly_id} does not have a Google Spreadsheet configuration")

    uow.assembly_gsheets.delete(assembly_gsheet)


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

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    # Check permissions
    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(action="view assembly gsheet", required_role="assembly role or global privileges")

    # Get the gsheet
    assembly_gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly_id)
    if assembly_gsheet:
        return assembly_gsheet.create_detached_copy()

    return None


def _apply_team_defaults(sel_settings: SelectionSettings, team: Teams) -> None:
    """Apply team-specific defaults to selection settings."""
    if team != OTHER_TEAM:
        sel_settings.id_column = DEFAULT_ID_COLUMN[team]
        sel_settings.check_same_address_cols = DEFAULT_ADDRESS_COLS[team]
        sel_settings.columns_to_keep = DEFAULT_COLS_TO_KEEP[team]


def _split_select_gsheet_kwargs(**kwargs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split options into gsheet-specific and selection settings"""
    selection_fields = {
        "id_column",
        "check_same_address",
        "check_same_address_cols",
        "columns_to_keep",
        "selection_algorithm",
        "check_same_address_cols_string",
        "columns_to_keep_string",
    }
    sel_kwargs = {k: v for k, v in kwargs.items() if k in selection_fields}
    gsheet_kwargs = {k: v for k, v in kwargs.items() if k not in selection_fields}
    return sel_kwargs, gsheet_kwargs


def get_or_create_selection_settings(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> SelectionSettings:
    """Get or create selection settings for an assembly.

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
            action="view selection settings",
            required_role="assembly role or global privileges",
        )

    if assembly.selection_settings is None:
        assembly.selection_settings = SelectionSettings(assembly_id=assembly_id)
        uow.commit()

    return cast("SelectionSettings", assembly.selection_settings).create_detached_copy()


def update_selection_settings(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    **settings: Any,
) -> SelectionSettings:
    """Update selection settings for an assembly.

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
            action="update selection settings",
            required_role="assembly-manager, global-organiser or admin",
        )

    if assembly.selection_settings is None:
        assembly.selection_settings = SelectionSettings(assembly_id=assembly_id)

    sel_settings = cast("SelectionSettings", assembly.selection_settings)
    for key, value in settings.items():
        if hasattr(sel_settings, key):
            setattr(sel_settings, key, value)

    return sel_settings.create_detached_copy()


def get_or_create_csv_config(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> AssemblyCSV:
    """Get or create CSV configuration for an assembly.

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
            action="view CSV configuration",
            required_role="assembly role or global privileges",
        )

    # Create default config if doesn't exist
    if assembly.csv is None:
        assembly.csv = AssemblyCSV(assembly_id=assembly_id)
        uow.commit()

    csv_config = cast("AssemblyCSV", assembly.csv)
    return csv_config.create_detached_copy()


def update_csv_config(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    **settings: Any,
) -> AssemblyCSV:
    """Update CSV configuration for an assembly.

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
            action="update CSV configuration",
            required_role="assembly-manager, global-organiser or admin",
        )

    # Create if doesn't exist
    if assembly.csv is None:
        assembly.csv = AssemblyCSV(assembly_id=assembly_id)

    # Update settings
    csv_config = cast("AssemblyCSV", assembly.csv)
    for key, value in settings.items():
        if hasattr(csv_config, key):
            setattr(csv_config, key, value)

    csv_config.updated_at = datetime.now(UTC)

    return csv_config.create_detached_copy()


@dataclass(kw_only=True)
class CSVUploadStatus:
    targets_count: int
    respondents_count: int
    csv_config: AssemblyCSV | None

    @property
    def has_targets(self) -> bool:
        return self.targets_count > 0

    @property
    def has_respondents(self) -> bool:
        return self.respondents_count > 0

    @property
    def has_data(self) -> bool:
        return self.respondents_count > 0 or self.targets_count > 0

    @property
    def selection_enabled(self) -> bool:
        return self.respondents_count > 0 and self.targets_count > 0


VALID_DATA_SOURCES = ("gsheet", "csv", "")


def determine_data_source(
    gsheet: AssemblyGSheet | None,
    csv_status: CSVUploadStatus | None,
    preferred_source: str = "",
) -> tuple[str, bool]:
    """Determine the active data source for an assembly and whether it is locked.

    Once an assembly has a gsheet config or CSV data, that source is locked in.
    Before any data exists the caller may express a preference (typically from
    a ?source= query parameter), which is returned unlocked so the UI can
    offer the other options.

    Returns:
        Tuple of (data_source, locked). data_source is one of "gsheet", "csv",
        or "" (no source chosen yet). locked indicates whether the source is
        fixed by existing data.
    """
    if gsheet:
        return "gsheet", True
    if csv_status and csv_status.has_data:
        return "csv", True
    if preferred_source not in VALID_DATA_SOURCES:
        preferred_source = ""
    return preferred_source, False


def get_tab_enabled_states(
    data_source: str,
    gsheet: AssemblyGSheet | None,
    csv_status: CSVUploadStatus | None,
) -> tuple[bool, bool, bool]:
    """Return which of the (targets, respondents, selection) tabs are enabled."""
    if data_source == "gsheet":
        enabled = gsheet is not None
        return enabled, enabled, enabled
    if data_source == "csv" and csv_status:
        # targets is always enabled, as you can create from blank in the targets tab
        return True, csv_status.has_respondents, csv_status.selection_enabled
    return False, False, False


def get_csv_upload_status(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> CSVUploadStatus:
    """Get CSV upload status for an assembly.

    Returns a dict with:
        - has_targets: bool - whether any targets have been uploaded
        - targets_count: int - number of target categories
        - has_respondents: bool - whether any respondents have been uploaded
        - respondents_count: int - number of respondents
        - csv_config: AssemblyCSV | None - the CSV config if exists

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
            action="view CSV upload status",
            required_role="assembly role or global privileges",
        )

    # Get targets count
    targets = uow.target_categories.get_by_assembly_id(assembly_id)
    targets_count = len(targets)

    # Get respondents count
    respondents = uow.respondents.get_by_assembly_id(assembly_id)
    respondents_count = len(respondents)

    # Get CSV config if exists
    csv_config = assembly.csv.create_detached_copy() if assembly.csv else None

    return CSVUploadStatus(
        targets_count=targets_count,
        respondents_count=respondents_count,
        csv_config=csv_config,
    )


@dataclass(kw_only=True)
class AssemblyNavContext:
    """Everything the backoffice navigation shell needs for an assembly page.

    Bundles the assembly with the derived data-source selection and the
    targets/respondents/selection tab enablement so routes do not need to
    re-run the same loading and wiring logic.
    """

    assembly: Assembly
    gsheet: AssemblyGSheet | None
    csv_status: CSVUploadStatus
    data_source: str
    data_source_locked: bool
    targets_enabled: bool
    respondents_enabled: bool
    selection_enabled: bool


def get_assembly_nav_context(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    preferred_source: str = "",
) -> AssemblyNavContext:
    """Load an assembly along with everything the backoffice nav shell needs.

    Raises the same exceptions as the wrapped service functions:
    UserNotFoundError, AssemblyNotFoundError, InsufficientPermissions.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    assembly = get_assembly_with_permissions(uow, assembly_id, user_id)
    gsheet = get_assembly_gsheet(uow, assembly_id, user_id)
    csv_status = get_csv_upload_status(uow, user_id, assembly_id)
    data_source, locked = determine_data_source(gsheet, csv_status, preferred_source)
    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)
    return AssemblyNavContext(
        assembly=assembly,
        gsheet=gsheet,
        csv_status=csv_status,
        data_source=data_source,
        data_source_locked=locked,
        targets_enabled=targets_enabled,
        respondents_enabled=respondents_enabled,
        selection_enabled=selection_enabled,
    )


def delete_respondents_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> int:
    """Delete all respondents for an assembly.

    Returns the number of respondents deleted.

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
            action="delete respondents",
            required_role="assembly-manager, global-organiser or admin",
        )

    return uow.respondents.delete_all_for_assembly(assembly_id)
