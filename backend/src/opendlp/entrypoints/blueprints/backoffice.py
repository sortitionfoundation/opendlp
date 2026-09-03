"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes for dashboard, assembly CRUD, data source, and team members"""

import uuid

import structlog
from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.bootstrap import get_email_adapter, get_template_renderer, get_url_generator
from opendlp.domain.value_objects import AssemblyRole
from opendlp.entrypoints.blueprints.registration import (
    registration_url,
    short_url,
)
from opendlp.entrypoints.forms import (
    AddUserToAssemblyForm,
    CreateAssemblyForm,
    CreateAssemblyGSheetForm,
    DbSelectionSettingsForm,
    EditAssemblyForm,
    EditAssemblyGSheetForm,
    UploadTargetsCsvForm,
)
from opendlp.feature_flags import showcase_enabled
from opendlp.service_layer.assembly_service import (
    create_assembly,
    get_assembly_nav_context,
    get_assembly_with_permissions,
    get_or_create_csv_config,
    get_or_create_selection_settings,
    update_assembly,
)
from opendlp.service_layer.dashboard_stats import (
    DashboardReport,
    get_assembly_dashboard_report,
    get_assembly_dashboard_summary,
)
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    NotFoundError,
)
from opendlp.service_layer.permissions import has_global_admin
from opendlp.service_layer.registration_page_service import (
    list_registration_pages,
)
from opendlp.service_layer.respondent_service import get_respondent_attribute_columns
from opendlp.service_layer.target_respondent_helpers import get_column_distinct_counts
from opendlp.service_layer.target_service import get_targets_for_assembly
from opendlp.service_layer.user_service import (
    get_assembly_members,
    get_user_assemblies,
    grant_user_assembly_role,
    revoke_user_assembly_role,
    search_assembly_candidate_users,
)
from opendlp.translations import gettext as _

backoffice_bp = Blueprint("backoffice", __name__)

logger = structlog.get_logger(__name__)


@backoffice_bp.route("/showcase")
def showcase() -> ResponseReturnValue:
    """Component showcase page demonstrating the backoffice design system.

    Takes no login, so that a designer or a reviewer can be sent a link. That is
    also why a production install has to opt in - see showcase_enabled().
    """
    if not showcase_enabled():
        abort(404)
    return render_template("backoffice/showcase.html"), 200


