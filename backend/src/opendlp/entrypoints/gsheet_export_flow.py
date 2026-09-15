"""ABOUTME: Shared entrypoint flow for exporting a table to a caller-supplied Google Sheet
ABOUTME: Reads the destination from the form, guards on credentials, runs the export and flashes the outcome"""

from collections.abc import Callable

import structlog
from flask import current_app, flash, redirect, request
from flask.typing import ResponseReturnValue

from opendlp.adapters.tabular_export import AbstractGSheetExportTarget, ExportTargetError
from opendlp.entrypoints.context_processors import get_service_account_email
from opendlp.translations import gettext as _

logger = structlog.get_logger(__name__)


def run_gsheet_export_flow(
    *,
    redirect_url: str,
    export: Callable[[str, str, AbstractGSheetExportTarget], None],
    success_message: str,
    log_event: str,
    log_context: dict[str, str],
) -> ResponseReturnValue:
    """Run a Google Sheets export from a modal POST, shared by the export routes.

    Handles everything around the export itself: the no-service-account guard,
    reading and requiring the destination spreadsheet URL, building the target
    via the app's injected factory, and translating ValueError (rejected URL)
    and ExportTargetError (unwritable sheet) into flashes.

    ``export`` is a callable of (spreadsheet_url, worksheet_name, target) —
    the caller wraps its service function there, including opening the
    UnitOfWork, so this helper stays free of uow handling and the caller's
    permission errors propagate to its own handlers. An empty worksheet name
    is passed through: each export service resolves its own default.
    """
    service_account_email = get_service_account_email()
    if not service_account_email:
        # The modal disables the option in this state; reaching here means a
        # hand-crafted POST or credentials removed since the modal rendered.
        flash(_("Google Sheets export is unavailable: no Google service account is configured."), "error")
        return redirect(redirect_url)

    spreadsheet_url = request.form.get("spreadsheet_url", "").strip()
    worksheet_name = request.form.get("worksheet_name", "").strip()
    if not spreadsheet_url:
        flash(_("A spreadsheet URL is required to export to Google Sheets"), "error")
        return redirect(redirect_url)

    # The Google Sheets target is injected via an app factory (registered in
    # flask_app.py, overridable in tests) because writing to it calls the real
    # Google Sheets API, so tests substitute a fake.
    factory = current_app.extensions["gsheet_export_target_factory"]
    target = factory(spreadsheet_url)
    try:
        export(spreadsheet_url, worksheet_name, target)
    except ValueError as e:
        # A malformed spreadsheet URL is rejected by the domain validator.
        flash(_("Could not export to Google Sheets: %(error)s", error=str(e)), "error")
        return redirect(redirect_url)
    except ExportTargetError as e:
        # The sheet could not be written — typically it is not shared with the
        # service account, or the URL points at a sheet that does not exist.
        logger.warning(log_event, error=str(e), **log_context)
        flash(
            _(
                "Could not write to the spreadsheet. Check the URL is correct and that "
                "the spreadsheet is shared with %(email)s.",
                email=service_account_email,
            ),
            "error",
        )
        return redirect(redirect_url)

    flash(success_message, "success")
    return redirect(redirect_url)
