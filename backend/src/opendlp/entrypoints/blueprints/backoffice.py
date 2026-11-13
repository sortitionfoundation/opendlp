"""ABOUTME: Backoffice routes for admin UI using Pines UI + Tailwind CSS
ABOUTME: Provides /backoffice/* routes for dashboard, assembly CRUD, data source, and team members"""

import uuid

import structlog
from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.adapters.tabular_export import AbstractGSheetExportTarget, CsvExportTarget
from opendlp.domain.assembly_export_gsheet import default_worksheet_name
from opendlp.domain.value_objects import GSheetExportKind
from opendlp.entrypoints.blueprints.data_source import project_dialog_context
from opendlp.entrypoints.blueprints.project_details import team_card_context
from opendlp.entrypoints.blueprints.registration import (
    registration_url,
    short_url,
)
from opendlp.entrypoints.context_processors import get_service_account_email
from opendlp.entrypoints.data_source_card import respondents_row, targets_row
from opendlp.entrypoints.gsheet_export_flow import run_gsheet_export_flow
from opendlp.entrypoints.registration_link_card import featured_registration_page, registration_tab_link_text
from opendlp.feature_flags import showcase_enabled
from opendlp.service_layer.assembly_service import (
    get_assembly_creator_name,
    get_assembly_nav_context,
    update_assembly,
)
from opendlp.service_layer.dashboard_stats import (
    CategoryValueRow,
    DashboardReport,
    export_dashboard_report,
    export_dashboard_report_to_gsheet,
    get_assembly_dashboard_report,
    get_assembly_dashboard_summary,
    get_dashboard_gsheet_config,
)
from opendlp.service_layer.exceptions import (
    CannotRemoveLastAssemblyManager,
    InsufficientPermissions,
    NotFoundError,
)
from opendlp.service_layer.gsheet_access_check import fetch_cached_result
from opendlp.service_layer.permissions import (
    can_manage_assembly,
    can_see_all_assemblies,
)
from opendlp.service_layer.registration_page_service import (
    list_registration_pages,
)
from opendlp.service_layer.user_service import (
    get_user_assemblies,
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


@backoffice_bp.route("/assembly/<path:rest>")
def redirect_old_assembly_url(rest: str) -> ResponseReturnValue:
    """Send a bookmarked /backoffice/assembly/… URL to its /backoffice/project/… twin.

    The interface calls the thing a project, and so do its URLs; the old paths
    live on in bookmarks, emails and spreadsheets. The query string comes too.
    """
    target = f"/backoffice/project/{rest}"
    if request.query_string:
        target = f"{target}?{request.query_string.decode()}"
    return redirect(target, code=301)


@backoffice_bp.route("/project/<uuid:assembly_id>")
@login_required
def view_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly details page."""
    try:
        nav_uow = bootstrap.get_flask_uow()
        with nav_uow:
            nav = get_assembly_nav_context(nav_uow, current_user.id, assembly_id)

        # One registration page's links, read-only. Every page, and editing
        # them, lives on the Registration tab.
        uow = bootstrap.get_flask_uow()
        with uow:
            registration_pages = list_registration_pages(uow, current_user.id, assembly_id)
            created_by_name = get_assembly_creator_name(uow, nav.assembly)
            can_manage_project = can_manage_assembly(current_user, nav.assembly)
            # The access check panel under a Google Sheet's URL: checked afresh
            # after a save (?check=1), otherwise whatever the last check found.
            gsheet_access_result = None
            gsheet_access_auto_check = False
            if nav.gsheet:
                gsheet_access_auto_check = can_manage_project and request.args.get("check", "") == "1"
                if not gsheet_access_auto_check:
                    gsheet_access_result = fetch_cached_result(assembly_id, nav.gsheet.url)
            project_dialog = None
            if request.args.get("data_source") == "1" and can_manage_project:
                project_dialog = project_dialog_context(uow, assembly_id)
            team_card = team_card_context(uow, nav.assembly)
        featured_page = featured_registration_page(registration_pages)
        registration_link = None
        if featured_page is not None:
            page_short_url = short_url(featured_page.short_url_slug) if featured_page.short_url_slug else ""
            registration_link = {
                "registration_url": registration_url(featured_page.url_slug) if featured_page.url_slug else "",
                "short_url": page_short_url,
                # The QR code encodes the short URL, so there is none to download without one.
                "qr_code_url": url_for(
                    "backoffice_registration.download_registration_qr_code",
                    assembly_id=assembly_id,
                    url_slug=featured_page.url_slug,
                )
                if page_short_url and featured_page.url_slug
                else "",
            }

        return render_template(
            "backoffice/assembly_details.html",
            assembly=nav.assembly,
            data_source=nav.data_source,
            gsheet=nav.gsheet,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
            registration_link=registration_link,
            registration_tab_link_text=registration_tab_link_text(len(registration_pages)),
            created_by_name=created_by_name,
            project_dialog=project_dialog,
            can_manage_project=can_manage_project,
            targets_row=targets_row(nav.assembly, nav.csv_status.targets_count),
            respondents_row=respondents_row(nav.assembly, nav.csv_status.respondents_count),
            gsheet_access_result=gsheet_access_result,
            gsheet_access_auto_check=gsheet_access_auto_check,
            can_check_gsheet_access=can_manage_project,
            **team_card,
        ), 200
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        # TODO: consider change to "Assembly not found" so as not to leak info
        flash(_("You don't have permission to view this project"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Project not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception("Backoffice assembly error", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while loading the project"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _target_band(row: CategoryValueRow) -> str:
    """The target band as entered: "30-31", collapsed to "30" when min == max.

    Shown instead of a single count: any single number would be a midpoint of our
    own invention, rounded to look plausible while matching nothing the user set.
    """
    if row.target_min == row.target_max:
        return str(row.target_min)
    return f"{row.target_min}–{row.target_max}"


def _build_dashboard_sections(report: DashboardReport) -> list[dict[str, object]]:
    """Turn the dashboard report into per-category sections of pie cards.

    Each category shows five dataset cards: Population, Target, Respondents
    (pool), Selected and Confirmed. Population is weighted by the population
    shares entered in the targets editor and Target by the share each min/max
    band implies — kept as two pies because the two deliberately differ when a
    group is over-sampled, and one pie showing sometimes-one, sometimes-the-other
    proved confusing. The Population pie only renders once every value in the
    category has a population share: charting the values that happen to have one
    would misrepresent the split. The other datasets' pies are populated from
    the report's real counts; a dataset whose category total is zero has
    ``segments = None``, which the pie card renders as a grey skeleton with the
    given ``message``. There is no separate "has selection started" flag: a
    selection assigns every selected person a value in every category at once,
    so a zero ``selected_count`` total for a category is exactly "no selection
    yet".

    Each card is a dict {title, segments, message}; a falsy ``segments`` triggers
    the pie card's skeleton state, and ``message`` is the text shown in it.
    """

    def segments_or_none(rows: list[CategoryValueRow], count_attr: str) -> list[dict[str, object]] | None:
        if not sum(getattr(row, count_attr) for row in rows):
            return None
        return [{"label": row.value, "count": getattr(row, count_attr)} for row in rows]

    def population_segments(rows: list[CategoryValueRow]) -> list[dict[str, object]] | None:
        segments: list[dict[str, object]] = []
        for row in rows:
            if row.population_pct is None:
                return None
            segments.append({"label": row.value, "count": row.population_pct, "display": f"{row.population_pct:.1f}%"})
        return segments

    sections: list[dict[str, object]] = []
    for category in report.categories:
        target_segments = [
            {"label": row.value, "count": row.target_pct, "display": _target_band(row)} for row in category.rows
        ]
        cards = [
            {
                "title": _("Population"),
                "segments": population_segments(category.rows),
                "message": _("Shows the population split once every value has a population share set in the targets."),
            },
            {"title": _("Target"), "segments": target_segments, "message": ""},
            {
                "title": _("Respondents"),
                "segments": segments_or_none(category.rows, "pool_count"),
                "message": _("Shows respondent data once registration starts."),
            },
            {
                "title": _("Selected"),
                "segments": segments_or_none(category.rows, "selected_count"),
                "message": _("Shows selected data once selection has happened."),
            },
            {
                "title": _("Confirmed"),
                "segments": segments_or_none(category.rows, "confirmed_count"),
                "message": _("Shows confirmed data once at least one selected respondent is confirmed."),
            },
        ]
        sections.append({"name": category.name, "cards": cards})
    return sections


def _build_dashboard_tables(report: DashboardReport) -> list[dict[str, object]]:
    """Turn the dashboard report into per-category tables (the on-screen Table view).

    One table per category; one row per category value with a percentage and a
    count column for each dataset (Population / Target / Respondents / Selected
    / Confirmed). All figures come straight from the report's rows:
    ``population_pct`` is the population share as entered in the targets editor
    (an em dash when unset — no band-derived fallback, that conflation is what
    these columns were split to remove); the Target column is the min-max band
    as entered; Respondents / Selected / Confirmed percentages are each value's
    share of that dataset's category total.

    This is the on-screen shape only. The exportable table (flat, all categories,
    with min/max/available/shortfall columns) is the service's
    ``build_dashboard_table`` and is used by the export button, not here.

    Each table is {name, rows}; each row is a dict of pre-formatted strings/ints
    the template drops straight into cells.
    """

    def pct(part: int, whole: int) -> str:
        return f"{(part / whole * 100):.1f}" if whole else "0.0"

    tables: list[dict[str, object]] = []
    for category in report.categories:
        pool_total = sum(row.pool_count for row in category.rows)
        selected_total = sum(row.selected_count for row in category.rows)
        confirmed_total = sum(row.confirmed_count for row in category.rows)
        rows = [
            {
                "value": row.value,
                "population_pct": f"{row.population_pct:.1f}" if row.population_pct is not None else "—",
                "target_count": _target_band(row),
                "respondents_pct": pct(row.pool_count, pool_total),
                "respondents_count": row.pool_count,
                "selected_pct": pct(row.selected_count, selected_total),
                "selected_count": row.selected_count,
                "confirmed_pct": pct(row.confirmed_count, confirmed_total),
                "confirmed_count": row.confirmed_count,
            }
            for row in category.rows
        ]
        tables.append({"name": category.name, "rows": rows})
    return tables


@backoffice_bp.route("/project/<uuid:assembly_id>/dashboard")
@login_required
def view_assembly_dashboard(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice assembly results dashboard (ticket 886).

    Header indicators (number to select / registrations) plus the per-category
    results, in one of two views selected by the ``view`` query parameter:
    "chart" (default) draws pie charts, "table" draws a table per category. Both
    are driven by the services in service_layer/dashboard_stats.py. The findings
    banner is not wired yet.
    """
    view = "table" if request.args.get("view") == "table" else "chart"
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            nav = get_assembly_nav_context(uow, current_user.id, assembly_id)
            summary = get_assembly_dashboard_summary(uow, current_user.id, assembly_id)
            report = get_assembly_dashboard_report(uow, current_user.id, assembly_id)

        dashboard_sections = _build_dashboard_sections(report)
        dashboard_tables = _build_dashboard_tables(report)

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
            number_of_respondents=summary.total_respondents,
            dashboard_view=view,
            dashboard_sections=dashboard_sections,
            dashboard_tables=dashboard_tables,
        ), 200
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Project not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to view this project"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception(
            "View assembly dashboard error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while loading the dashboard"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/project/<uuid:assembly_id>/dashboard/export/modal")
