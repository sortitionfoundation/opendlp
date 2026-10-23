"""ABOUTME: Backoffice routes for CRUD operations on assembly targets
ABOUTME: Provides target viewing, editing, CSV upload, and deletion under /backoffice/assembly/*/targets"""

import contextlib
import uuid
from typing import Any

import structlog
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.blueprints.backoffice import render_assembly_data_page
from opendlp.entrypoints.decorators import require_assembly_management
from opendlp.entrypoints.save_all_parser import errors_by_field, parse_save_all_targets, pending_categories
from opendlp.entrypoints.scroll_utils import redirect_preserving_scroll
from opendlp.service_layer.assembly_service import (
    CSVUploadStatus,
    determine_data_source,
    get_assembly_gsheet,
    get_assembly_with_permissions,
    get_csv_upload_status,
    get_or_create_csv_config,
    get_tab_enabled_states,
)
from opendlp.service_layer.constants import MAX_DISTINCT_VALUES_FOR_AUTO_ADD
from opendlp.service_layer.exceptions import (
    FieldDefinitionConflictError,
    InsufficientPermissions,
    InvalidSelection,
    NotFoundError,
    ServiceLayerError,
)
from opendlp.service_layer.permissions import can_manage_assembly
from opendlp.service_layer.respondent_service import get_respondent_attribute_value_counts
from opendlp.service_layer.sortition import start_db_select_task
from opendlp.service_layer.target_checking import check_targets_detailed
from opendlp.service_layer.target_csv_import import import_targets_from_csv
from opendlp.service_layer.target_respondent_helpers import (
    build_respondent_counts,
    build_selected_counts,
    get_assembly_respondent_attribute_columns,
    get_column_distinct_counts,
)
from opendlp.service_layer.target_service import (
    TargetEditError,
    TargetLinkedError,
    TargetsNotSaved,
    add_target_value,
    create_target_category,
    delete_targets_for_assembly,
    get_targets_for_assembly,
    save_all_targets,
)
from opendlp.service_layer.target_suggestions import accept_all_suggestions, accept_suggestion
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _

from ..forms import (
    SaveAllTargetsForm,
    TargetValueForm,
    UploadTargetsCsvForm,
)

targets_bp = Blueprint("targets", __name__)

logger = structlog.get_logger(__name__)


def _percentage_from(form: TargetValueForm) -> float | None:
    """The submitted percentage as a float, or None when the field was cleared."""
    return None if form.percentage.data is None else float(form.percentage.data)


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _can_manage(assembly_id: uuid.UUID) -> bool:
    uow = bootstrap.get_flask_uow()
    with uow:
        user = uow.users.get(current_user.id)
        assembly = uow.assemblies.get(assembly_id)
        if user and assembly:
            return can_manage_assembly(user, assembly)
    return False


def _get_assembly_context(assembly_id: uuid.UUID) -> dict:
    """Get common assembly context needed for the targets page layout (tabs, data source)."""
    uow = bootstrap.get_flask_uow()
    with uow:
        gsheet = None
        # No gsheet config exists is expected for new assemblies.
        with contextlib.suppress(ServiceLayerError):
            gsheet = get_assembly_gsheet(uow, assembly_id, current_user.id)

        csv_status: CSVUploadStatus | None = None
        # No CSV data is expected for new assemblies.
        with contextlib.suppress(ServiceLayerError):
            csv_status = get_csv_upload_status(uow, current_user.id, assembly_id)

    data_source, _locked = determine_data_source(gsheet, csv_status, request.args.get("source", ""))
    targets_enabled, respondents_enabled, selection_enabled = get_tab_enabled_states(data_source, gsheet, csv_status)

    return {
        "data_source": data_source,
        "gsheet": gsheet,
        "targets_enabled": targets_enabled,
        "respondents_enabled": respondents_enabled,
        "selection_enabled": selection_enabled,
    }