@backoffice_bp.route("/dashboard")
@login_required
def dashboard() -> ResponseReturnValue:
    """Backoffice dashboard showing user's assemblies."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assemblies = get_user_assemblies(uow, current_user.id)

        return render_template("backoffice/dashboard.html", assemblies=assemblies), 200
    except Exception as e:
        logger.exception("Backoffice dashboard error", user_id=str(current_user.id), error=str(e))
        return render_template("backoffice/dashboard.html", assemblies=[]), 500


@backoffice_bp.route("/assembly/new", methods=["GET", "POST"])
@login_required
def new_assembly() -> ResponseReturnValue:
    """Create a new assembly in backoffice."""
    form = CreateAssemblyForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.get_flask_uow()
            with uow:
                assembly = create_assembly(
                    uow=uow,
                    title=form.title.data or "",
                    created_by_user_id=current_user.id,
                    question=form.question.data or "",
                    first_assembly_date=form.first_assembly_date.data,
                    number_to_select=form.number_to_select.data or 0,
                )

            flash(_("Assembly '%(title)s' created successfully", title=assembly.title), "success")
            return redirect(url_for("backoffice.view_assembly", assembly_id=assembly.id))
        except InsufficientPermissions as e:
            logger.warning("Insufficient permissions to create assembly", user_id=str(current_user.id), error=str(e))
            flash(_("You don't have permission to create assemblies"), "error")
            return redirect(url_for("backoffice.dashboard"))
        except NotFoundError as e:
            logger.error("User not found during assembly creation", user_id=str(current_user.id), error=str(e))
            flash(_("An error occurred while creating the assembly"), "error")
            return redirect(url_for("backoffice.dashboard"))
        except Exception as e:
            logger.exception("Create assembly error", user_id=str(current_user.id), error=str(e))
            flash(_("An error occurred while creating the assembly"), "error")
            return redirect(url_for("backoffice.dashboard"))

    return render_template("backoffice/create_assembly.html", form=form), 200


@backoffice_bp.route("/assembly/<uuid:assembly_id>")
@login_required
def view_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly details page."""
    try:
        nav_uow = bootstrap.get_flask_uow()
        with nav_uow:
            nav = get_assembly_nav_context(
                nav_uow,
                current_user.id,
                assembly_id,
                request.args.get("source", ""),
            )

        # Read-only registration page summary: name, status and copyable URLs per
        # page. Editing lives on the Registration tab, not here.
        uow = bootstrap.get_flask_uow()
        with uow:
            registration_pages = list_registration_pages(uow, current_user.id, assembly_id)
        registration_page_rows = [
            {
                "page": page,
                "registration_url": registration_url(page.url_slug) if page.url_slug else "",
                "short_url": short_url(page.short_url_slug) if page.short_url_slug else "",
            }
            for page in registration_pages
        ]

        return render_template(
            "backoffice/assembly_details.html",
            assembly=nav.assembly,
            data_source=nav.data_source,
            gsheet=nav.gsheet,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
            registration_page_rows=registration_page_rows,
        ), 200
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        # TODO: consider change to "Assembly not found" so as not to leak info
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception("Backoffice assembly error", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while loading the assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _build_dashboard_sections(report: DashboardReport) -> list[dict[str, object]]:
    """Turn the (mock) dashboard report into per-category sections of pie cards.

    Each category shows four dataset cards, matching the Figma layout:
      - Target: the target distribution (band midpoints), always populated;
      - Respondents / Selected / Confirmed: populated once the service exposes
        those distributions. The mock report carries only the pool ("Respondents")
        counts, so Selected and Confirmed render their skeleton state with a message.

    Each card is a dict {title, segments, message}; a falsy ``segments`` triggers
    the pie card's skeleton state, and ``message`` is the text shown in it.
    """
    sections: list[dict[str, object]] = []
    for category in report.categories:
        target_segments = [
            {"label": row.value, "count": round((row.target_min + row.target_max) / 2)} for row in category.rows
        ]
        pool_total = sum(row.pool_count for row in category.rows)
        respondent_segments = (
            [{"label": row.value, "count": row.pool_count} for row in category.rows] if pool_total else None
        )
        cards = [
            {"title": _("Target"), "segments": target_segments, "message": ""},
            {
                "title": _("Respondents"),
                "segments": respondent_segments,
                "message": _("Shows respondent data once registration starts."),
            },
            {
                "title": _("Selected"),
                "segments": None,
                "message": _("Shows selected data once the selection process starts."),
            },
            {
                "title": _("Confirmed"),
                "segments": None,
                "message": _("Shows confirmed data once registration closes."),
            },
        ]
        sections.append({"name": category.name, "cards": cards})
    return sections


@backoffice_bp.route("/assembly/<uuid:assembly_id>/dashboard")
@login_required
def view_assembly_dashboard(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly results dashboard (ticket 886).

    First iteration: the header indicators (number to select / registrations) and
    the per-category pie charts, driven by the MOCK services in
    service_layer/dashboard_stats.py. The chart/table toggle, the export button and
    the findings banner are not wired yet.
    """
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            nav = get_assembly_nav_context(
                uow,
                current_user.id,
                assembly_id,
                request.args.get("source", ""),
            )
            summary = get_assembly_dashboard_summary(uow, current_user.id, assembly_id)
            report = get_assembly_dashboard_report(uow, assembly_id)

        dashboard_sections = _build_dashboard_sections(report)

        return render_template(
            "backoffice/assembly_dashboard.html",
            assembly=nav.assembly,
            current_tab="dashboard",
            data_source=nav.data_source,
            gsheet=nav.gsheet,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
            number_to_select=summary.number_to_select,
            number_of_registrations=summary.total_respondents,
            dashboard_sections=dashboard_sections,
        ), 200
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
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
            "View assembly dashboard error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while loading the dashboard"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/edit", methods=["GET", "POST"])
@login_required
def edit_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice edit assembly page."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            assembly = get_assembly_with_permissions(uow, assembly_id, current_user.id)

        form = EditAssemblyForm(obj=assembly)

        if form.validate_on_submit():
            try:
                # Registration page URLs are deliberately NOT handled here — they
                # are page-scoped settings edited on the Registration tab.
                with uow:
                    updated_assembly = update_assembly(
                        uow=uow,
                        assembly_id=assembly_id,
                        user_id=current_user.id,
                        title=form.title.data,
                        question=form.question.data or "",
                        first_assembly_date=form.first_assembly_date.data,
                        number_to_select=form.number_to_select.data,
                    )

                flash(_("Assembly '%(title)s' updated successfully", title=updated_assembly.title), "success")
                return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
            except InsufficientPermissions as e:
                logger.warning(
                    "Insufficient permissions to edit assembly",
                    assembly_id=str(assembly_id),
                    user_id=str(current_user.id),
                    error=str(e),
                )
                flash(_("You don't have permission to edit this assembly"), "error")
                return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
            except NotFoundError as e:
                logger.error(
                    "Assembly or user not found while editing assembly",
                    assembly_id=str(assembly_id),
                    user_id=str(current_user.id),
                    error=str(e),
                )
                flash(_("An error occurred while updating the assembly"), "error")
                return redirect(url_for("backoffice.dashboard"))
            except Exception as e:
                logger.exception(
                    "Edit assembly error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
                )
                flash(_("An error occurred while updating the assembly"), "error")
                return redirect(url_for("backoffice.dashboard"))

        return render_template(
            "backoffice/edit_assembly.html",
            form=form,
            assembly=assembly,
        ), 200
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for edit", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to access assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to edit this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/update-number-to-select", methods=["POST"])
@login_required
def update_number_to_select(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Update just the number_to_select field for an assembly."""
    try:
        number_to_select = request.form.get("number_to_select", type=int)
        if number_to_select is None or number_to_select < 1:
            flash(_("Please enter a valid positive number"), "error")
            return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id, edit_number=1))

        uow = bootstrap.get_flask_uow()
        with uow:
            updated_assembly = update_assembly(
                uow=uow,
                assembly_id=assembly_id,
                user_id=current_user.id,
                number_to_select=number_to_select,
            )

        flash(_("Number to select updated to %(number)s", number=updated_assembly.number_to_select), "success")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to update number_to_select for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to edit this assembly"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for update", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


