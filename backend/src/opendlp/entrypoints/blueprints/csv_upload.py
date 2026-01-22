"""ABOUTME: Blueprint for CSV file upload functionality for assembly participant data
ABOUTME: Provides routes for uploading, previewing, and managing CSV data sources"""

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
                filename = file.filename or "unknown"
                flash(_("File '%(filename)s' uploaded successfully!", filename=filename), "success")
                return redirect(url_for("csv_upload.upload_csv", assembly_id=assembly_id))

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
