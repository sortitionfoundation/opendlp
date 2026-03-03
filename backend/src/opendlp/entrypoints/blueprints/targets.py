"""ABOUTME: Targets blueprint for viewing and uploading target categories via CSV
ABOUTME: Provides routes for assembly-level target category management"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.service_layer.assembly_service import (
    get_assembly_with_permissions,
    get_targets_for_assembly,
    import_targets_from_csv,
)
from opendlp.service_layer.exceptions import InsufficientPermissions, InvalidSelection, NotFoundError
from opendlp.translations import gettext as _

from ..forms import UploadTargetsCsvForm

targets_bp = Blueprint("targets", __name__)


@targets_bp.route("/assemblies/<uuid:assembly_id>/targets")
@login_required
def view_assembly_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        uow = bootstrap.bootstrap()
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        uow2 = bootstrap.bootstrap()
        target_categories = get_targets_for_assembly(uow2, current_user.id, assembly_id)

        form = UploadTargetsCsvForm()

        return render_template(
            "targets/view_targets.html",
            assembly=assembly,
            target_categories=target_categories,
            form=form,
            current_tab="targets",
        )

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error viewing targets for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred"), "error")
        return redirect(url_for("main.dashboard"))


@targets_bp.route("/assemblies/<uuid:assembly_id>/targets/upload", methods=["POST"])
@login_required
def upload_targets_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    try:
        form = UploadTargetsCsvForm()

        if not form.validate_on_submit():
            uow = bootstrap.bootstrap()
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

            uow2 = bootstrap.bootstrap()
            target_categories = get_targets_for_assembly(uow2, current_user.id, assembly_id)

            return render_template(
                "targets/view_targets.html",
                assembly=assembly,
                target_categories=target_categories,
                form=form,
                current_tab="targets",
            ), 200

        csv_file = form.csv_file.data
        csv_content = csv_file.read().decode("utf-8-sig")
        filename = csv_file.filename or "unknown.csv"

        uow = bootstrap.bootstrap()
        categories = import_targets_from_csv(
            uow=uow,
            user_id=current_user.id,
            assembly_id=assembly_id,
            csv_content=csv_content,
            replace_existing=True,
        )

        total_values = sum(len(c.values) for c in categories)
        flash(
            _(
                "Successfully imported %(cats)s categories with %(vals)s values from %(file)s",
                cats=len(categories),
                vals=total_values,
                file=filename,
            ),
            "success",
        )

        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except InvalidSelection as e:
        current_app.logger.warning(f"Invalid targets CSV for assembly {assembly_id}: {e}")
        flash(_("CSV import failed: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("main.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to import targets"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except UnicodeDecodeError:
        flash(_("Could not read CSV file. Please ensure it is UTF-8 encoded."), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Upload targets error for assembly {assembly_id}: {e}")
        current_app.logger.exception("stacktrace")
        flash(_("An unexpected error occurred during import"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