@targets_bp.route("/assembly/<uuid:assembly_id>/targets")
@login_required
def view_assembly_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly targets page."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            target_categories = get_targets_for_assembly(uow, current_user.id, assembly_id)

        value_form = TargetValueForm()
        can_manage = _can_manage(assembly_id)

        attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
        respondent_counts = build_respondent_counts(assembly_id, target_categories, attribute_columns)
        selected_counts = build_selected_counts(assembly_id, target_categories, attribute_columns)
        has_selected = any(selected_counts.values())

        context = _get_assembly_context(assembly_id)

        return render_template(
            "backoffice/assembly_targets.html",
            assembly=assembly,
            assembly_id=assembly_id,
            target_categories=target_categories,
            value_form=value_form,
            can_manage=can_manage,
            all_respondent_counts=respondent_counts,
            all_selected_counts=selected_counts,
            has_selected=has_selected,
            **context,
        ), 200
    except NotFoundError as e:
        logger.warning("Assembly not found", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e))
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception(
            "View assembly targets error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while loading assembly targets"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _render_targets_upload_page(assembly_id: uuid.UUID, form: UploadTargetsCsvForm) -> ResponseReturnValue:
    """Re-render the data page so the user sees their upload error beside the form.

    The form lives on the data page rather than this blueprint's own, so this
    borrows that page's renderer. Redirecting instead would leave the reason in
    a flash message at the top of the page, away from the field it is about.
    """
    return render_assembly_data_page(assembly_id, targets_upload_form=form, preferred_source="csv"), 200


@targets_bp.route("/assembly/<uuid:assembly_id>/targets/upload", methods=["POST"])
@login_required
def upload_targets_csv(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Upload targets CSV file for an assembly."""
    form = UploadTargetsCsvForm()
    try:
        if not form.validate_on_submit():
            return _render_targets_upload_page(assembly_id, form)

        csv_file = form.csv_file.data
        csv_content = csv_file.read().decode("utf-8-sig")
        filename = csv_file.filename or "unknown.csv"

        uow = bootstrap.get_flask_uow()
        with uow:
            import_result = import_targets_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=True,
            )
            categories = import_result.categories
            import_warnings = import_result.warnings

        total_values = sum(len(c.values) for c in categories)
        flash(
            _(
                "Successfully imported %(cats)s targets with %(vals)s values from %(file)s",
                cats=len(categories),
                vals=total_values,
                file=filename,
            ),
            "success",
        )
        for warning in import_warnings:
            flash(warning, "warning")

        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except InvalidSelection as e:
        logger.warning("Invalid targets CSV", assembly_id=str(assembly_id), error=str(e))
        form.csv_file.errors.append(_("CSV import failed: %(error)s", error=str(e)))
        return _render_targets_upload_page(assembly_id, form)
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to import targets"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except UnicodeDecodeError:
        form.csv_file.errors.append(_("Could not read CSV file. Please ensure it is UTF-8 encoded."))
        return _render_targets_upload_page(assembly_id, form)
    except Exception as e:
        logger.exception("Upload targets error", assembly_id=str(assembly_id), error=str(e))
        form.csv_file.errors.append(_("An unexpected error occurred during import"))
        return _render_targets_upload_page(assembly_id, form)


@targets_bp.route("/assembly/<uuid:assembly_id>/data/delete-targets", methods=["POST"])
@login_required
def delete_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Delete all targets for an assembly, asking first when questions are linked to them."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            count = delete_targets_for_assembly(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                force_unlink=request.form.get("force_unlink") == "1",
            )

        flash(_("Targets deleted: %(count)d", count=count), "success")
        return redirect_preserving_scroll(
            url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv")
        )

    except TargetLinkedError as e:
        return _render_force_unlink_confirm(
            assembly_id,
            request.form,
            e.blocks,
            confirm_url=url_for("targets.delete_targets", assembly_id=assembly_id),
            cancel_url=url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"),
            deleting_all=True,
        )
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to delete targets",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to delete targets"), "error")
        return redirect_preserving_scroll(
            url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv")
        )
    except NotFoundError as e:
        logger.warning("Assembly not found for targets deletion", assembly_id=str(assembly_id), error=str(e))
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception(
            "Delete targets error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while deleting targets"), "error")
        return redirect_preserving_scroll(
            url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv")
        )


@targets_bp.route(
    "/assembly/<uuid:assembly_id>/targets/categories/add-from-columns",
    methods=["POST"],
)
@login_required
def add_categories_from_columns(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Bulk-create target categories from selected respondent attribute columns."""
    try:
        selected_columns = request.form.getlist("columns")
        if not selected_columns:
            flash(_("No columns selected"), "warning")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
        column_distinct_counts = get_column_distinct_counts(assembly_id, attribute_columns)

        created = []
        values_added_count = 0
        uow = bootstrap.get_flask_uow()
        # The whole bulk create is one unit of work: either every category the
        # organiser selected lands or none does.
        with uow:
            for column_name in selected_columns:
                try:
                    category = create_target_category(
                        uow=uow,
                        user_id=current_user.id,
                        assembly_id=assembly_id,
                        name=column_name,
                    )
                    created.append(column_name)

                    # Auto-add all distinct values for low-cardinality columns
                    distinct_count = column_distinct_counts.get(column_name, 0)
                    if distinct_count > 0 and distinct_count < MAX_DISTINCT_VALUES_FOR_AUTO_ADD:
                        value_counts = get_respondent_attribute_value_counts(uow, assembly_id, column_name)
                        for value_name in sorted(value_counts.keys()):
                            add_target_value(
                                uow=uow,
                                user_id=current_user.id,
                                assembly_id=assembly_id,
                                category_id=category.id,
                                value=value_name,
                                min_count=0,
                                max_count=0,
                            )
                            values_added_count += 1
                except ValueError:
                    # Category with this name may already exist; skip it
                    continue

        if not created:
            flash(_("No new targets were created"), "warning")
            return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))

        if values_added_count > 0:
            flash(
                _(
                    "Created %(count)s targets with %(values)s values: %(names)s",
                    count=len(created),
                    values=values_added_count,
                    names=", ".join(created),
                ),
                "success",
            )
        else:
            flash(
                _("Created %(count)s targets: %(names)s", count=len(created), names=", ".join(created)),
                "success",
            )

        # The new categories carry no percentages, minimums or maximums yet, so
        # the targets page is where the organiser needs to be next.
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    except (NotFoundError, InsufficientPermissions) as e:
        flash(str(e), "error")
        return redirect(url_for("backoffice.view_assembly_data", assembly_id=assembly_id, source="csv"))