@login_required
def dashboard_export_modal(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Render the dashboard export modal fragment (HTMX-loaded).

    The Google Sheets option always writes a caller-supplied destination
    spreadsheet, as in the respondents export. There is no source-spreadsheet
    special case: an assembly whose data source is a Google Sheet has no
    OpenDLP data to build a dashboard from.
    """
    dashboard_url = url_for("backoffice.view_assembly_dashboard", assembly_id=assembly_id, view="table")
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            gsheet_config = get_dashboard_gsheet_config(uow, current_user.id, assembly_id)
    except InsufficientPermissions:
        flash(_("You don't have permission to export the dashboard"), "error")
        return redirect(dashboard_url)
    except NotFoundError:
        flash(_("Project not found"), "error")
        return redirect(url_for("backoffice.dashboard"))

    worksheet_name = (
        gsheet_config.worksheet_name if gsheet_config else default_worksheet_name(GSheetExportKind.DASHBOARD)
    )
    return render_template(
        "backoffice/dashboard_export_modal.html",
        assembly_id=assembly_id,
        worksheet_name=worksheet_name,
        gsheet_url=gsheet_config.url if gsheet_config else "",
        service_account_email=get_service_account_email(),
    ), 200


@backoffice_bp.route("/project/<uuid:assembly_id>/dashboard/export/run", methods=["POST"])
@login_required
def run_dashboard_export(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Run a dashboard export from the modal: CSV download or Google Sheets write."""
    dashboard_url = url_for("backoffice.view_assembly_dashboard", assembly_id=assembly_id, view="table")
    file_type = request.form.get("file_type", "csv")
    if file_type not in ("csv", "gsheet"):
        flash(_("Only CSV and Google Sheets exports are available for now"), "error")
        return redirect(dashboard_url)

    try:
        if file_type == "gsheet":
            return _run_dashboard_gsheet_export(assembly_id, dashboard_url)
        # The CSV target is built inline rather than injected: pure in-memory work,
        # no seam needed. The Google Sheets target is injected via an app factory
        # instead (see _run_dashboard_gsheet_export and the respondents export).
        target = CsvExportTarget()
        uow = bootstrap.get_flask_uow()
        with uow:
            export_dashboard_report(uow, current_user.id, assembly_id, target=target)
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to export dashboard",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to export the dashboard"), "error")
        return redirect(dashboard_url)
    except NotFoundError as e:
        logger.warning("Assembly not found for dashboard export", assembly_id=str(assembly_id), error=str(e))
        flash(_("Project not found"), "error")
        return redirect(url_for("backoffice.dashboard"))

    filename = f"dashboard-{str(assembly_id)[:8]}.csv"
    return Response(
        target.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _run_dashboard_gsheet_export(assembly_id: uuid.UUID, dashboard_url: str) -> ResponseReturnValue:
    """Export the dashboard as a tab of a caller-supplied Google Spreadsheet.

    The destination is always a caller-supplied spreadsheet URL, as in the
    respondents export — an assembly whose data source is a Google Sheet has
    no OpenDLP data to build a dashboard from, so there is no
    source-spreadsheet special case. The shared flow handles the credentials
    guard, the URL requirement and the error flashes; permission and
    not-found errors propagate to the caller's handlers.
    """

    def export(spreadsheet_url: str, worksheet_name: str, target: AbstractGSheetExportTarget) -> None:
        uow = bootstrap.get_flask_uow()
        with uow:
            export_dashboard_report_to_gsheet(
                uow,
                current_user.id,
                assembly_id,
                spreadsheet_url=spreadsheet_url,
                worksheet_name=worksheet_name,
                target=target,
            )

    return run_gsheet_export_flow(
        redirect_url=dashboard_url,
        export=export,
        success_message=_("Dashboard exported to Google Sheets."),
        log_event="Google Sheets dashboard export failed",
        log_context={"assembly_id": str(assembly_id), "user_id": str(current_user.id)},
    )


@backoffice_bp.route("/project/<uuid:assembly_id>/edit", methods=["GET", "POST"])
@login_required
def edit_assembly(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Where the edit page was. A project's details are edited in place on its details page."""
    return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))


