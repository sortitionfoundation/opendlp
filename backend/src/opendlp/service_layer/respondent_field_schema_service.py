"""ABOUTME: Service layer for the per-assembly RespondentFieldDefinition schema.
ABOUTME: Read, populate, edit, and initialise field schemas."""

from __future__ import annotations

import csv as csv_module
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import StringIO

from opendlp.config import to_bool
from opendlp.domain.respondent_field_schema import _UNSET as _UNSET_OPTIONS
from opendlp.domain.respondent_field_schema import (
    FIXED_FIELD_TYPES,
    GROUP_DISPLAY_ORDER,
    IN_SCHEMA_FIXED_FIELDS,
    SORT_ORDER_STEP,
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    humanise_field_key,
)
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    UserNotFoundError,
)
from opendlp.service_layer.permissions import can_manage_assembly, can_view_assembly
from opendlp.service_layer.respondent_field_schema_heuristics import classify_field_key
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

_MAX_RADIO_OPTIONS = 6


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
    for f in fields:
        grouped.setdefault(f.group, []).append(f)
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
                field_type=FIXED_FIELD_TYPES.get(key, FieldType.TEXT),
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
    field_type: FieldType | None = None,
    options: list[ChoiceOption] | None = _UNSET_OPTIONS,
) -> RespondentFieldDefinition:
    """Update a field's label, group, sort_order, field_type, or options.

    ``options`` uses a sentinel to distinguish "leave alone" from "set to None".
    """
    with uow:
        _ensure_manage_permission(uow, user_id, assembly_id)
        field = uow.respondent_field_definitions.get(field_id)
        if field is None or field.assembly_id != assembly_id:
            raise FieldDefinitionNotFoundError(f"Field {field_id} not found in assembly {assembly_id}")
        try:
            field.update(
                label=label,
                group=group,
                sort_order=sort_order,
                field_type=field_type,
                options=options,
            )
        except ValueError as exc:
            if "fixed" in str(exc):
                raise FieldDefinitionConflictError(str(exc)) from exc
            raise
        uow.commit()
        detached: RespondentFieldDefinition = field.create_detached_copy()
        return detached


def _choice_type_for(n_options: int) -> FieldType:
    return FieldType.CHOICE_RADIO if n_options <= _MAX_RADIO_OPTIONS else FieldType.CHOICE_DROPDOWN


def _non_empty(values: list[str]) -> list[str]:
    return [v.strip() for v in values if v is not None and v.strip()]


def _is_all_bool(values: list[str]) -> bool:
    if not values:
        return False
    for v in values:
        try:
            to_bool(v)
        except ValueError:
            return False
    return True


def _is_all_int(values: list[str]) -> bool:
    if not values:
        return False
    for v in values:
        try:
            int(v)
        except ValueError:
            return False
    return True


