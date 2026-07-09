"""ABOUTME: Respondent management service layer for participant pool operations
ABOUTME: Provides functions for respondent creation, CSV import, and validation"""

import csv
import uuid
from io import StringIO
from typing import Any

from opendlp.domain.respondents import _UNSET as _RESPONDENT_UNSET
from opendlp.domain.respondents import Respondent, normalise_field_name, pop_normalised
from opendlp.domain.users import User
from opendlp.domain.value_objects import (
    ALLOWED_SELECTION_STATUS_TRANSITIONS,
    RespondentAction,
    RespondentSourceType,
    RespondentStatus,
)
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    RespondentNotFoundError,
    UserNotFoundError,
)
from opendlp.service_layer.permissions import (
    can_call_confirmations,
    can_edit_respondent,
    can_manage_assembly,
    can_view_assembly,
)
from opendlp.service_layer.respondent_field_schema_service import update_schema_from_headers
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

# Internal, export-only columns recognised and skipped on import. They mirror
# the extra columns build_respondent_table appends, so an exported file
# re-imports without colliding with reserved Respondent field names.
_INTERNAL_IMPORT_SKIP_COLUMNS = ("selection_status", "selection_run_id", "source_type", "created_at", "updated_at")


def create_respondent(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    external_id: str,
    attributes: dict[str, Any],
    **kwargs: Any,
) -> Respondent:
    """Create a new respondent for an assembly."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="create respondent",
                required_role="assembly-manager, global-organiser or admin",
            )

        # Check for duplicate
        existing = uow.respondents.get_by_external_id(assembly_id, external_id)
        if existing:
            raise ValueError(f"Respondent with external_id '{external_id}' already exists")

        respondent = Respondent(
            assembly_id=assembly_id,
            external_id=external_id,
            attributes=attributes,
            source_type=RespondentSourceType.MANUAL_ENTRY,
            **kwargs,
        )
        respondent.add_comment(
            text="Created via manual entry",
            author_id=user_id,
            action=RespondentAction.CREATE,
        )

        uow.respondents.add(respondent)
        uow.commit()
        return respondent.create_detached_copy()


def import_respondents_from_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    csv_content: str,
    replace_existing: bool = False,
    id_column: str | None = None,
    filename: str = "",
) -> tuple[list[Respondent], list[str], str]:
    """
    Import respondents from CSV.

    CSV format: id_column is required, all other columns become attributes.
    If id_column is not provided, the first column in the CSV is used.
    The filename, if provided, is recorded in the CREATE comment each row gets.
    Returns: (list of created respondents, list of error messages, resolved id_column name)
    """
    reader = csv.DictReader(StringIO(csv_content))
    headers = list(reader.fieldnames) if reader.fieldnames else []
    rows = list(reader) if reader.fieldnames else []
    return import_respondents_from_rows(
        uow,
        user_id,
        assembly_id,
        headers,
        rows,
        replace_existing=replace_existing,
        id_column=id_column,
        filename=filename,
    )


def import_respondents_from_rows(  # noqa: C901
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    headers: list[str],
    rows: list[dict[str, str]],
    replace_existing: bool = False,
    id_column: str | None = None,
    filename: str = "",
) -> tuple[list[Respondent], list[str], str]:
    """Import respondents from already-parsed tabular rows.

    Shared core behind CSV import (and, in future, Google Sheets import).
    ``headers`` is the ordered column list; ``rows`` maps each header to its
    value. The id_column becomes external_id; all other columns become
    attributes. If id_column is not provided, the first column is used.
    Returns: (list of created respondents, list of error messages, resolved id_column name)
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
                action="import respondents",
                required_role="assembly-manager, global-organiser or admin",
            )

        if not headers:
            raise InvalidSelection("CSV file is empty or has no header row")

        # Auto-detect id_column from first column if not provided
        if id_column is None:
            id_column = headers[0]

        if id_column not in headers:
            raise InvalidSelection(f"CSV must have '{id_column}' column")

        errors = []

        # Internal export-only columns are recognised and skipped so that a
        # previously-exported file re-imports cleanly (they would otherwise
        # collide with reserved Respondent field names). Report each once.
        skip_normalised = {normalise_field_name(c) for c in _INTERNAL_IMPORT_SKIP_COLUMNS}
        for header in headers:
            if header != id_column and normalise_field_name(header) in skip_normalised:
                errors.append(f"Ignored internal column not imported: {header}")

        # Replace existing if requested
        if replace_existing:
            uow.respondents.delete_all_for_assembly(assembly_id)

        # Create respondents
        respondents = []
        seen_ids = set()  # Track IDs within this import to catch duplicates
        # rows have had the header row stripped, so the first data row is line 2
        # of the file; start=2 makes row_number match what the user sees when
        # they open the file to fix a flagged row.
        for row_number, row in enumerate(rows, start=2):
            external_id = row.get(id_column, "").strip()
            if not external_id:
                errors.append(f"Row {row_number}: skipped, empty {id_column}")
                continue

            # Check for duplicate in database
            existing = uow.respondents.get_by_external_id(assembly_id, external_id)
            if existing:
                errors.append(f"Row {row_number}: skipped duplicate {id_column}: {external_id}")
                continue

            # Check for duplicate within this import
            if external_id in seen_ids:
                errors.append(f"Row {row_number}: skipped duplicate {id_column}: {external_id}")
                continue
            seen_ids.add(external_id)

            respondents.append(respondent_from_row(assembly_id, user_id, row, external_id, id_column, filename))

        # Bulk add for performance
        uow.respondents.bulk_add(respondents)

        # Seed the field schema on first import; reconcile (add new keys,
        # preserve absent ones) on subsequent imports.
        target_category_names = [cat.name for cat in uow.target_categories.get_by_assembly_id(assembly_id)]
        update_schema_from_headers(
            uow,
            assembly_id,
            list(headers),
            id_column,
            target_category_names=target_category_names,
        )

        uow.commit()

        return [r.create_detached_copy() for r in respondents], errors, id_column


