"""ABOUTME: Service layer for exporting respondents to CSV or Google Sheets
ABOUTME: Builds tabular data, resolves status filters, orchestrates the export"""

import uuid

from opendlp import config
from opendlp.adapters.tabular_export import (
    AbstractGSheetExportTarget,
    AbstractTabularExportTarget,
    TabularData,
)
from opendlp.domain.assembly import Assembly
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet, default_worksheet_name
from opendlp.domain.respondent_field_schema import RespondentFieldDefinition
from opendlp.domain.respondents import Respondent
from opendlp.domain.validators import GoogleSpreadsheetURLValidator
from opendlp.domain.value_objects import GSheetExportKind, RespondentStatus
from opendlp.service_layer.exceptions import AssemblyNotFoundError, InvalidSelection
from opendlp.service_layer.export_gsheet_config import save_export_gsheet_config
from opendlp.service_layer.permissions import can_manage_assembly, require_assembly_permission
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _

EXPORT_KIND = GSheetExportKind.RESPONDENTS

# UI filter tokens accepted by resolve_status_filter alongside plain status names.
STATUS_FILTER_ALL = "all"
STATUS_FILTER_SELECTED_OR_CONFIRMED = "selected_or_confirmed"

# Reserved top-level fields read directly off the Respondent rather than
# from its attributes dict. Kept in sync with the fixed schema fields.
_TOP_LEVEL_FIELD_KEYS = frozenset({"email", "eligible", "can_attend", "consent", "stay_on_db"})

# Internal-only columns appended after the schema and attribute columns.
_INTERNAL_COLUMNS = ("selection_status", "source_type", "selection_run_id", "created_at", "updated_at")

# The final column: a link to the respondent's page in OpenDLP.
VIEW_URL_COLUMN = "view_url"


def resolve_status_filter(raw: str) -> list[RespondentStatus] | None:
    """Map a UI filter token to the statuses to export.

    Returns ``None`` for "all" (every status except DELETED, applied at fetch
    time). DELETED can still be chosen on its own: those rows carry only the
    external ID, so an organiser can find and erase the person from copies held
    outside OpenDLP. Rejects unrecognised values with InvalidSelection.
    """
    value = (raw or "").strip()
    if not value or value == STATUS_FILTER_ALL:
        return None
    if value == STATUS_FILTER_SELECTED_OR_CONFIRMED:
        return [RespondentStatus.SELECTED, RespondentStatus.CONFIRMED]
    status = RespondentStatus.from_str(value)
    if status is None:
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