def render_assembly_data_page(
    assembly_id: uuid.UUID,
    targets_upload_form: UploadTargetsCsvForm | None = None,
    preferred_source: str = "",
) -> str:
    """Render the assembly data page.

    Shared with the targets blueprint, which owns the targets CSV upload route
    but not the page the form is on: a rejected upload re-renders this page with
    `targets_upload_form` carrying the errors, rather than redirecting and
    leaving the reason in a flash message away from the field. That caller also
    names the source, because a POST carries no `?source=` to read it from.

    Raises the same exceptions as the service functions it calls.
    """
    google_service_account_email = current_app.config.get("GOOGLE_SERVICE_ACCOUNT_EMAIL", "UNKNOWN")

    nav_uow = bootstrap.get_flask_uow()
    with nav_uow:
        nav = get_assembly_nav_context(
            nav_uow,
            current_user.id,
            assembly_id,
            preferred_source or request.args.get("source", ""),
        )

    # Get selection settings for gsheet display and form population.
    # A single UnitOfWork is reused for the sequential reads below.
    uow = bootstrap.get_flask_uow()
    sel_settings = None
    with uow:
        try:
            sel_settings = get_or_create_selection_settings(uow, current_user.id, assembly_id)
        except Exception as sel_error:
            logger.exception("Error loading selection settings", error=str(sel_error))

    # Set up gsheet form if gsheet source is selected
    gsheet_mode = "new"
    gsheet_form = None
    if nav.data_source == "gsheet":
        mode_param = request.args.get("mode", "")
        gsheet_mode = ("edit" if mode_param == "edit" else "view") if nav.gsheet else "new"
        if nav.gsheet:
            gsheet_form = EditAssemblyGSheetForm(
                obj=nav.gsheet,
                id_column=sel_settings.id_column if sel_settings else "",
                check_same_address=sel_settings.check_same_address if sel_settings else True,
                check_same_address_cols_string=sel_settings.check_same_address_cols_string if sel_settings else "",
                columns_to_keep_string=sel_settings.columns_to_keep_string if sel_settings else "",
            )
        else:
            gsheet_form = CreateAssemblyGSheetForm()

    # Set up CSV settings form if CSV source is selected
    csv_settings_form = None
    csv_available_columns: list[str] = []
    csv_mode = "view"  # Default to view mode
    csv_config = None
    # What the "Create from respondent data" dialog on the targets card needs:
    # the columns it can offer, how many distinct answers each holds, and the
    # categories that already cover one.
    target_categories: list = []
    respondent_attribute_columns: list[str] = []
    column_distinct_counts: dict[str, int] = {}
    if nav.data_source == "csv":
        # Determine mode (view or edit)
        mode_param = request.args.get("mode", "")
        csv_mode = "edit" if mode_param == "edit" else "view"

        # Get or create CSV config (reusing the UnitOfWork from above)
        with uow:
            csv_config = get_or_create_csv_config(uow, current_user.id, assembly_id)

            # Get available columns from respondents for validation hints
            csv_available_columns = get_respondent_attribute_columns(uow, assembly_id)

            target_categories = get_targets_for_assembly(uow, current_user.id, assembly_id)

        # The id column identifies a respondent rather than describing them,
        # so it is never a target category.
        respondent_attribute_columns = [
            column for column in csv_available_columns if column != csv_config.csv_id_column
        ]
        if respondent_attribute_columns:
            # Opens its own UnitOfWork, so it stays outside the block above.
            column_distinct_counts = get_column_distinct_counts(assembly_id, respondent_attribute_columns)

        # Create form with current values from SelectionSettings
        csv_settings_form = DbSelectionSettingsForm(
            data={
                "check_same_address": sel_settings.check_same_address if sel_settings else True,
                "check_same_address_cols_string": sel_settings.check_same_address_cols_string if sel_settings else "",
                "columns_to_keep_string": sel_settings.columns_to_keep_string if sel_settings else "",
            },
            available_columns=csv_available_columns,
        )

    return render_template(
        "backoffice/assembly_data.html",
        assembly=nav.assembly,
        data_source=nav.data_source,
        data_source_locked=nav.data_source_locked,
        gsheet=nav.gsheet,
        selection_settings=sel_settings,
        gsheet_mode=gsheet_mode,
        gsheet_form=gsheet_form,
        google_service_account_email=google_service_account_email,
        targets_enabled=nav.targets_enabled,
        respondents_enabled=nav.respondents_enabled,
        selection_enabled=nav.selection_enabled,
        csv_status=nav.csv_status,
        csv_settings_form=csv_settings_form,
        csv_available_columns=csv_available_columns,
        csv_mode=csv_mode,
        csv_config=csv_config,
        target_categories=target_categories,
        respondent_attribute_columns=respondent_attribute_columns,
        column_distinct_counts=column_distinct_counts,
        targets_upload_form=targets_upload_form,
    )