@targets_bp.route("/assembly/<uuid:assembly_id>/targets/check", methods=["GET"])
@login_required
def check_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Run detailed target validation and display results."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
            check_result = check_targets_detailed(uow, current_user.id, assembly_id)
            target_categories = get_targets_for_assembly(uow, current_user.id, assembly_id)

        value_form = TargetValueForm()
        can_manage = _can_manage(assembly_id)

        attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
        respondent_counts = build_respondent_counts(assembly_id, target_categories, attribute_columns)
        selected_counts = build_selected_counts(assembly_id, target_categories, attribute_columns)
        has_selected = any(selected_counts.values())

        context = _get_assembly_context(assembly_id)

        return render_template(
            "backoffice/assembly_targets.html",
            assembly=assembly,
            assembly_id=assembly_id,
            target_categories=target_categories,
            value_form=value_form,
            can_manage=can_manage,
            all_respondent_counts=respondent_counts,
            all_selected_counts=selected_counts,
            has_selected=has_selected,
            check_result=check_result,
            # Carried through from a failed selection run (see accept_suggestions),
            # so the page offers to re-run and keeps the link alive across rechecks.
            selection_provenance=_selection_provenance(request.args),
            # "Adjust targets" on a failed run opens straight into the editor,
            # with each suggestion under the row it would change.
            editing_all=can_manage and request.args.get("edit") == "1",
            **context,
        ), 200

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception("Error checking targets", assembly_id=str(assembly_id), error=str(e))
        flash(_("An unexpected error occurred while checking targets"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


def _accept_from_form(uow: AbstractUnitOfWork, assembly_id: uuid.UUID, form: Any) -> bool:
    """Accept what the form asks for - every suggestion, or the one it names."""
    if form.get("scope") == "all":
        return accept_all_suggestions(uow, current_user.id, assembly_id)
    try:
        category_id = uuid.UUID(form.get("category_id", ""))
        value_id = uuid.UUID(form.get("value_id", ""))
    except ValueError:
        return False
    return accept_suggestion(
        uow,
        current_user.id,
        assembly_id,
        category_id,
        value_id,
        form.get("field", ""),
        comment=form.get("comment", ""),
    )


def _start_rerun(uow: AbstractUnitOfWork, assembly_id: uuid.UUID, provenance: dict[str, Any]) -> uuid.UUID | None:
    """Re-run the kind of selection that failed, unless its settings still need confirming.

    A failed test selection is re-run as a test selection, never as the real one.

    A refused start - another task writing to the assembly, or settings the
    selection cannot use - is reported and swallowed rather than raised: the
    target changes are in the same unit of work, and raising would roll them back.
    """
    csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)
    if not csv_config.settings_confirmed:
        flash(_("Please review and save the selection settings before running selection"), "warning")
        return None
    try:
        task_id: uuid.UUID = start_db_select_task(
            uow, current_user.id, assembly_id, test_selection=provenance.get("test") == "1"
        )
    except InvalidSelection as e:
        # SelectionAlreadyRunning is an InvalidSelection too. Both are raised before
        # the run record is written, so the session is clean and the targets commit.
        flash(_("Could not start selection task: %(error)s", error=str(e)), "error")
        return None
    return task_id


def _redirect_after_save(assembly_id: uuid.UUID, task_id: uuid.UUID | None, recheck_url: str) -> ResponseReturnValue:
    """To the new selection run if one was started, otherwise back to the check."""
    if task_id is not None:
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, current_selection=task_id))
    return redirect_preserving_scroll(recheck_url)