def respondent_view_url(application_url: str, assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> str:
    """The absolute URL of a respondent's page, or "" when APPLICATION_URL is not set.

    Built by hand rather than with ``url_for`` because the automatic export runs
    in a Celery worker, with no Flask app to build it. Must match the route of
    ``respondents.view_respondent``; a test holds the two together.
    """
    if not application_url:
        return ""
    return f"{application_url}/backoffice/assembly/{assembly_id}/respondents/{respondent_id}"


def build_respondent_table(
    respondents: list[Respondent],
    schema: list[RespondentFieldDefinition],
    id_column_header: str,
    application_url: str = "",
) -> TabularData:
    """Turn respondents into a table: id column, schema fields, leftover
    attributes (sorted), internal columns, then the respondent's view URL.

    The view URL column is always present, but blank when ``application_url`` is empty.

    Pure: takes already-fetched domain objects and the resolved id-column
    header, so it can be unit-tested without a UnitOfWork.
    """
    schema_keys = [f.field_key for f in schema]
    schema_key_set = set(schema_keys)

    leftover_keys: set[str] = set()
    for respondent in respondents:
        leftover_keys.update(k for k in respondent.attributes if k not in schema_key_set)
    leftover = sorted(leftover_keys)

    headers = [id_column_header, *schema_keys, *leftover, *_INTERNAL_COLUMNS, VIEW_URL_COLUMN]

    rows: list[list[str]] = []
    for respondent in respondents:
        row = [respondent.external_id]
        row.extend(_serialise_field(respondent, key) for key in schema_keys)
        row.extend(_serialise_field(respondent, key) for key in leftover)
        row.extend(_serialise_internal(respondent, column) for column in _INTERNAL_COLUMNS)
        row.append(respondent_view_url(application_url, respondent.assembly_id, respondent.id))
        rows.append(row)

    return TabularData(headers=headers, rows=rows)


def resolve_id_column_header(assembly: Assembly) -> str:
    if assembly.csv is not None and assembly.csv.csv_id_column:
        return str(assembly.csv.csv_id_column)
    return "external_id"


def _fetch_respondents(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    status_filter: list[RespondentStatus] | None,
) -> list[Respondent]:
    """Fetch respondents for the export, ordered oldest-first by created_at.

    ``None`` means every non-DELETED respondent; a list means those statuses.
    Ordering is done in the query so the export is stable regardless of status.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    return list(uow.respondents.get_by_assembly_id_statuses(assembly_id, status_filter))


def _load_assembly(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> Assembly:
    """Load the assembly, assuming the caller has already checked permissions.

    Manage permission is enforced by the ``require_assembly_permission``
    decorator on the public functions, so this only guards against a missing

    The caller is expected to manage the `uow` context (`with uow: ...`).
    row (which the decorator also rejects, but mypy needs the narrowing)."""
    assembly: Assembly | None = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    return assembly


def _write_export(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    assembly: Assembly,
    status_filter: list[RespondentStatus] | None,
    target: AbstractTabularExportTarget,
    sheet_title: str,
) -> None:
    """Build the respondent table and hand it to the target. Assumes an open

    The caller is expected to manage the `uow` context (`with uow: ...`).
    uow and an already-authorised caller."""
    respondents = _fetch_respondents(uow, assembly_id, status_filter)
    schema = uow.respondent_field_definitions.list_by_assembly(assembly_id)
    id_column_header = resolve_id_column_header(assembly)
    table = build_respondent_table(respondents, schema, id_column_header, application_url=config.get_application_url())
    target.write_sheet(sheet_title, table)


def write_respondent_export(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    *,
    status_filter: list[RespondentStatus] | None,
    target: AbstractTabularExportTarget,
    sheet_title: str = "",
) -> None:
    """Export an assembly's respondents to the given target, with no permission check.

    ``status_filter`` of ``None`` exports every non-DELETED respondent; a list
    of statuses exports just those (fetched in a single query). Routes must go
    through ``export_respondents``, which gates on manage permission; this is
    for callers with no acting user, such as the automatic export task.

    An empty ``sheet_title`` means the default for this export kind, resolved
    here rather than as a default argument so it lands in the caller's language.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    sheet_title = sheet_title or default_worksheet_name(EXPORT_KIND)
    assembly = _load_assembly(uow, assembly_id)
    _write_export(uow, assembly_id, assembly, status_filter, target, sheet_title)


@require_assembly_permission(can_manage_assembly)
def export_respondents(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    status_filter: list[RespondentStatus] | None,
    target: AbstractTabularExportTarget,
    sheet_title: str = "",
) -> None:
    """Export an assembly's respondents to the given target.

    ``status_filter`` of ``None`` exports every non-DELETED respondent; a list
    of statuses exports just those (fetched in a single query). Requires manage
    permission on the assembly. The caller is expected to manage the ``uow``
    context (``with uow: ...``).
    """
    write_respondent_export(uow, assembly_id, status_filter=status_filter, target=target, sheet_title=sheet_title)


@require_assembly_permission(can_manage_assembly)
def get_respondent_gsheet_config(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> "AssemblyExportGSheet | None":
    """Return the saved respondent-export sheet config, or None. Manage-gated.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly_id, EXPORT_KIND)
    return config.create_detached_copy() if config else None


@require_assembly_permission(can_manage_assembly)
def export_respondents_to_gsheet(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    status_filter: list[RespondentStatus] | None,
    spreadsheet_url: str,
    worksheet_name: str,
    target: AbstractGSheetExportTarget,
    auto_export: bool = False,
    auto_export_status_filter: str = "",
) -> None:
    """Export respondents to a Google Sheet and save/update the sheet config.

    ``target`` is the (real or fake) Google Sheets target; the caller reads its
    result URL afterwards. The spreadsheet URL and worksheet name are persisted
    to AssemblyExportGSheet so later exports can pre-fill the form, along
    with the spreadsheet's title and the direct worksheet link read off the
    target after the write, so the respondents page can link to the export.

    ``auto_export`` is saved as given on every Google Sheets export, so the
    checkbox on the form is the truth each time. Because the write comes first,
    a failed export cannot switch auto-export on. ``auto_export_status_filter``
    is the UI token the background export should resolve with
    ``resolve_status_filter``; it should describe ``status_filter``.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Validate the destination URL BEFORE writing: gspread's URL parsing is laxer
    # than the domain validator, so validating only at config-save time would let
    # the write clear a tab of a sheet whose URL is then rejected.
    GoogleSpreadsheetURLValidator().validate_str(spreadsheet_url.strip())
    worksheet_name = worksheet_name.strip() or default_worksheet_name(EXPORT_KIND)
    assembly = _load_assembly(uow, assembly_id)

    # Write first so the target's result_title/result_url are populated; only
    # then persist the config, so a failed write saves nothing (the caller's
    # uow rolls back on the raised ExportTargetError before this commit).
    _write_export(uow, assembly_id, assembly, status_filter, target, worksheet_name)

    save_export_gsheet_config(
        uow,
        assembly_id,
        EXPORT_KIND,
        spreadsheet_url=spreadsheet_url,
        worksheet_name=worksheet_name,
        target=target,
        auto_export=auto_export,
        auto_export_status_filter=auto_export_status_filter if auto_export else "",
    )


@require_assembly_permission(can_manage_assembly)
def disable_auto_export(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> None:
    """Switch off the automatic respondent export, touching nothing else.

    The saved URL, tab and last-export link stay so the next manual export
    pre-fills as before. No Google call is made: this must work when the sheet
    is the thing that is broken. Does nothing when there is no config, or
    auto-export is already off. Commits.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly_id, EXPORT_KIND)
    if config is None or not config.auto_export:
        return
    config.update_values(auto_export=False)
    uow.commit()