@backoffice_bp.route("/project/<uuid:assembly_id>/update-number-to-select", methods=["POST"])
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

        flash(_("Panel size updated to %(number)s", number=updated_assembly.number_to_select), "success")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to update number_to_select for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to edit this project"), "error")
        return redirect(url_for("gsheets.view_assembly_selection", assembly_id=assembly_id))
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for update", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Project not found"), "error")
        return redirect(url_for("backoffice.dashboard"))


@backoffice_bp.route("/project/<uuid:assembly_id>/data")
@login_required
def view_assembly_data(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Where the Data Source tab was. The data source is a card on the project details page."""
    return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id, _anchor="data-source"))


@backoffice_bp.route("/project/<uuid:assembly_id>/members")
@login_required
def view_assembly_members(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Where the Team Members tab was. The team is a card on the project details page."""
    return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id, _anchor="team"))


@backoffice_bp.route("/project/<uuid:assembly_id>/members/<uuid:user_id>/remove", methods=["POST"])
@login_required
def remove_user_from_assembly(assembly_id: uuid.UUID, user_id: uuid.UUID) -> ResponseReturnValue:
    """Remove a user from an assembly, from the Team card on the project details page."""
    team_url = url_for("backoffice.view_assembly", assembly_id=assembly_id, _anchor="team")
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
                _("%(user)s removed from project", user=target_user.display_name),
                "success",
            )

        # Someone who removed themselves can no longer open the project, unless
        # they see every project anyway.
        if user_id == current_user.id and not can_see_all_assemblies(current_user):
            return redirect(url_for("backoffice.dashboard"))
        return redirect(team_url)

    except CannotRemoveLastAssemblyManager as e:
        logger.warning(
            "Refused to leave assembly without a manager",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
        )
        flash(e.user_msg(), "error")
        return redirect(team_url)
    except NotFoundError as e:
        logger.error("Error removing user from assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("Could not remove user from project: %(error)s", error=str(e)), "error")
        return redirect(team_url)
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions to remove user from assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to remove users from this project"), "error")
        return redirect(team_url)
    except Exception as e:
        logger.exception(
            "Unexpected error removing user from assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("An error occurred while removing the user from the project"), "error")
        return redirect(team_url)


@backoffice_bp.route("/project/<uuid:assembly_id>/members/search")
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
    except NotFoundError:
        return jsonify([]), 404
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
