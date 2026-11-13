"""ABOUTME: The data source dialogs: creating a project in three steps, and a project's data source settings
ABOUTME: One form drawn by the server at every step, swapped into the page's dialog host over htmx"""

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from flask import Blueprint, flash, make_response, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from werkzeug.datastructures import MultiDict

from opendlp import bootstrap
from opendlp.config import get_max_csv_upload_bytes, get_max_csv_upload_mb
from opendlp.domain.value_objects import DataSource, RespondentsSource, TargetsSource
from opendlp.entrypoints.context_processors import get_service_account_email
from opendlp.entrypoints.decorators import require_assembly_management, require_create_assembly
from opendlp.entrypoints.forms import (
    CreateAssemblyGSheetForm,
    EditAssemblyGSheetForm,
    ProjectDetailsStepForm,
    UploadTargetsCsvForm,
)
from opendlp.service_layer.assembly_service import (
    GSHEET_SOURCE,
    OPENDLP_SOURCE,
    AssemblyNavContext,
    add_assembly_gsheet,
    get_assembly_nav_context,
    get_user_assemblies,
    set_data_sources,
    update_assembly_gsheet,
    update_csv_config,
)
from opendlp.service_layer.csv_upload_stash import StashedUpload
from opendlp.service_layer.csv_upload_stash import stash as stash_pending_upload
from opendlp.service_layer.exceptions import InvalidSelection
from opendlp.service_layer.gsheet_access_check import forget_cached_result
from opendlp.service_layer.project_creation_service import (
    ProjectDetails,
    create_project,
    create_project_with_gsheet,
    create_project_with_respondents_csv,
    create_project_with_targets_csv,
)
from opendlp.service_layer.respondent_field_schema_service import compute_diff_for_pending_csv
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.target_csv_import import import_targets_from_csv
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _

data_source_bp = Blueprint("data_source", __name__)

logger = structlog.get_logger(__name__)

MODE_CREATE = "create"
MODE_SETTINGS = "settings"

DIALOG_TEMPLATE = "backoffice/data_source/_dialog.html"

# How many skipped rows an upload names in the dialog; the rest go to the logs.
_MAX_NOTICE_LINES = 20

_GSHEET_FIELDS = (
    "url",
    "team",
    "select_registrants_tab",
    "select_targets_tab",
    "replace_registrants_tab",
    "replace_targets_tab",
    "already_selected_tab",
    "id_column",
    "check_same_address",
    "generate_remaining_tab",
    "check_same_address_cols_string",
    "columns_to_keep_string",
)

_STORED_LOCATION = {GSHEET_SOURCE: DataSource.GSHEET, OPENDLP_SOURCE: DataSource.OPENDLP}


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _redirect(location: str) -> ResponseReturnValue:
    """Redirect, telling htmx to load the page rather than swap it into the dialog host."""
    if _is_htmx():
        response = make_response("", 200)
        response.headers["HX-Redirect"] = location
        return response
    return redirect(location)


def _details_url(assembly_id: uuid.UUID, **params: Any) -> str:
    return url_for("backoffice.view_assembly", assembly_id=assembly_id, **params)


def _posted_choice[E: (TargetsSource, RespondentsSource)](enum_class: type[E], raw: str | None, default: E) -> E:
    """A dropdown's value as its enum, falling back to `default` for anything unrecognised."""
    if raw is None:
        return default
    try:
        return enum_class(raw)
    except ValueError:
        return default


def _posted_location(posted: MultiDict[str, str], default: str = OPENDLP_SOURCE) -> str:
    location = posted.get("location", default)
    return location if location in (GSHEET_SOURCE, OPENDLP_SOURCE) else default


def _gsheet_settings(form: CreateAssemblyGSheetForm | EditAssemblyGSheetForm) -> dict[str, Any]:
    return {name: getattr(form, name).data for name in _GSHEET_FIELDS}


def _warn_if_no_columns_to_keep(form: CreateAssemblyGSheetForm | EditAssemblyGSheetForm) -> None:
    """A soft warning: a team preset fills the columns in, a custom set-up may have left them empty."""
    team = form.team.data or ""
    has_team_defaults = bool(team) and team != "other"
    if not (form.columns_to_keep_string.data or "").strip() and not has_team_defaults:
        flash(
            _(
                "Warning: No columns to keep specified. "
                "This means the output will only include respondent data columns "
                "used for the targets and address checking. Is this intentional?"
            ),
            "warning",
        )


