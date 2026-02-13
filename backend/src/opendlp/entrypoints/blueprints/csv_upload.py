"""ABOUTME: Blueprint for CSV file upload functionality for assembly participant data
ABOUTME: Provides routes for uploading, previewing, and managing CSV data sources"""

import csv
import io
import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.forms import CSVUploadForm
from opendlp.service_layer.assembly_service import get_assembly_with_permissions
from opendlp.service_layer.exceptions import InsufficientPermissions, NotFoundError
from opendlp.translations import gettext as _

csv_upload_bp = Blueprint("csv_upload", __name__)

# Number of preview rows to show
PREVIEW_ROW_COUNT = 5


def parse_csv_file(file_storage: object) -> tuple[list[str], list[list[str]], int]:
    """
    Parse a CSV file and return columns, preview rows, and total row count.

    Args:
        file_storage: Flask FileStorage object

    Returns:
        Tuple of (columns, preview_rows, total_row_count)

    Raises:
        ValueError: If the CSV file is empty or invalid
    """
    # Read file content and decode
    content = file_storage.read().decode("utf-8-sig")  # type: ignore[union-attr]
    file_storage.seek(0)  # type: ignore[union-attr] # Reset for potential future reads

    if not content.strip():
        raise ValueError(_("The CSV file is empty"))

    # Parse CSV
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)

    if len(rows) < 1:
        raise ValueError(_("The CSV file has no header row"))

    columns = rows[0]
    if not columns or all(not col.strip() for col in columns):
        raise ValueError(_("The CSV file has no valid column headers"))

    # Get data rows (excluding header)
    data_rows = rows[1:]
    total_row_count = len(data_rows)

    # Get preview rows
    preview_rows = data_rows[:PREVIEW_ROW_COUNT]

    return columns, preview_rows, total_row_count


@csv_upload_bp.route("/assemblies/<uuid:assembly_id>/csv/upload", methods=["GET", "POST"])
@login_required
def upload_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Display CSV upload page and handle file upload."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        form = CSVUploadForm()

        if form.validate_on_submit():
            file = form.csv_file.data
            if file:
                try:
                    columns, preview_rows, total_row_count = parse_csv_file(file)
                    filename = file.filename or "unknown"

                    return render_template(
                        "csv_upload/preview.html",
                        assembly=assembly,
                        current_tab="data",
                        filename=filename,
                        columns=columns,
                        preview_rows=preview_rows,
                        total_row_count=total_row_count,
                        preview_row_count=len(preview_rows),
                    ), 200

                except ValueError as e:
                    flash(str(e), "error")
                except UnicodeDecodeError:
                    flash(_("Could not read the CSV file. Please ensure it is UTF-8 encoded."), "error")

        return render_template(
            "csv_upload/upload.html",
            assembly=assembly,
            current_tab="data",
            form=form,
        ), 200

    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"CSV upload page error for assembly {assembly_id} user {current_user.id}: {e}")
        current_app.logger.exception("stacktrace")
        return render_template("errors/500.html"), 500
