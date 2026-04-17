"""ABOUTME: Service layer for the per-assembly RespondentFieldDefinition schema.
ABOUTME: Read, populate, edit, and initialise field schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from opendlp.domain.respondent_field_schema import (
    GROUP_DISPLAY_ORDER,
    IN_SCHEMA_FIXED_FIELDS,
    SORT_ORDER_STEP,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    humanise_field_key,
)
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    UserNotFoundError,
)
from opendlp.service_layer.permissions import can_manage_assembly, can_view_assembly
from opendlp.service_layer.respondent_field_schema_heuristics import classify_field_key
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


class FieldDefinitionNotFoundError(Exception):
    """Raised when a RespondentFieldDefinition cannot be found."""


class FieldDefinitionConflictError(Exception):
    """Raised when adding a field that already exists, or attempting a disallowed edit."""


def _ensure_view_permission(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> None:
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(
            action="view respondent field schema",
            required_role="assembly role or global privileges",
        )


def _ensure_manage_permission(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> None:
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="edit respondent field schema",
            required_role="assembly-manager, global-organiser or admin",
        )


def get_schema(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> list[RespondentFieldDefinition]:
    """Return the schema for an assembly, ordered by GROUP_DISPLAY_ORDER then sort_order."""
    with uow:
        _ensure_view_permission(uow, user_id, assembly_id)
        fields = uow.respondent_field_definitions.list_by_assembly(assembly_id)
        return [f.create_detached_copy() for f in fields]


def get_schema_grouped(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> dict[RespondentFieldGroup, list[RespondentFieldDefinition]]:
    """Return the schema as a map keyed by group, in display order.

    All groups are present in the map even if empty, so view code can iterate
    uniformly.
    """
    fields = get_schema(uow, user_id, assembly_id)
    grouped: dict[RespondentFieldGroup, list[RespondentFieldDefinition]] = {group: [] for group in GROUP_DISPLAY_ORDER}
    for field in fields:
        grouped.setdefault(field.group, []).append(field)
    return grouped


def _build_fixed_rows(assembly_id: uuid.UUID) -> list[RespondentFieldDefinition]:
    """Construct the in-schema fixed-field rows at their default positions.

    Per-group ordering here is fixed: rows are emitted in the order they appear
    in IN_SCHEMA_FIXED_FIELDS.
    """
    per_group_counter: dict[RespondentFieldGroup, int] = {}
    rows: list[RespondentFieldDefinition] = []
    for key, group, label in IN_SCHEMA_FIXED_FIELDS:
        idx = per_group_counter.get(group, 0)
        per_group_counter[group] = idx + 1
        rows.append(
            RespondentFieldDefinition(
                assembly_id=assembly_id,
                field_key=key,
                label=label,
                group=group,
                sort_order=(idx + 1) * SORT_ORDER_STEP,
                is_fixed=True,
            )
        )
    return rows


def _next_sort_order(
    per_group_next: dict[RespondentFieldGroup, int],
    group: RespondentFieldGroup,
) -> int:
    idx = per_group_next.get(group, 0)
    per_group_next[group] = idx + 1
    return (idx + 1) * SORT_ORDER_STEP


def populate_schema_from_headers(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    headers: list[str],
    id_column: str,
    target_category_names: list[str] | None = None,
) -> int:
    """Seed a fresh schema for an assembly from a set of CSV headers.

    Creates the in-schema fixed-field rows plus one row per non-fixed, non-id
    header, using heuristics to bucket each into a group. Preserves CSV header
    order within each group. No-op if the assembly already has a schema.
    Returns the number of rows inserted. Does not commit — caller owns the txn.
    """
    if uow.respondent_field_definitions.count_by_assembly_id(assembly_id) > 0:
        return 0

    target_names = target_category_names or []
    fixed_keys = {key for key, _group, _label in IN_SCHEMA_FIXED_FIELDS}

    rows = _build_fixed_rows(assembly_id)
    # Start per-group counters from where the fixed-field seeding left off so
    # heuristic-classified rows append after fixed rows in the same group.
    per_group_next: dict[RespondentFieldGroup, int] = {}
    for row in rows:
        per_group_next[row.group] = max(per_group_next.get(row.group, 0), row.sort_order // SORT_ORDER_STEP)

    for header in headers:
        header_stripped = header.strip()
        if not header_stripped or header_stripped == id_column or header_stripped in fixed_keys:
            continue
        group = classify_field_key(header_stripped, target_names)
        rows.append(
            RespondentFieldDefinition(
                assembly_id=assembly_id,
                field_key=header_stripped,
                label=humanise_field_key(header_stripped),
                group=group,
                sort_order=_next_sort_order(per_group_next, group),
            )
        )

    uow.respondent_field_definitions.bulk_add(rows)
    return len(rows)


def initialise_empty_schema(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> int:
    """Seed a schema containing only the fixed-field rows.

    For registration-form-first assemblies that don't yet have respondent data.
    No-op if a schema already exists.
    """
    with uow:
        _ensure_manage_permission(uow, user_id, assembly_id)
        if uow.respondent_field_definitions.count_by_assembly_id(assembly_id) > 0:
            return 0
        rows = _build_fixed_rows(assembly_id)
        uow.respondent_field_definitions.bulk_add(rows)
        uow.commit()
        return len(rows)


def update_field(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_id: uuid.UUID,
    label: str | None = None,
    group: RespondentFieldGroup | None = None,
    sort_order: int | None = None,
) -> RespondentFieldDefinition:
    """Update a field's label, group, or sort_order."""
    with uow:
        _ensure_manage_permission(uow, user_id, assembly_id)
        field = uow.respondent_field_definitions.get(field_id)
        if field is None or field.assembly_id != assembly_id:
            raise FieldDefinitionNotFoundError(f"Field {field_id} not found in assembly {assembly_id}")
        field.update(label=label, group=group, sort_order=sort_order)
        uow.commit()
        detached: RespondentFieldDefinition = field.create_detached_copy()
        return detached