def _selection_provenance(params: Any) -> dict[str, Any]:
    """What marks a visit as coming from a failed selection run, as url or form params.

    ``from=selection`` and the ``run_id``, plus ``test=1`` when the run was a test
    selection - the same flag the selection page starts a test run with - so a
    re-run starts the same kind of selection that failed. Empty for any other
    visit, so it can be splatted into ``url_for`` or rendered as hidden fields.

    A ``run_id`` that is not a UUID drops the provenance altogether. It comes from
    the address bar and ends up inside an Alpine expression on the targets page,
    where a quote in it would break out of the string it sits in.
    """
    if params.get("from") != "selection":
        return {}
    try:
        run_id = uuid.UUID(params.get("run_id", ""))
    except ValueError:
        return {}
    provenance = {"from": "selection", "run_id": str(run_id)}
    if params.get("test") == "1":
        provenance["test"] = "1"
    return provenance


@targets_bp.route("/assembly/<uuid:assembly_id>/targets/accept-suggestions", methods=["POST"])
@login_required
@require_assembly_management
def accept_suggestions(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Apply one or all of the algorithm's recommended target changes.

    The suggestions are re-derived from a fresh check rather than trusted from
    the form, so a stale page cannot apply a number the check no longer
    recommends (see `target_suggestions`). Each applied
    value gets a comment recording where the change came from; for a single
    accept the organiser may have edited that comment before saving.

    ``then=run`` re-runs the failed selection after saving - a test run as a test
    run - and is only honoured when the organiser arrived from one
    (``from=selection``).
    """
    provenance = _selection_provenance(request.form)
    run_after = bool(provenance) and request.form.get("then") == "run"
    recheck_url = url_for("targets.check_targets", assembly_id=assembly_id, **provenance)

    try:
        uow = bootstrap.get_flask_uow()
        task_id = None
        with uow:
            if not _accept_from_form(uow, assembly_id, request.form):
                flash(_("That suggestion is no longer available. The targets have been re-checked."), "warning")
                return redirect_preserving_scroll(recheck_url)

            if run_after:
                task_id = _start_rerun(uow, assembly_id, provenance)

        flash(_("Recommended changes applied."), "success")
        return _redirect_after_save(assembly_id, task_id, recheck_url)

    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions:
        flash(_("You don't have permission to manage this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception("Error accepting target suggestions", assembly_id=str(assembly_id), error=str(e))
        flash(_("An unexpected error occurred while applying the recommended changes"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))


def _render_targets_edit_errors(
    assembly_id: uuid.UUID,
    form_data: Any,
    errors: list[TargetEditError],
) -> ResponseReturnValue:
    """Re-render the bulk edit form as submitted, each error against its field.

    Redirecting instead would land the user on the read-only page having thrown
    away every edit they had made, leaving the message in a toast with nothing
    to point at.
    """
    uow = bootstrap.get_flask_uow()
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
        target_categories = get_targets_for_assembly(uow, current_user.id, assembly_id)

    attribute_columns = get_assembly_respondent_attribute_columns(assembly_id)
    selected_counts = build_selected_counts(assembly_id, target_categories, attribute_columns)
    context = _get_assembly_context(assembly_id)

    flash(_("Your targets were not saved. Please correct the errors below."), "error")
    return render_template(
        "backoffice/assembly_targets.html",
        assembly=assembly,
        assembly_id=assembly_id,
        target_categories=target_categories,
        pending_categories=pending_categories(form_data),
        field_errors=errors_by_field(errors),
        editing_all=True,
        selection_provenance=_selection_provenance(form_data),
        value_form=TargetValueForm(),
        can_manage=_can_manage(assembly_id),
        all_respondent_counts=build_respondent_counts(assembly_id, target_categories, attribute_columns),
        all_selected_counts=selected_counts,
        has_selected=any(selected_counts.values()),
        **context,
    ), 200


def _render_force_unlink_confirm(
    assembly_id: uuid.UUID,
    form_data: Any,
    blocks: list[Any],
    confirm_url: str = "",
    cancel_url: str = "",
    deleting_all: bool = False,
) -> ResponseReturnValue:
    """Ask before a rename/delete unlinks the fields feeding those targets.

    The whole submission is echoed back as hidden inputs so confirming
    resubmits exactly what was typed, plus force_unlink=1. It goes back to the
    save-all route unless ``confirm_url`` says otherwise.
    """
    uow = bootstrap.get_flask_uow()
    with uow:
        assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)
    resubmit_fields = [(key, value) for key in form_data for value in form_data.getlist(key) if key != "csrf_token"]
    return render_template(
        "backoffice/targets_force_unlink_confirm.html",
        assembly=assembly,
        assembly_id=assembly_id,
        blocks=blocks,
        resubmit_fields=resubmit_fields,
        confirm_url=confirm_url or url_for("targets.save_all", assembly_id=assembly_id),
        cancel_url=cancel_url or url_for("targets.view_assembly_targets", assembly_id=assembly_id),
        deleting_all=deleting_all,
    ), 200


@targets_bp.route("/assembly/<uuid:assembly_id>/targets/save-all", methods=["POST"])
@login_required
def save_all(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Apply every edit on the targets page in one operation."""
    form = SaveAllTargetsForm()
    if not form.validate_on_submit():
        flash(_("Please try again"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))

    try:
        edits, errors = parse_save_all_targets(request.form)
        if errors:
            return _render_targets_edit_errors(assembly_id, request.form, errors)

        provenance = _selection_provenance(request.form)
        run_after = bool(provenance) and request.form.get("then") == "run"
        task_id = None
        uow = bootstrap.get_flask_uow()
        with uow:
            save_all_targets(
                uow,
                current_user.id,
                assembly_id,
                edits,
                force_unlink=request.form.get("force_unlink") == "1",
            )
            if run_after:
                task_id = _start_rerun(uow, assembly_id, provenance)

        flash(_("Targets saved"), "success")
        # The detailed check is the whole point of saving: land on the page that
        # runs it, so its annotations arrive without anyone asking for them.
        return _redirect_after_save(
            assembly_id, task_id, url_for("targets.check_targets", assembly_id=assembly_id, **provenance)
        )

    except TargetLinkedError as e:
        return _render_force_unlink_confirm(assembly_id, request.form, e.blocks)
    except TargetsNotSaved as e:
        return _render_targets_edit_errors(assembly_id, request.form, e.errors)
    except FieldDefinitionConflictError as e:
        # Renaming a target re-keys its computed question, which can collide with an existing one.
        flash(e.user_msg(), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except (ValueError, NotFoundError) as e:
        flash(_("Error: %(error)s", error=str(e)), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to edit these targets"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
    except Exception as e:
        # A whole page of edits is at stake, so an unexpected failure gets a
        # flash and the page back, not a stack trace.
        logger.exception(
            "Save all targets error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while saving the targets"), "error")
        return redirect(url_for("targets.view_assembly_targets", assembly_id=assembly_id))