def guess_field_types(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> dict[str, FieldType]:
    """Overwrite field_type for non-fixed, non-derived, text-typed fields based
    on the attribute-value distribution. Returns a map of field_key -> new type
    for rows that were changed."""
    # Local import to avoid a circular import:
    # target_respondent_helpers -> respondent_service -> respondent_field_schema_service.
    from opendlp.service_layer.target_respondent_helpers import MAX_DISTINCT_VALUES_FOR_AUTO_ADD  # noqa: PLC0415

    changed: dict[str, FieldType] = {}
    with uow:
        _ensure_manage_permission(uow, user_id, assembly_id)
        fields = uow.respondent_field_definitions.list_by_assembly(assembly_id)
        target_categories = uow.target_categories.get_by_assembly_id(assembly_id)
        target_by_name = {cat.name.lower(): cat for cat in target_categories}

        for f in fields:
            if f.is_fixed or f.is_derived or f.field_type != FieldType.TEXT:
                continue

            # Target-category name match wins first.
            cat = target_by_name.get(f.field_key.lower())
            if cat is not None and cat.values:
                option_values = sorted(v.value for v in cat.values)
                new_type = _choice_type_for(len(option_values))
                f.update(
                    field_type=new_type,
                    options=[ChoiceOption(value=v) for v in option_values],
                )
                changed[f.field_key] = new_type
                continue

            value_counts = uow.respondents.get_attribute_value_counts(assembly_id, f.field_key)
            distinct = _non_empty(list(value_counts.keys()))
            if not distinct:
                continue

            if _is_all_bool(distinct):
                f.update(field_type=FieldType.BOOL_OR_NONE)
                changed[f.field_key] = FieldType.BOOL_OR_NONE
                continue

            if _is_all_int(distinct):
                f.update(field_type=FieldType.INTEGER)
                changed[f.field_key] = FieldType.INTEGER
                continue

            if 0 < len(distinct) < MAX_DISTINCT_VALUES_FOR_AUTO_ADD:
                option_values = sorted(distinct)
                new_type = _choice_type_for(len(option_values))
                f.update(
                    field_type=new_type,
                    options=[ChoiceOption(value=v) for v in option_values],
                )
                changed[f.field_key] = new_type
                continue

        uow.commit()
    return changed


def add_choice_option(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_id: uuid.UUID,
    value: str,
    help_text: str = "",
) -> RespondentFieldDefinition:
    """Append a ChoiceOption to a choice field's options list."""
    with uow:
        _ensure_manage_permission(uow, user_id, assembly_id)
        field = uow.respondent_field_definitions.get(field_id)
        if field is None or field.assembly_id != assembly_id:
            raise FieldDefinitionNotFoundError(f"Field {field_id} not found in assembly {assembly_id}")
        if field.field_type not in {FieldType.CHOICE_RADIO, FieldType.CHOICE_DROPDOWN}:
            raise FieldDefinitionConflictError("Options can only be set on choice fields")
        value = value.strip()
        if not value:
            raise FieldDefinitionConflictError("Option value cannot be blank")
        new_options = list(field.options or [])
        if any(o.value == value for o in new_options):
            raise FieldDefinitionConflictError(f"Option '{value}' already exists")
        new_options.append(ChoiceOption(value=value, help_text=help_text))
        field.update(options=new_options)
        uow.commit()
        detached: RespondentFieldDefinition = field.create_detached_copy()
        return detached


def remove_choice_option(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    field_id: uuid.UUID,
    value: str,
) -> RespondentFieldDefinition:
    """Remove a ChoiceOption from a choice field's options list."""
    with uow:
        _ensure_manage_permission(uow, user_id, assembly_id)
        field = uow.respondent_field_definitions.get(field_id)
        if field is None or field.assembly_id != assembly_id:
            raise FieldDefinitionNotFoundError(f"Field {field_id} not found in assembly {assembly_id}")
        existing = list(field.options or [])
        remaining = [o for o in existing if o.value != value]
        if len(remaining) == len(existing):
            raise FieldDefinitionNotFoundError(f"Option '{value}' not found on field {field_id}")
        if not remaining:
            raise FieldDefinitionConflictError("A choice field must keep at least one option")
        field.update(options=remaining)
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


# ---------------------------------------------------------------------------
# Reconciliation: comparing an existing schema against a new CSV's headers.
# ---------------------------------------------------------------------------


@dataclass
class ReconciliationDiff:
    """Summary of how a new set of CSV headers compares to an existing schema.

    ``unchanged`` and ``absent_keys`` exclude the in-schema fixed-field keys
    (``email``, ``consent``, ``stay_on_db``, ``eligible``, ``can_attend``) and
    the id column — those are never reconciled.

    ``new_keys`` carries each new key paired with its heuristic-suggested group
    so the UI can show where it will land if applied.

    ``has_changes`` returns True iff applying the diff would mutate the schema.
    """

    assembly_id: uuid.UUID
    unchanged: list[str] = field(default_factory=list)
    new_keys: list[tuple[str, RespondentFieldGroup]] = field(default_factory=list)
    absent_keys: list[str] = field(default_factory=list)
    id_column_changed: tuple[str, str] | None = None

    @property
    def has_changes(self) -> bool:
        return bool(self.new_keys) or bool(self.absent_keys) or self.id_column_changed is not None


def compute_reconciliation_diff(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    headers: list[str],
    id_column: str,
    target_category_names: list[str] | None = None,
    previous_id_column: str | None = None,
) -> ReconciliationDiff:
    """Compare a CSV's headers against the existing schema. Read-only.

    Excludes the id column and the in-schema fixed-field keys from comparison
    (those are always present and not reconciled). New keys are classified via
    heuristics so the UI can surface the suggested group.

    ``previous_id_column`` lets the caller supply the id column from the prior
    upload so a column rename can be flagged. Pass ``None`` to skip that check.
    """
    diff = ReconciliationDiff(assembly_id=assembly_id)
    if previous_id_column and previous_id_column != id_column:
        diff.id_column_changed = (previous_id_column, id_column)

    fixed_keys = {key for key, _group, _label in IN_SCHEMA_FIXED_FIELDS}
    target_names = target_category_names or []

    existing = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    existing_keys = {f.field_key for f in existing if not f.is_fixed}

    seen_in_csv: set[str] = set()
    for header in headers:
        key = header.strip()
        if not key or key == id_column or key in fixed_keys or key in seen_in_csv:
            continue
        seen_in_csv.add(key)
        if key in existing_keys:
            diff.unchanged.append(key)
        else:
            diff.new_keys.append((key, classify_field_key(key, target_names)))

    diff.absent_keys = sorted(existing_keys - seen_in_csv)
    return diff


def apply_reconciliation(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    diff: ReconciliationDiff,
) -> int:
    """Insert schema rows for new keys discovered by the reconciliation.

    Absent keys are intentionally left in place — their data is gone but the
    schema row is preserved so the layout sticks if the column reappears, and
    so the organiser can still see what was lost. Does not commit; the caller
    owns the transaction.

    Returns the number of new rows inserted.
    """
    if not diff.new_keys:
        return 0

    existing = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    per_group_next: dict[RespondentFieldGroup, int] = {}
    for f in existing:
        per_group_next[f.group] = max(per_group_next.get(f.group, 0), f.sort_order // SORT_ORDER_STEP)

    new_rows: list[RespondentFieldDefinition] = []
    for key, group in diff.new_keys:
        new_rows.append(
            RespondentFieldDefinition(
                assembly_id=assembly_id,
                field_key=key,
                label=humanise_field_key(key),
                group=group,
                sort_order=_next_sort_order(per_group_next, group),
            )
        )
    uow.respondent_field_definitions.bulk_add(new_rows)
    return len(new_rows)


def update_schema_from_headers(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    headers: list[str],
    id_column: str,
    target_category_names: list[str] | None = None,
) -> int:
    """Bring the schema in line with a CSV's headers.

    Wraps the populate / reconcile branch: if no schema exists for the
    assembly, seed a fresh one; otherwise add rows for any new headers and
    leave absent keys in place. Returns the number of rows inserted.
    """
    if uow.respondent_field_definitions.count_by_assembly_id(assembly_id) == 0:
        return populate_schema_from_headers(
            uow, assembly_id, headers, id_column, target_category_names=target_category_names
        )
    diff = compute_reconciliation_diff(
        uow, assembly_id, headers, id_column, target_category_names=target_category_names
    )
    return apply_reconciliation(uow, assembly_id, diff)


def _parse_csv_headers(csv_content: str) -> list[str]:
    """Read the header row from a CSV and return the column names in order.

    Raises ``InvalidSelection`` if the CSV has no header row at all.
    """
    reader = csv_module.DictReader(StringIO(csv_content))
    headers = list(reader.fieldnames or [])
    if not headers:
        raise InvalidSelection("CSV file is empty or has no header row")
    return headers


def _auto_detect_id_column(headers: list[str], explicit_id_column: str | None) -> str:
    """Mirror ``import_respondents_from_csv``'s id-column rule.

    If the caller supplies a column name, use it verbatim; otherwise the first
    column wins. Returns the empty string only when ``headers`` is empty (in
    practice that can't happen because ``_parse_csv_headers`` rejects it).
    """
    if explicit_id_column:
        return explicit_id_column
    return headers[0] if headers else ""


def compute_diff_for_pending_csv(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    csv_content: str,
    explicit_id_column: str | None,
) -> ReconciliationDiff | None:
    """Compute the reconciliation diff for a pending CSV upload.

    Read-only. Parses the CSV header row, resolves the id column via the same
    auto-detect rule the importer uses, pulls the existing schema and target
    categories, and compares. Returns ``None`` when the assembly has no schema
    yet — the caller interprets that as "skip the confirmation page entirely".

    Raises ``InvalidSelection`` if the CSV has no header row.
    """
    headers = _parse_csv_headers(csv_content)
    id_column = _auto_detect_id_column(headers, explicit_id_column)

    with uow:
        _ensure_view_permission(uow, user_id, assembly_id)
        if uow.respondent_field_definitions.count_by_assembly_id(assembly_id) == 0:
            return None

        target_category_names = [c.name for c in uow.target_categories.get_by_assembly_id(assembly_id)]

        # Pull the previous id column from the assembly's CSV config so we can
        # flag column renames. ``assembly.csv`` is the ORM relationship, so we
        # read it inside the same uow rather than reopening another one.
        assembly = uow.assemblies.get(assembly_id)
        if assembly is None:
            raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
        previous_id_column: str | None = None
        if assembly.csv is not None:
            previous_id_column = assembly.csv.csv_id_column

        return compute_reconciliation_diff(
            uow,
            assembly_id,
            headers,
            id_column,
            target_category_names=target_category_names,
            previous_id_column=previous_id_column,
        )