def _unbound_gsheet_form(nav: AssemblyNavContext | None) -> CreateAssemblyGSheetForm | EditAssemblyGSheetForm:
    """The sheet form as first shown: the saved settings, or the defaults for a new sheet."""
    if nav is None or nav.gsheet is None:
        return CreateAssemblyGSheetForm(formdata=None)
    settings = nav.assembly.selection_settings
    return EditAssemblyGSheetForm(
        formdata=None,
        obj=nav.gsheet,
        id_column=settings.id_column if settings else "",
        check_same_address=settings.check_same_address if settings else True,
        check_same_address_cols_string=settings.check_same_address_cols_string if settings else "",
        columns_to_keep_string=settings.columns_to_keep_string if settings else "",
    )


def _gsheet_form_for(
    nav: AssemblyNavContext | None, posted: MultiDict[str, str]
) -> CreateAssemblyGSheetForm | EditAssemblyGSheetForm:
    """The sheet form carrying what was typed, when this request carried the sheet's fields."""
    if "url" not in posted:
        return _unbound_gsheet_form(nav)
    if nav is not None and nav.gsheet is not None:
        return EditAssemblyGSheetForm()
    return CreateAssemblyGSheetForm()


def _base_context(posted: MultiDict[str, str], extra: dict[str, Any]) -> dict[str, Any]:
    return {
        "targets_errors": [],
        "respondents_errors": [],
        "targets_notices": [],
        "respondents_notices": [],
        "form_error": "",
        "dirty": posted.get("dirty") == "1",
        "service_account_email": get_service_account_email(),
        **extra,
    }


