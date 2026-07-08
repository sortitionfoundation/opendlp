"""ABOUTME: Service layer for exporting respondents to CSV or Google Sheets
ABOUTME: Builds tabular data, resolves status filters, orchestrates the export"""

import uuid

from opendlp.adapters.tabular_export import AbstractTabularExportTarget, TabularData
from opendlp.domain.assembly_respondent_gsheet import AssemblyRespondentGSheet
from opendlp.domain.respondent_field_schema import RespondentFieldDefinition
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    InvalidSelection,
    UserNotFoundError,
)
from opendlp.service_layer.permissions import can_manage_assembly
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _

DEFAULT_SHEET_TITLE = "Respondents"

# UI filter tokens accepted by resolve_status_filter alongside plain status names.
STATUS_FILTER_ALL = "all"
STATUS_FILTER_SELECTED_OR_CONFIRMED = "selected_or_confirmed"

# Reserved top-level fields read directly off the Respondent rather than
# from its attributes dict. Kept in sync with the fixed schema fields.
_TOP_LEVEL_FIELD_KEYS = frozenset({"email", "eligible", "can_attend", "consent", "stay_on_db"})

# Internal-only columns appended after the schema and attribute columns.
_INTERNAL_COLUMNS = ("selection_status", "source_type", "selection_run_id", "created_at", "updated_at")


def resolve_status_filter(raw: str) -> list[RespondentStatus] | None:
    """Map a UI filter token to the statuses to export.

    Returns ``None`` for "all" (every status except DELETED, applied at fetch
    time). Rejects DELETED and unrecognised values with InvalidSelection.
    """
    value = (raw or "").strip()
    if not value or value == STATUS_FILTER_ALL:
        return None
    if value == STATUS_FILTER_SELECTED_OR_CONFIRMED:
        return [RespondentStatus.SELECTED, RespondentStatus.CONFIRMED]
    status = RespondentStatus.from_str(value)
    if status is None or status == RespondentStatus.DELETED:
        raise InvalidSelection(_("Invalid respondent status filter: %(value)s", value=value))
    return [status]


def _serialise_bool(value: bool | None) -> str:
    if value is None:
        return ""
    return "true" if value else "false"


def _serialise_field(respondent: Respondent, field_key: str) -> str:
    """Serialise one schema field for a respondent as a CSV-ready string."""
    if field_key == "email":
        return respondent.email
    if field_key in _TOP_LEVEL_FIELD_KEYS:
        return _serialise_bool(getattr(respondent, field_key))
    value = respondent.attributes.get(field_key)
    return "" if value is None else str(value)


def _serialise_internal(respondent: Respondent, column: str) -> str:
    if column == "selection_status":
        return respondent.selection_status.value
    if column == "source_type":
        return respondent.source_type.value
    if column == "selection_run_id":
        return str(respondent.selection_run_id) if respondent.selection_run_id else ""
    if column == "created_at":
        return respondent.created_at.isoformat()
    return respondent.updated_at.isoformat()


def build_respondent_table(
    respondents: list[Respondent],
    schema: list[RespondentFieldDefinition],
    id_column_header: str,
) -> TabularData:
    """Turn respondents into a table: id column, schema fields, leftover
    attributes (sorted), then internal columns.

    Pure: takes already-fetched domain objects and the resolved id-column
    header, so it can be unit-tested without a UnitOfWork.
    """
    schema_keys = [f.field_key for f in schema]
    schema_key_set = set(schema_keys)

    leftover_keys: set[str] = set()
    for respondent in respondents:
        leftover_keys.update(k for k in respondent.attributes if k not in schema_key_set)
    leftover = sorted(leftover_keys)

    headers = [id_column_header, *schema_keys, *leftover, *_INTERNAL_COLUMNS]

    rows: list[list[str]] = []
    for respondent in respondents:
        row = [respondent.external_id]
        row.extend(_serialise_field(respondent, key) for key in schema_keys)
        row.extend(_serialise_field(respondent, key) for key in leftover)
        row.extend(_serialise_internal(respondent, column) for column in _INTERNAL_COLUMNS)
        rows.append(row)

    return TabularData(headers=headers, rows=rows)


def _resolve_id_column_header(assembly: object) -> str:
    csv_config = getattr(assembly, "csv", None)
    if csv_config is not None and csv_config.csv_id_column:
        return str(csv_config.csv_id_column)
    return "external_id"


def _fetch_respondents(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    status_filter: list[RespondentStatus] | None,
) -> list[Respondent]:
    """Fetch respondents for the export, ordered oldest-first by created_at.

    ``None`` means every non-DELETED respondent; a list means those statuses.
    Ordering is done in the query so the export is stable regardless of status.
    """
    return list(uow.respondents.get_by_assembly_id_statuses(assembly_id, status_filter))


def _require_manage(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> object:
    """Load the assembly after checking the user may manage it."""
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")

    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")

    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(
            action="export respondents",
            required_role="assembly-manager, global-organiser or admin",
        )
    return assembly


def _write_export(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    assembly: object,
    status_filter: list[RespondentStatus] | None,
    target: AbstractTabularExportTarget,
    sheet_title: str,
) -> None:
    """Build the respondent table and hand it to the target. Assumes an open
    uow and an already-authorised caller."""
    respondents = _fetch_respondents(uow, assembly_id, status_filter)
    schema = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    id_column_header = _resolve_id_column_header(assembly)
    table = build_respondent_table(respondents, schema, id_column_header)
    target.write_sheet(sheet_title, table)


def export_respondents(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    status_filter: list[RespondentStatus] | None,
    target: AbstractTabularExportTarget,
    sheet_title: str = DEFAULT_SHEET_TITLE,
) -> None:
    """Export an assembly's respondents to the given target.

    ``status_filter`` of ``None`` exports every non-DELETED respondent; a list
    of statuses exports just those (fetched with one query each and merged).
    Requires manage permission on the assembly.
    """
    with uow:
        assembly = _require_manage(uow, user_id, assembly_id)
        _write_export(uow, assembly_id, assembly, status_filter, target, sheet_title)


def get_respondent_gsheet_config(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> "AssemblyRespondentGSheet | None":
    """Return the saved respondent-export sheet config, or None. Manage-gated."""
    with uow:
        _require_manage(uow, user_id, assembly_id)
        config = uow.assembly_respondent_gsheets.get_by_assembly_id(assembly_id)
        return config.create_detached_copy() if config else None


def export_respondents_to_gsheet(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    status_filter: list[RespondentStatus] | None,
    spreadsheet_url: str,
    worksheet_name: str,
    target: AbstractTabularExportTarget,
) -> None:
    """Export respondents to a Google Sheet and save/update the sheet config.

    ``target`` is the (real or fake) Google Sheets target; the caller reads its
    result URL afterwards. The spreadsheet URL and worksheet name are persisted
    to AssemblyRespondentGSheet so later exports can pre-fill the form.
    """
    worksheet_name = worksheet_name.strip() or DEFAULT_SHEET_TITLE
    with uow:
        assembly = _require_manage(uow, user_id, assembly_id)

        config = uow.assembly_respondent_gsheets.get_by_assembly_id(assembly_id)
        if config is None:
            config = AssemblyRespondentGSheet(
                assembly_id=assembly_id,
                url=spreadsheet_url,
                worksheet_name=worksheet_name,
            )
            uow.assembly_respondent_gsheets.add(config)
        else:
            config.update_values(url=spreadsheet_url, worksheet_name=worksheet_name)

        _write_export(uow, assembly_id, assembly, status_filter, target, worksheet_name)
        uow.commit()