def reorder_group(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    group: RespondentFieldGroup,
    ordered_field_ids: list[uuid.UUID],
) -> None:
    """Re-issue sort_order values for every field in a group.

    ``ordered_field_ids`` must contain all field_ids currently in the group,
    in the desired display order. Fields are re-numbered 10, 20, 30, ...
    """
    with uow:
        _ensure_manage_permission(uow, user_id, assembly_id)
        existing = [f for f in uow.respondent_field_definitions.list_by_assembly(assembly_id) if f.group == group]
        existing_by_id = {f.id: f for f in existing}
        if set(ordered_field_ids) != set(existing_by_id.keys()):
            raise FieldDefinitionConflictError(
                "reorder_group requires the complete set of field_ids currently in the group"
            )
        now = datetime.now(UTC)
        for i, field_id in enumerate(ordered_field_ids, start=1):
            field = existing_by_id[field_id]
            field.sort_order = i * SORT_ORDER_STEP
            field.updated_at = now
        uow.commit()


def delete_field(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_id: uuid.UUID,
) -> None:
    """Delete a non-fixed field from the schema.

    Fixed fields cannot be deleted — raises FieldDefinitionConflictError.
    Respondent attribute data is untouched (the attributes dict still holds
    the value, it's just no longer rendered in the detail page).
    """
    with uow:
        _ensure_manage_permission(uow, user_id, assembly_id)
        field = uow.respondent_field_definitions.get(field_id)
        if field is None or field.assembly_id != assembly_id:
            raise FieldDefinitionNotFoundError(f"Field {field_id} not found in assembly {assembly_id}")
        if field.is_fixed:
            raise FieldDefinitionConflictError(f"Fixed field '{field.field_key}' cannot be deleted")
        uow.respondent_field_definitions.delete(field)
        uow.commit()