def new_project_dialog_context(
    step: int,
    details_form: ProjectDetailsStepForm,
    posted: MultiDict[str, str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """What the create dialog renders from while the project does not exist yet."""
    posted = posted if posted is not None else MultiDict()
    location = _posted_location(posted)
    context = _base_context(posted, extra)
    context.setdefault("gsheet_form", _gsheet_form_for(None, posted) if location == GSHEET_SOURCE else None)
    return {
        "mode": MODE_CREATE,
        "step": step,
        "assembly": None,
        "details_form": details_form,
        "location": location,
        "locked": False,
        "targets_source": _posted_choice(TargetsSource, posted.get("targets_source"), TargetsSource.UNDECIDED),
        "respondents_source": _posted_choice(
            RespondentsSource, posted.get("respondents_source"), RespondentsSource.UNDECIDED
        ),
        "targets_count": 0,
        "respondents_count": 0,
        "csv_config": None,
        "gsheet": None,
        "close_url": url_for("backoffice.dashboard"),
        "urls": {
            "step": url_for("data_source.new_project_step"),
            "save": url_for("data_source.new_project_save"),
            "upload_targets": url_for("data_source.new_project_upload_targets"),
            "upload_respondents": url_for("data_source.new_project_upload_respondents"),
        },
        **context,
    }


def project_dialog_context(
    uow: AbstractUnitOfWork,
    assembly_id: uuid.UUID,
    mode: str = MODE_SETTINGS,
    posted: MultiDict[str, str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """What either dialog renders from once the project exists.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    posted = posted if posted is not None else MultiDict()
    nav = get_assembly_nav_context(uow, current_user.id, assembly_id)
    location = nav.data_source if nav.data_source_locked else _posted_location(posted, nav.data_source)
    context = _base_context(posted, extra)
    context.setdefault("gsheet_form", _gsheet_form_for(nav, posted) if location == GSHEET_SOURCE else None)
    return {
        "mode": mode,
        "step": 3,
        "assembly": nav.assembly,
        "details_form": None,
        "location": location,
        "locked": nav.data_source_locked,
        "targets_source": _posted_choice(TargetsSource, posted.get("targets_source"), nav.assembly.targets_source),
        "respondents_source": _posted_choice(
            RespondentsSource, posted.get("respondents_source"), nav.assembly.respondents_source
        ),
        "targets_count": nav.csv_status.targets_count,
        "respondents_count": nav.csv_status.respondents_count,
        "csv_config": nav.csv_status.csv_config,
        "gsheet": nav.gsheet,
        "close_url": _details_url(assembly_id),
        "urls": {
            "refresh": url_for("data_source.refresh", assembly_id=assembly_id),
            "save": url_for("data_source.save", assembly_id=assembly_id),
            "upload_targets": url_for("data_source.upload_targets", assembly_id=assembly_id),
            "upload_respondents": url_for("data_source.upload_respondents", assembly_id=assembly_id),
            "delete_targets": url_for("targets.delete_targets", assembly_id=assembly_id),
            "delete_respondents": url_for("respondents.delete_respondents", assembly_id=assembly_id),
            "remove_gsheet": url_for("gsheets.delete_gsheet_config", assembly_id=assembly_id),
        },
        **context,
    }


def _posted_mode() -> str:
    return MODE_CREATE if request.form.get("dialog") == MODE_CREATE else MODE_SETTINGS


def _render_project_dialog(assembly_id: uuid.UUID, status: int = 200, **extra: Any) -> ResponseReturnValue:
    """The dialog for an existing project, as this request left it."""
    mode = extra.pop("mode", None) or _posted_mode()
    uow = bootstrap.get_flask_uow()
    with uow:
        context = project_dialog_context(uow, assembly_id, mode=mode, posted=request.form, **extra)
    return render_template(DIALOG_TEMPLATE, ds=context), status


def _render_new_project_dialog(step: int, status: int = 200, **extra: Any) -> ResponseReturnValue:
    details_form = extra.pop("details_form", None) or ProjectDetailsStepForm()
    context = new_project_dialog_context(step, details_form, posted=request.form, **extra)
    return render_template(DIALOG_TEMPLATE, ds=context), status


def _read_targets_upload() -> tuple[str, list[str]]:
    """The uploaded targets CSV as text, or the reasons it cannot be read."""
    form = UploadTargetsCsvForm()
    if not form.validate_on_submit():
        return "", [str(error) for errors in form.errors.values() for error in errors]
    try:
        return form.csv_file.data.read().decode("utf-8-sig"), []
    except UnicodeDecodeError:
        return "", [_("Could not read CSV file. Please ensure it is UTF-8 encoded.")]


def _read_respondents_upload() -> tuple[str, str, list[str]]:
    """The uploaded respondents CSV as (text, filename), or the reasons it cannot be read."""
    file = request.files.get("file")
    if file is None or not file.filename:
        return "", "", [_("Please select a CSV file to upload")]
    raw = file.read()
    if len(raw) > get_max_csv_upload_bytes():
        logger.warning("Rejected oversized CSV upload", size_bytes=len(raw), limit_bytes=get_max_csv_upload_bytes())
        return (
            "",
            "",
            [
                _(
                    "CSV is too large: limit is %(limit)d MB. Update MAX_CSV_UPLOAD_MB if a larger file is needed.",
                    limit=get_max_csv_upload_mb(),
                )
            ],
        )
    try:
        return raw.decode("utf-8-sig"), file.filename, []
    except UnicodeDecodeError:
        return "", "", [_("Could not read CSV file. Please ensure it is UTF-8 encoded.")]


def _skipped_row_notices(errors: list[str]) -> list[str]:
    """The rows an import skipped, capped so the dialog stays readable."""
    if not errors:
        return []
    notices = [_("Some rows were not imported:"), *errors[:_MAX_NOTICE_LINES]]
    if len(errors) > _MAX_NOTICE_LINES:
        notices.append(
            _(
                "… and %(count)d more (see the server logs for the full list)",
                count=len(errors) - _MAX_NOTICE_LINES,
            )
        )
    return notices


def _project_details(form: ProjectDetailsStepForm) -> ProjectDetails:
    return ProjectDetails(
        title=form.title.data or "",
        question=form.question.data or "",
        number_to_select=form.number_to_select.data or 0,
    )


def _flash_created(title: str) -> None:
    flash(_("Project '%(title)s' created successfully", title=title), "success")


# --- Creating a project -----------------------------------------------------


@data_source_bp.route("/project/new")
@login_required
@require_create_assembly
def new_project() -> ResponseReturnValue:
    """The create dialog at its first step.

    Over htmx the dialog alone, for the dashboard's dialog host. Without htmx
    the dashboard with the dialog open, so the address works as a link.
    """
    context = new_project_dialog_context(1, ProjectDetailsStepForm(formdata=None))
    if _is_htmx():
        return render_template(DIALOG_TEMPLATE, ds=context), 200
    uow = bootstrap.get_flask_uow()
    with uow:
        assemblies = get_user_assemblies(uow, current_user.id)
    return render_template("backoffice/dashboard.html", assemblies=assemblies, project_dialog=context), 200


@data_source_bp.route("/project/new/step", methods=["POST"])
@login_required
@require_create_assembly
def new_project_step() -> ResponseReturnValue:
    """Move between the steps. Nothing is written: what was typed rides along in the form."""
    details_form = ProjectDetailsStepForm()
    try:
        current = int(request.form.get("step", "1"))
    except ValueError:
        current = 1
    going_back = request.form.get("go") == "back"
    if not going_back and not details_form.validate():
        return _render_new_project_dialog(1, status=422, details_form=details_form)
    target = max(1, min(3, current + (-1 if going_back else 1)))
    return _render_new_project_dialog(target, details_form=details_form)


@data_source_bp.route("/project/new/save", methods=["POST"])
@login_required
@require_create_assembly
def new_project_save() -> ResponseReturnValue:
    """Create the project from the last step, with a Google Sheet's settings if that is where its data lives."""
    details_form = ProjectDetailsStepForm()
    if not details_form.validate():
        return _render_new_project_dialog(1, status=422, details_form=details_form)
    details = _project_details(details_form)
    location = _posted_location(request.form)

    gsheet_form = None
    if location == GSHEET_SOURCE:
        gsheet_form = CreateAssemblyGSheetForm()
        if not gsheet_form.validate():
            return _render_new_project_dialog(3, status=422, details_form=details_form, gsheet_form=gsheet_form)

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            if gsheet_form is not None:
                assembly = create_project_with_gsheet(uow, current_user.id, details, _gsheet_settings(gsheet_form))
            else:
                assembly = create_project(
                    uow,
                    current_user.id,
                    details,
                    data_source=DataSource.OPENDLP,
                    targets_source=_posted_choice(
                        TargetsSource, request.form.get("targets_source"), TargetsSource.UNDECIDED
                    ),
                    respondents_source=_posted_choice(
                        RespondentsSource, request.form.get("respondents_source"), RespondentsSource.UNDECIDED
                    ),
                )
    except Exception as e:
        logger.exception("Create project error", user_id=str(current_user.id), error=str(e))
        return _render_new_project_dialog(
            3,
            status=422,
            details_form=details_form,
            gsheet_form=gsheet_form,
            form_error=_("An error occurred while creating the project"),
        )

    _flash_created(assembly.title)
    if gsheet_form is not None:
        _warn_if_no_columns_to_keep(gsheet_form)
        return _redirect(_details_url(assembly.id, check=1))
    return _redirect(_details_url(assembly.id))


@data_source_bp.route("/project/new/upload-targets", methods=["POST"])
@login_required
@require_create_assembly
def new_project_upload_targets() -> ResponseReturnValue:
    """Create the project and import its targets, or neither: a refused file leaves nothing behind."""
    details_form = ProjectDetailsStepForm()
    if not details_form.validate():
        return _render_new_project_dialog(1, status=422, details_form=details_form)
    csv_content, errors = _read_targets_upload()
    if errors:
        return _render_new_project_dialog(3, status=422, details_form=details_form, targets_errors=errors)

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assembly, result = create_project_with_targets_csv(
                uow,
                current_user.id,
                _project_details(details_form),
                csv_content,
                respondents_source=_posted_choice(
                    RespondentsSource, request.form.get("respondents_source"), RespondentsSource.UNDECIDED
                ),
            )
            warnings = list(result.warnings)
    except InvalidSelection as e:
        logger.warning("Invalid targets CSV for a new project", user_id=str(current_user.id), error=str(e))
        return _render_new_project_dialog(
            3,
            status=422,
            details_form=details_form,
            targets_errors=[_("CSV import failed: %(error)s", error=str(e))],
        )
    except Exception as e:
        logger.exception("Create project with targets error", user_id=str(current_user.id), error=str(e))
        return _render_new_project_dialog(
            3,
            status=422,
            details_form=details_form,
            targets_errors=[_("An unexpected error occurred during import")],
        )

    _flash_created(assembly.title)
    return _render_project_dialog(assembly.id, mode=MODE_CREATE, targets_notices=warnings, dirty=False)


@data_source_bp.route("/project/new/upload-respondents", methods=["POST"])
@login_required
@require_create_assembly
def new_project_upload_respondents() -> ResponseReturnValue:
    """Create the project and import its respondents, or neither: a refused file leaves nothing behind."""
    details_form = ProjectDetailsStepForm()
    if not details_form.validate():
        return _render_new_project_dialog(1, status=422, details_form=details_form)
    csv_content, filename, errors = _read_respondents_upload()
    if errors:
        return _render_new_project_dialog(3, status=422, details_form=details_form, respondents_errors=errors)

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assembly, _respondents, skipped = create_project_with_respondents_csv(
                uow,
                current_user.id,
                _project_details(details_form),
                csv_content,
                id_column=request.form.get("id_column", "").strip() or None,
                filename=filename,
                targets_source=_posted_choice(
                    TargetsSource, request.form.get("targets_source"), TargetsSource.UNDECIDED
                ),
            )
    except InvalidSelection as e:
        logger.warning("Invalid respondents CSV for a new project", user_id=str(current_user.id), error=str(e))
        return _render_new_project_dialog(
            3,
            status=422,
            details_form=details_form,
            respondents_errors=[_("Invalid CSV format: %(error)s", error=e.user_msg())],
        )
    except Exception as e:
        logger.exception("Create project with respondents error", user_id=str(current_user.id), error=str(e))
        return _render_new_project_dialog(
            3,
            status=422,
            details_form=details_form,
            respondents_errors=[_("An error occurred while uploading respondents")],
        )

    if skipped:
        logger.warning(
            "respondent CSV import completed with warnings",
            assembly_id=str(assembly.id),
            error_count=len(skipped),
            errors=skipped,
        )
    _flash_created(assembly.title)
    return _render_project_dialog(
        assembly.id, mode=MODE_CREATE, respondents_notices=_skipped_row_notices(skipped), dirty=False
    )


# --- An existing project ----------------------------------------------------


@data_source_bp.route("/project/<uuid:assembly_id>/data-source")
@login_required
@require_assembly_management
def settings(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """The data source settings dialog, for the project details page's dialog host."""
    if not _is_htmx():
        return redirect(_details_url(assembly_id, data_source=1))
    uow = bootstrap.get_flask_uow()
    with uow:
        context = project_dialog_context(uow, assembly_id)
    return render_template(DIALOG_TEMPLATE, ds=context), 200


@data_source_bp.route("/project/<uuid:assembly_id>/data-source/refresh", methods=["POST"])
@login_required
@require_assembly_management
def refresh(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Redraw the dialog for the location just chosen. Nothing is written."""
    return _render_project_dialog(assembly_id)


def _refuse_unless_in_opendlp(assembly_id: uuid.UUID) -> ResponseReturnValue | None:
    """A CSV cannot go into a project whose data is managed in a Google Sheet."""
    uow = bootstrap.get_flask_uow()
    with uow:
        nav = get_assembly_nav_context(uow, current_user.id, assembly_id)
    if nav.data_source_locked and nav.data_source == GSHEET_SOURCE:
        return _render_project_dialog(
            assembly_id,
            status=422,
            form_error=_("This project's data is managed in Google Sheets, so a CSV cannot be imported."),
        )
    return None


@data_source_bp.route("/project/<uuid:assembly_id>/data-source/upload-targets", methods=["POST"])
@login_required
@require_assembly_management
def upload_targets(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Import targets from a CSV, replacing any the project has."""
    refusal = _refuse_unless_in_opendlp(assembly_id)
    if refusal is not None:
        return refusal
    csv_content, errors = _read_targets_upload()
    if errors:
        return _render_project_dialog(assembly_id, status=422, targets_errors=errors)

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            result = import_targets_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=True,
            )
            warnings = list(result.warnings)
            set_data_sources(
                uow, current_user.id, assembly_id, data_source=DataSource.OPENDLP, targets_source=TargetsSource.CSV
            )
    except InvalidSelection as e:
        logger.warning("Invalid targets CSV", assembly_id=str(assembly_id), error=str(e))
        return _render_project_dialog(
            assembly_id, status=422, targets_errors=[_("CSV import failed: %(error)s", error=str(e))]
        )
    except Exception as e:
        logger.exception("Upload targets error", assembly_id=str(assembly_id), error=str(e))
        return _render_project_dialog(
            assembly_id, status=422, targets_errors=[_("An unexpected error occurred during import")]
        )

    return _render_project_dialog(assembly_id, targets_notices=warnings, dirty=False)


@data_source_bp.route("/project/<uuid:assembly_id>/data-source/upload-respondents", methods=["POST"])
@login_required
@require_assembly_management
def upload_respondents(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Import respondents from a CSV, asking first when the file's columns differ from the project's questions."""
    refusal = _refuse_unless_in_opendlp(assembly_id)
    if refusal is not None:
        return refusal
    csv_content, filename, errors = _read_respondents_upload()
    if errors:
        return _render_project_dialog(assembly_id, status=422, respondents_errors=errors)
    id_column = request.form.get("id_column", "").strip() or None

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            diff = compute_diff_for_pending_csv(uow, current_user.id, assembly_id, csv_content, id_column)
        if diff is not None and diff.has_changes:
            stash_pending_upload(
                user_id=current_user.id,
                assembly_id=assembly_id,
                upload=StashedUpload(
                    csv_content=csv_content, filename=filename, id_column=id_column, replace_existing=True
                ),
            )
            return _redirect(url_for("respondents.confirm_upload_diff", assembly_id=assembly_id))

        with uow:
            _respondents, skipped, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                csv_content=csv_content,
                replace_existing=True,
                id_column=id_column,
                filename=filename,
            )
            update_csv_config(
                uow=uow,
                user_id=current_user.id,
                assembly_id=assembly_id,
                last_import_filename=filename,
                last_import_timestamp=datetime.now(UTC),
                csv_id_column=resolved_id_column,
            )
            set_data_sources(
                uow,
                current_user.id,
                assembly_id,
                data_source=DataSource.OPENDLP,
                respondents_source=RespondentsSource.CSV,
            )
    except InvalidSelection as e:
        logger.warning("Invalid CSV format for respondents upload", assembly_id=str(assembly_id), error=str(e))
        return _render_project_dialog(
            assembly_id, status=422, respondents_errors=[_("Invalid CSV format: %(error)s", error=e.user_msg())]
        )
    except Exception as e:
        logger.exception("Upload respondents error", assembly_id=str(assembly_id), error=str(e))
        return _render_project_dialog(
            assembly_id, status=422, respondents_errors=[_("An error occurred while uploading respondents")]
        )

    if skipped:
        logger.warning(
            "respondent CSV import completed with warnings",
            assembly_id=str(assembly_id),
            error_count=len(skipped),
            errors=skipped,
        )
    return _render_project_dialog(assembly_id, respondents_notices=_skipped_row_notices(skipped), dirty=False)


@data_source_bp.route("/project/<uuid:assembly_id>/data-source/save", methods=["POST"])
@login_required
@require_assembly_management
def save(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save the dialog: a Google Sheet's settings, or how the targets and respondents will arrive."""
    uow = bootstrap.get_flask_uow()
    with uow:
        nav = get_assembly_nav_context(uow, current_user.id, assembly_id)
    location = nav.data_source if nav.data_source_locked else _posted_location(request.form, nav.data_source)
    created_here = _posted_mode() == MODE_CREATE

    if location != GSHEET_SOURCE:
        with uow:
            set_data_sources(
                uow,
                current_user.id,
                assembly_id,
                data_source=_STORED_LOCATION[location],
                targets_source=_posted_choice(
                    TargetsSource, request.form.get("targets_source"), nav.assembly.targets_source
                ),
                respondents_source=_posted_choice(
                    RespondentsSource, request.form.get("respondents_source"), nav.assembly.respondents_source
                ),
            )
        if not created_here:
            flash(_("Data source settings saved"), "success")
        return _redirect(_details_url(assembly_id))

    form = EditAssemblyGSheetForm() if nav.gsheet else CreateAssemblyGSheetForm()
    if not form.validate():
        return _render_project_dialog(assembly_id, status=422, gsheet_form=form)
    try:
        with uow:
            if nav.gsheet:
                update_assembly_gsheet(
                    uow=uow, assembly_id=assembly_id, user_id=current_user.id, **_gsheet_settings(form)
                )
            else:
                add_assembly_gsheet(uow=uow, assembly_id=assembly_id, user_id=current_user.id, **_gsheet_settings(form))
            set_data_sources(uow, current_user.id, assembly_id, data_source=DataSource.GSHEET)
    except Exception as e:
        logger.exception("Gsheet save error for assembly", assembly_id=str(assembly_id), error=str(e))
        return _render_project_dialog(
            assembly_id,
            status=422,
            gsheet_form=form,
            form_error=_("An error occurred while saving the Google Sheets configuration"),
        )

    # The URL may have changed, so the cached access check may describe another sheet
    forget_cached_result(assembly_id)
    if not created_here:
        flash(_("Data source settings saved"), "success")
    _warn_if_no_columns_to_keep(form)
    return _redirect(_details_url(assembly_id, check=1))