def respondent_from_row(
    assembly_id: uuid.UUID,
    user_id: uuid.UUID,
    row: dict[str, str],
    external_id: str,
    id_column: str,
    filename: str = "",
) -> Respondent:
    """Build a single ``Respondent`` from one parsed import row.

    ``external_id`` is the already-stripped id value: the caller needs it for
    duplicate detection, so it is passed in rather than re-derived here. Every
    column except ``id_column`` becomes an attribute; the boolean flags and email
    are lifted out of the attributes, and internal export-only columns are
    discarded so they never land in ``attributes``. A CREATE comment recording
    the import (with the filename when known) is attached.
    """
    # All columns except id_column become attributes
    attributes = {k: v for k, v in row.items() if k != id_column}

    # Extract boolean flags if present (leave as None if not in CSV)
    consent_str = pop_normalised(attributes, "consent")
    consent = consent_str.lower() == "true" if consent_str else None

    eligible_str = pop_normalised(attributes, "eligible")
    eligible = eligible_str.lower() == "true" if eligible_str else None

    can_attend_str = pop_normalised(attributes, "can_attend")
    can_attend = can_attend_str.lower() == "true" if can_attend_str else None

    # stay_on_db is honoured when creating a fresh record (e.g. importing
    # from an internal system). A future update path must instead ignore
    # it, since bulk import must never silently flip an existing consent.
    stay_on_db_str = pop_normalised(attributes, "stay_on_db")
    stay_on_db = stay_on_db_str.lower() == "true" if stay_on_db_str else None

    email = pop_normalised(attributes, "email", "")

    # Discard internal export-only columns before constructing the
    # Respondent so they never land in attributes.
    for skip_column in _INTERNAL_IMPORT_SKIP_COLUMNS:
        pop_normalised(attributes, skip_column)

    respondent = Respondent(
        assembly_id=assembly_id,
        external_id=external_id,
        attributes=attributes,
        consent=consent,
        eligible=eligible,
        can_attend=can_attend,
        stay_on_db=stay_on_db,
        email=email,
        source_type=RespondentSourceType.CSV_IMPORT,
    )
    create_text = f"Created via CSV import ({filename})" if filename else "Created via CSV import"
    respondent.add_comment(
        text=create_text,
        author_id=user_id,
        action=RespondentAction.CREATE,
    )
    return respondent


