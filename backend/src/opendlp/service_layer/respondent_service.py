"""ABOUTME: Respondent management service layer for participant pool operations
ABOUTME: Provides functions for respondent creation, CSV import, and validation"""

import csv
import uuid
from io import StringIO
from typing import Any

from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentSourceType, RespondentStatus
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    UserNotFoundError,
)
from opendlp.service_layer.permissions import can_manage_assembly, can_view_assembly
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


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

        uow.respondents.add(respondent)
        uow.commit()
        return respondent.create_detached_copy()


def import_respondents_from_csv(  # noqa: C901
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    csv_content: str,
    replace_existing: bool = False,
    id_column: str | None = None,
) -> tuple[list[Respondent], list[str], str]:
    """
    Import respondents from CSV.

    CSV format: id_column is required, all other columns become attributes.
    If id_column is not provided, the first column in the CSV is used.
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

        # Parse CSV
        csv_file = StringIO(csv_content)
        reader = csv.DictReader(csv_file)

        if not reader.fieldnames:
            raise InvalidSelection("CSV file is empty or has no header row")

        # Auto-detect id_column from first CSV column if not provided
        if id_column is None:
            id_column = reader.fieldnames[0]

        if id_column not in reader.fieldnames:
            raise InvalidSelection(f"CSV must have '{id_column}' column")

        errors = []

        # Replace existing if requested
        if replace_existing:
            existing_respondents = uow.respondents.get_by_assembly_id(assembly_id)
            for resp in existing_respondents:
                uow.respondents.delete(resp)

        # Create respondents
        respondents = []
        seen_ids = set()  # Track IDs within this CSV to catch duplicates
        for row in reader:
            external_id = row.get(id_column, "").strip()
            if not external_id:
                errors.append(f"Skipped row with empty {id_column}")
                continue

            # Check for duplicate in database
            existing = uow.respondents.get_by_external_id(assembly_id, external_id)
            if existing:
                errors.append(f"Skipped duplicate {id_column}: {external_id}")
                continue

            # Check for duplicate within this CSV
            if external_id in seen_ids:
                errors.append(f"Skipped duplicate {id_column}: {external_id}")
                continue
            seen_ids.add(external_id)

            # All columns except id_column become attributes
            attributes = {k: v for k, v in row.items() if k != id_column}

            # Extract boolean flags if present (leave as None if not in CSV)
            consent_str = attributes.pop("consent", None)
            consent = consent_str.lower() == "true" if consent_str else None

            eligible_str = attributes.pop("eligible", None)
            eligible = eligible_str.lower() == "true" if eligible_str else None

            can_attend_str = attributes.pop("can_attend", None)
            can_attend = can_attend_str.lower() == "true" if can_attend_str else None

            email = attributes.pop("email", "")

            respondent = Respondent(
                assembly_id=assembly_id,
                external_id=external_id,
                attributes=attributes,
                consent=consent,
                eligible=eligible,
                can_attend=can_attend,
                email=email,
                source_type=RespondentSourceType.CSV_IMPORT,
                source_reference=f"CSV import by user {user_id}",
            )
            respondents.append(respondent)

        # Bulk add for performance
        uow.respondents.bulk_add(respondents)
        uow.commit()

        return [r.create_detached_copy() for r in respondents], errors, id_column


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
) -> list[Respondent]:
    """Get respondents for an assembly."""
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

        respondents = uow.respondents.get_by_assembly_id(assembly_id, status=status)
        return [r.create_detached_copy() for r in respondents]


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
