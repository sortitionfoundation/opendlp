"""ABOUTME: Service layer for exporting an assembly's targets to CSV or Google Sheets
ABOUTME: Writes the columns the targets CSV import reads, so an export can be uploaded again"""

import uuid

from opendlp.adapters.tabular_export import (
    AbstractGSheetExportTarget,
    AbstractTabularExportTarget,
    TabularData,
)
from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet, default_worksheet_name
from opendlp.domain.targets import TargetCategory, flex_is_set_on_all
from opendlp.domain.validators import GoogleSpreadsheetURLValidator
from opendlp.domain.value_objects import GSheetExportKind
from opendlp.service_layer.export_gsheet_config import save_export_gsheet_config
from opendlp.service_layer.permissions import can_manage_assembly, require_assembly_permission
from opendlp.service_layer.target_csv_import import (
    CATEGORY_COMMENT_COLUMN,
    CATEGORY_SOURCE_URL_COLUMN,
    VALUE_COMMENT_COLUMN,
    VALUE_PERCENTAGE_COLUMN,
)
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

EXPORT_KIND = GSheetExportKind.TARGETS

# The sortition library's own column names, as the import reads them.
_LIBRARY_COLUMNS = ("feature", "value", "min", "max")
_FLEX_COLUMNS = ("min_flex", "max_flex")
_EXTRA_COLUMNS = (VALUE_PERCENTAGE_COLUMN, VALUE_COMMENT_COLUMN, CATEGORY_COMMENT_COLUMN, CATEGORY_SOURCE_URL_COLUMN)


def _format_percentage(percentage: float | None) -> str:
    """A whole percentage without its ".0", as someone would type it; blank when unset."""
    if percentage is None:
        return ""
    if float(percentage).is_integer():
        return str(int(percentage))
    return str(percentage)


def build_targets_table(categories: list[TargetCategory]) -> TabularData:
    """Turn target categories into the table the targets CSV import reads.

    One row per value, in the order the categories and values are shown. The
    category's comment and source are repeated on every one of its rows, so a
    row can be sorted or filtered without losing them; the import takes them
    from whichever row has them, and repeats agree.

    Flex columns are written only when every value has flex set - the same rule
    selection uses - so uploading the export gives the flex that selecting from
    these targets would. A category with no values has no row to go in, so it
    is left out, as the import has no way to create one.

    Pure: takes already-fetched domain objects, so it can be unit-tested
    without a UnitOfWork.
    """
    values = [(category, value) for category in categories for value in category.values]
    with_flex = flex_is_set_on_all([(value.min_flex, value.max_flex) for _, value in values])
    headers = [*_LIBRARY_COLUMNS, *(_FLEX_COLUMNS if with_flex else ()), *_EXTRA_COLUMNS]

    rows: list[list[str]] = []
    for category, value in values:
        row = [category.name, value.value, str(value.min), str(value.max)]
        if with_flex:
            row.extend([str(value.min_flex), str(value.max_flex)])
        row.extend([
            _format_percentage(value.percentage_target),
            value.comment,
            category.comment,
            category.source_url,
        ])
        rows.append(row)

    return TabularData(headers=headers, rows=rows)


def _write_export(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    target: AbstractTabularExportTarget,
    sheet_title: str,
) -> None:
    """Build the targets table and hand it to the target. Assumes an open uow
    and an already-authorised caller.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    categories = list(uow.target_categories.get_by_assembly_id(assembly_id))
    target.write_sheet(sheet_title, build_targets_table(categories))


@require_assembly_permission(can_manage_assembly)
def export_targets(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    target: AbstractTabularExportTarget,
    sheet_title: str = "",
) -> None:
    """Write an assembly's targets to the given target.

    The format is the target: a CsvExportTarget yields CSV, a Google Sheets one
    writes a worksheet. Requires manage permission, matching the other exports.

    An empty ``sheet_title`` means the default for this export kind, resolved
    here rather than as a default argument so it lands in the caller's language.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    _write_export(uow, assembly_id, target, sheet_title or default_worksheet_name(EXPORT_KIND))


@require_assembly_permission(can_manage_assembly)
def get_targets_gsheet_config(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> AssemblyExportGSheet | None:
    """The saved targets-export sheet config, or None before the first export. Manage-gated.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly_id, EXPORT_KIND)
    return config.create_detached_copy() if config else None


@require_assembly_permission(can_manage_assembly)
def export_targets_to_gsheet(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    spreadsheet_url: str,
    worksheet_name: str,
    target: AbstractGSheetExportTarget,
) -> None:
    """Write an assembly's targets to a Google Sheet and save the sheet config.

    The config is saved under its own export kind, so the next targets export
    pre-fills with this spreadsheet rather than the respondent or dashboard one.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    # Validate the destination URL BEFORE writing: gspread's URL parsing is laxer
    # than the domain validator, so validating only at config-save time would let
    # the write clear a tab of a sheet whose URL is then rejected.
    GoogleSpreadsheetURLValidator().validate_str(spreadsheet_url.strip())
    worksheet_name = worksheet_name.strip() or default_worksheet_name(EXPORT_KIND)

    # Write first so the target's result_title/result_url are populated; only
    # then persist the config, so a failed write saves nothing.
    _write_export(uow, assembly_id, target, worksheet_name)

    save_export_gsheet_config(
        uow,
        assembly_id,
        EXPORT_KIND,
        spreadsheet_url=spreadsheet_url,
        worksheet_name=worksheet_name,
        target=target,
    )