def reset_selection_status(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> int:
    """Reset all respondents for an assembly back to POOL status. Returns count updated."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="reset selection status",
                required_role="assembly-manager, global-organiser or admin",
            )

        count = uow.respondents.reset_all_to_pool(assembly_id)
        uow.commit()
        return count


def get_respondents_for_assembly(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    status: RespondentStatus | None = None,
    include_deleted: bool = False,
) -> list[Respondent]:
    """Get respondents for an assembly. DELETED excluded unless include_deleted=True."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(
                action="view respondents",
                required_role="assembly role or global privileges",
            )

        respondents = uow.respondents.get_by_assembly_id(assembly_id, status=status, include_deleted=include_deleted)
        return [r.create_detached_copy() for r in respondents]


def get_respondents_for_assembly_paginated(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    page: int = 1,
    per_page: int = 50,
    status: RespondentStatus | None = None,
) -> tuple[list[Respondent], int]:
    """Get paginated respondents for an assembly. Returns (respondents, total_count)."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(
                action="view respondents",
                required_role="assembly role or global privileges",
            )

        respondents, total_count = uow.respondents.get_by_assembly_id_paginated(
            assembly_id,
            page=page,
            per_page=per_page,
            status=status,
            eligible_only=False,
            include_deleted=True,
        )
        return [r.create_detached_copy() for r in respondents], total_count


def count_non_pool_respondents(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> int:
    """Count respondents for an assembly that are not in POOL status."""
    return uow.respondents.count_non_pool(assembly_id)


def get_respondent_attribute_columns(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
) -> list[str]:
    """Get sorted list of available respondent attribute column names for an assembly."""
    return uow.respondents.get_attribute_columns(assembly_id)


def get_respondent_attribute_value_counts(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    attribute_name: str,
) -> dict[str, int]:
    """Get counts of each distinct value for a given attribute across respondents in an assembly."""
    return uow.respondents.get_attribute_value_counts(assembly_id, attribute_name)


def get_selected_respondent_attribute_value_counts(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    attribute_name: str,
) -> dict[str, int]:
    """Get counts of each distinct value for a given attribute across selected/confirmed respondents."""
    return uow.respondents.get_selected_attribute_value_counts(assembly_id, attribute_name)


def delete_respondent(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
    comment: str,
) -> None:
    """Blank personal data on a respondent (GDPR right to be forgotten)."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="delete respondent",
                required_role="assembly-manager, global-organiser or admin",
            )

        respondent = uow.respondents.get(respondent_id)
        if not respondent or respondent.assembly_id != assembly_id:
            raise RespondentNotFoundError(f"Respondent {respondent_id} not found in assembly {assembly_id}")
        assert isinstance(respondent, Respondent)

        respondent.delete_personal_data(author_id=user_id, comment=comment)
        uow.commit()