@backoffice_bp.route("/assembly/<uuid:assembly_id>/data")
@login_required
def view_assembly_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly data page."""
    try:
        return render_assembly_data_page(assembly_id), 200
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
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
            "View assembly data error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while loading assembly data"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members")
@login_required
def view_assembly_members(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly team members page."""
    try:
        nav_uow = bootstrap.get_flask_uow()
        with nav_uow:
            nav = get_assembly_nav_context(
                nav_uow,
                current_user.id,
                assembly_id,
                request.args.get("source", ""),
            )

        uow = bootstrap.get_flask_uow()
        with uow:
            assembly_users = get_assembly_members(uow, assembly_id, current_user)

        can_manage_assembly_users = has_global_admin(current_user)
        add_user_form = AddUserToAssemblyForm()

        return render_template(
            "backoffice/assembly_members.html",
            assembly=nav.assembly,
            assembly_users=assembly_users,
            can_manage_assembly_users=can_manage_assembly_users,
            add_user_form=add_user_form,
            current_tab="members",
            data_source=nav.data_source,
            gsheet=nav.gsheet,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
        ), 200
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
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
            "View assembly members error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while loading team members"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/add", methods=["POST"])
@login_required
def add_user_to_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Add a user to an assembly with a specific role."""
    form = AddUserToAssemblyForm()

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            if form.validate_on_submit():
                user_id = uuid.UUID(form.user_id.data)

                # Role is already an AssemblyRole enum from form coercion
                role = form.role.data
                assert isinstance(role, AssemblyRole)

                # Get email adapters for sending notification
                email_adapter = get_email_adapter()
                template_renderer = get_template_renderer(current_app)
                url_generator = get_url_generator(current_app)

                # Call service layer to add user to assembly
                _assembly_role, target_user = grant_user_assembly_role(
                    uow=uow,
                    user_id=user_id,
                    assembly_id=assembly_id,
                    role=role,
                    current_user=current_user,
                    email_adapter=email_adapter,
                    template_renderer=template_renderer,
                    url_generator=url_generator,
                )

                flash(
                    _(
                        "%(user)s added to assembly with role %(role)s",
                        user=target_user.display_name,
                        role=role.value,
                    ),
                    "success",
                )
            else:
                flash(_("Please select a user and role"), "error")

        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))

    except NotFoundError as e:
        logger.error("Error adding user to assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("Could not add user to assembly: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to add user to assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to add users to this assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except Exception as e:
        logger.exception(
            "Unexpected error adding user to assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("An error occurred while adding the user to the assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/<uuid:user_id>/remove", methods=["POST"])
@login_required
def remove_user_from_assembly(assembly_id: uuid.UUID, user_id: uuid.UUID) -> ResponseReturnValue:
    """Remove a user from an assembly."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            # Call service layer to remove user from assembly
            _assembly_role, target_user = revoke_user_assembly_role(
                uow=uow,
                user_id=user_id,
                assembly_id=assembly_id,
                current_user=current_user,
            )

            flash(
                _("%(user)s removed from assembly", user=target_user.display_name),
                "success",
            )

        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))

    except NotFoundError as e:
        logger.error("Error removing user from assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("Could not remove user from assembly: %(error)s", error=str(e)), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to remove user from assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to remove users from this assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))
    except Exception as e:
        logger.exception(
            "Unexpected error removing user from assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("An error occurred while removing the user from the assembly"), "error")
        return redirect(url_for("backoffice.view_assembly_members", assembly_id=assembly_id))


@backoffice_bp.route("/assembly/<uuid:assembly_id>/members/search")
@login_required
def search_users(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Search for users not yet added to the assembly.

    Returns JSON array for use with autocomplete component.
    """
    try:
        search_term = request.args.get("q", "").strip()

        uow = bootstrap.get_flask_uow()
        with uow:
            matching_users = search_assembly_candidate_users(uow, assembly_id, search_term, current_user)

        # Return JSON array with id, label, sublabel format expected by autocomplete
        results = [
            {
                "id": str(user.id),
                "label": user.email,
                "sublabel": user.display_name,
            }
            for user in matching_users
        ]

        return jsonify(results), 200

    except InsufficientPermissions:
        return jsonify([]), 403
    except Exception as e:
        logger.exception("Error searching users for assembly", assembly_id=str(assembly_id), error=str(e))
        return jsonify([]), 500


@backoffice_bp.route("/showcase/search-demo")
def search_demo() -> ResponseReturnValue:
    """Demo search endpoint for showcase page.

    Returns mock data for demonstrating the search_dropdown component. Goes
    wherever the showcase goes - it is the page's own endpoint.
    """
    if not showcase_enabled():
        abort(404)
    search_term = request.args.get("q", "").strip().lower()

    # Mock data for demonstration
    mock_users = [
        {"id": "1", "label": "alice@example.com", "sublabel": "Alice Johnson"},
        {"id": "2", "label": "bob@example.com", "sublabel": "Bob Smith"},
        {"id": "3", "label": "carol@example.com", "sublabel": "Carol Williams"},
        {"id": "4", "label": "david@example.com", "sublabel": "David Brown"},
        {"id": "5", "label": "eve@example.com", "sublabel": "Eve Davis"},
    ]

    if not search_term:
        return jsonify([]), 200

    # Filter mock data based on search term
    results = [
        user for user in mock_users if search_term in user["label"].lower() or search_term in user["sublabel"].lower()
    ]

    return jsonify(results), 200
