"""ABOUTME: Saves where an assembly's Google Sheet export of a given kind writes to
ABOUTME: Shared by the respondent and dashboard exports, which save the same way"""

from typing import TYPE_CHECKING

from opendlp.domain.assembly_export_gsheet import AssemblyExportGSheet

if TYPE_CHECKING:
    import uuid

    from opendlp.adapters.tabular_export import AbstractGSheetExportTarget
    from opendlp.domain.value_objects import GSheetExportKind
    from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


def save_export_gsheet_config(
    uow: "AbstractUnitOfWork",
    assembly_id: "uuid.UUID",
    export_kind: "GSheetExportKind",
    *,
    spreadsheet_url: str,
    worksheet_name: str,
    target: "AbstractGSheetExportTarget",
) -> None:
    """Record where this kind of export writes, so the next one can pre-fill the form.

    Creates the row on the first export of a kind and updates it afterwards; an
    assembly has at most one per kind. ``spreadsheet_title`` and ``worksheet_url``
    are read off ``target``, so this must be called *after* the write, once the
    target has been where it is describing.

    Commits, because saving the config is the last thing every export does. The
    caller is expected to manage the ``uow`` context (``with uow: ...``).
    """
    config = uow.assembly_export_gsheets.get_by_assembly_and_kind(assembly_id, export_kind)
    if config is None:
        config = AssemblyExportGSheet(
            assembly_id=assembly_id,
            export_kind=export_kind,
            url=spreadsheet_url,
            worksheet_name=worksheet_name,
            spreadsheet_title=target.result_title,
            worksheet_url=target.result_url,
        )
        uow.assembly_export_gsheets.add(config)
    else:
        config.update_values(
            url=spreadsheet_url,
            worksheet_name=worksheet_name,
            spreadsheet_title=target.result_title,
            worksheet_url=target.result_url,
        )
    uow.commit()