def update_respondent(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
    comment: str,
    *,
    email: str | None = _RESPONDENT_UNSET,
    eligible: bool | None = _RESPONDENT_UNSET,
    can_attend: bool | None = _RESPONDENT_UNSET,
    consent: bool | None = _RESPONDENT_UNSET,
    stay_on_db: bool | None = _RESPONDENT_UNSET,
    attributes: dict[str, Any] | None = None,
) -> None:
    """Apply a backoffice edit to a respondent. Requires `can_edit_respondent`."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_edit_respondent(user, assembly):
            raise InsufficientPermissions(
                action="edit respondent",
                required_role="assembly-manager, confirmation-caller, global-organiser or admin",
            )

        respondent = uow.respondents.get(respondent_id)
        if not respondent or respondent.assembly_id != assembly_id:
            raise RespondentNotFoundError(f"Respondent {respondent_id} not found in assembly {assembly_id}")
        assert isinstance(respondent, Respondent)

        respondent.apply_edit(
            author_id=user_id,
            comment=comment,
            email=email,
            eligible=eligible,
            can_attend=can_attend,
            consent=consent,
            stay_on_db=stay_on_db,
            attributes=attributes,
        )
        uow.commit()


def add_respondent_comment(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
    text: str,
) -> None:
    """Append a plain comment to a respondent."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(
                action="add respondent comment",
                required_role="assembly-manager, global-organiser or admin",
            )

        respondent = uow.respondents.get(respondent_id)
        if not respondent or respondent.assembly_id != assembly_id:
            raise RespondentNotFoundError(f"Respondent {respondent_id} not found in assembly {assembly_id}")
        assert isinstance(respondent, Respondent)

        respondent.add_comment(text=text, author_id=user_id)
        uow.commit()


def get_respondent(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
) -> Respondent:
    """Get single respondent for an assembly."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(
                action="view respondents",
                required_role="assembly role or global privileges",
            )

        respondent = uow.respondents.get(respondent_id)
        if not respondent or respondent.assembly_id != assembly_id:
            raise RespondentNotFoundError(f"Respondent {respondent_id} not found in assembly {assembly_id}")
        assert isinstance(respondent, Respondent)

        return respondent.create_detached_copy()


def get_respondent_with_comment_authors(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
) -> tuple[Respondent, dict[uuid.UUID, User]]:
    """Get a respondent plus the User behind each comment's author_id.

    Authors that no longer exist are omitted from the returned dict.
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
                action="view respondents",
                required_role="assembly role or global privileges",
            )

        respondent = uow.respondents.get(respondent_id)
        if not respondent or respondent.assembly_id != assembly_id:
            raise RespondentNotFoundError(f"Respondent {respondent_id} not found in assembly {assembly_id}")
        assert isinstance(respondent, Respondent)

        author_ids = {c.author_id for c in respondent.comments}
        authors: dict[uuid.UUID, User] = {}
        for author_id in author_ids:
            author = uow.users.get(author_id)
            if author:
                authors[author_id] = author.create_detached_copy()

        return respondent.create_detached_copy(), authors


def _required_permission_for_transition(old: RespondentStatus, new: RespondentStatus) -> Any:
    """Map a (from, to) transition to the permission function that must authorise it.

    Any transition that touches POOL on either side is an organiser-level
    operation (moving someone into or out of the unselected pool). Transitions
    among SELECTED / CONFIRMED / WITHDRAWN remain available to confirmation
    callers as part of their day-to-day work.
    """
    if old == RespondentStatus.POOL or new == RespondentStatus.POOL:
        return can_manage_assembly
    return can_call_confirmations


def transition_respondent_status(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    respondent_id: uuid.UUID,
    new_status: RespondentStatus,
    comment: str,
) -> None:
    """Apply a selection-status transition driven from the backoffice UI."""
    with uow:
        user = uow.users.get(user_id)
        if not user:
            raise UserNotFoundError(f"User {user_id} not found")

        assembly = uow.assemblies.get(assembly_id)
        if not assembly:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

        respondent = uow.respondents.get(respondent_id)
        if not respondent or respondent.assembly_id != assembly_id:
            raise RespondentNotFoundError(f"Respondent {respondent_id} not found in assembly {assembly_id}")
        assert isinstance(respondent, Respondent)

        allowed = ALLOWED_SELECTION_STATUS_TRANSITIONS.get(respondent.selection_status, [])
        if new_status not in allowed:
            raise ValueError(f"Transition {respondent.selection_status.value} -> {new_status.value} is not allowed")

        check = _required_permission_for_transition(respondent.selection_status, new_status)
        if not check(user, assembly):
            raise InsufficientPermissions(
                action="transition respondent status",
                required_role=check.__name__,
            )

        respondent.apply_status_transition(
            new_status=new_status,
            author_id=user_id,
            comment=comment,
        )
        uow.commit()
