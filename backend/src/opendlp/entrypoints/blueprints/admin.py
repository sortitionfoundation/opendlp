"""ABOUTME: Admin routes for user management and system administration
ABOUTME: Handles admin-only features like viewing and editing users, requires admin role"""

import uuid

import structlog
from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    make_response,
    redirect,
    render_template,
    render_template_string,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.adapters.tabular_export import AbstractGSheetExportTarget, CsvExportTarget
from opendlp.bootstrap import get_email_adapter, get_template_renderer, get_url_generator
from opendlp.domain.user_signup_surveys import SIGNUP_SURVEY_QUESTIONS, leftover_answer_keys
from opendlp.domain.users import User
from opendlp.entrypoints.context_processors import get_service_account_email
from opendlp.entrypoints.decorators import require_admin
from opendlp.entrypoints.forms import CreateInviteForm, EditUserNamesForm, EditUserRoleForm
from opendlp.entrypoints.gsheet_export_flow import run_gsheet_export_flow
from opendlp.service_layer import two_factor_service
from opendlp.service_layer.exceptions import (
    CannotDisableSelf,
    InsufficientPermissions,
    InviteNotFoundError,
    UserNotFoundError,
)
from opendlp.service_layer.invite_service import (
    cleanup_expired_invites,
    generate_invite,
    get_invite_details,
    get_invite_statistics,
    list_invites,
    revoke_invite,
)
from opendlp.service_layer.signup_survey_service import (
    USERS_WORKSHEET_NAME,
    export_users,
    export_users_to_gsheet,
    get_signup_survey,
)
from opendlp.service_layer.two_factor_service import TwoFactorSetupError
from opendlp.service_layer.user_service import (
    disable_user,
    enable_user,
    get_user_by_id,
    get_user_stats,
    list_users_paginated,
    send_account_reenabled_email,
    totp_cleared_by_lockout,
    update_user,
)
from opendlp.translations import gettext as _

admin_bp = Blueprint("admin", __name__)

logger = structlog.get_logger(__name__)

# A user's names, each edited in place in a row of its own on their page
# (templates/admin/_name_row.html).
NAME_FIELDS = ("first_name", "last_name")

# One name's row on its own, as htmx swaps it in for the row on the page, with
# any flash appended out of band to the page's floating alerts.
_NAME_ROW_RESPONSE = (
    '{% from "admin/_name_row.html" import name_row %}'
    '{% from "backoffice/components/floating_alerts.html" import floating_alerts %}'
    "{{ name_row(user, field, submitted=submitted, error=error, return_focus=return_focus) }}"
    "{{ floating_alerts(oob=true) }}"
)


@admin_bp.route("/")
@login_required
@require_admin
def index() -> ResponseReturnValue:
    """Site Admin opens on its first tab, the users list."""
    return redirect(url_for("admin.list_users"))


@admin_bp.route("/users")
@login_required
@require_admin
def list_users() -> ResponseReturnValue:
    """List all users with pagination and filtering."""
    try:
        # Get query parameters
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", 20, type=int)
        role_filter = request.args.get("role", None, type=str)
        active_filter_str = request.args.get("active", None, type=str)
        search_term = request.args.get("search", None, type=str)

        # Convert active filter string to boolean
        active_filter = None
        if active_filter_str == "true":
            active_filter = True
        elif active_filter_str == "false":
            active_filter = False

        # Validate page number
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 20

        uow = bootstrap.get_flask_uow()
        with uow:
            users, total_count, total_pages = list_users_paginated(
                uow=uow,
                admin_user_id=current_user.id,
                page=page,
                per_page=per_page,
                role_filter=role_filter,
                active_filter=active_filter,
                search_term=search_term,
            )

            # Get user statistics for dashboard
            stats = get_user_stats(uow, current_user.id)

        return render_template(
            "admin/users.html",
            users=users,
            page=page,
            per_page=per_page,
            total_count=total_count,
            total_pages=total_pages,
            role_filter=role_filter,
            active_filter=active_filter_str,
            search_term=search_term,
            stats=stats,
        ), 200

    except InsufficientPermissions as e:
        logger.warning("Unauthorized access to user list", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error("Error listing users for admin", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while loading the user list"), "error")
        return render_template("errors/500.html"), 500


@admin_bp.route("/users/export/modal")
@login_required
@require_admin
def export_users_modal() -> ResponseReturnValue:
    """Render the users export modal fragment (HTMX-loaded).

    The spreadsheet URL always starts empty: where the users go is each
    admin's own choice, so it is not saved between exports.
    """
    return render_template(
        "admin/users_export_modal.html",
        worksheet_name=USERS_WORKSHEET_NAME,
        service_account_email=get_service_account_email(),
    ), 200


@admin_bp.route("/users/export/run", methods=["POST"])
@login_required
@require_admin
def run_users_export() -> ResponseReturnValue:
    """Export every user with their signup survey answers: CSV download or Google Sheets write."""
    users_url = url_for("admin.list_users")
    file_type = request.form.get("file_type", "csv")
    if file_type not in ("csv", "gsheet"):
        flash(_("Only CSV and Google Sheets exports are available for now"), "error")
        return redirect(users_url)

    try:
        if file_type == "gsheet":
            return _run_users_gsheet_export(users_url)
        target = CsvExportTarget()
        uow = bootstrap.get_flask_uow()
        with uow:
            export_users(uow, current_user.id, target=target)
    except InsufficientPermissions:
        flash(_("You don't have permission to export users"), "error")
        return redirect(users_url)

    return Response(
        target.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": 'attachment; filename="opendlp-users.csv"'},
    )


def _run_users_gsheet_export(users_url: str) -> ResponseReturnValue:
    """Export the users to a tab of a caller-supplied Google Spreadsheet.

    The shared flow handles the credentials guard, the URL requirement and the
    error flashes; a permission error propagates to the caller's handler.
    """

    def export(spreadsheet_url: str, worksheet_name: str, target: AbstractGSheetExportTarget) -> None:
        uow = bootstrap.get_flask_uow()
        with uow:
            export_users_to_gsheet(
                uow,
                current_user.id,
                spreadsheet_url=spreadsheet_url,
                worksheet_name=worksheet_name,
                target=target,
            )

    return run_gsheet_export_flow(
        redirect_url=users_url,
        export=export,
        success_message=_("Users exported to Google Sheets"),
        log_event="Google Sheets users export failed",
        log_context={"user_id": str(current_user.id)},
    )


@admin_bp.route("/users/<uuid:user_id>")
@login_required
@require_admin
def view_user(user_id: uuid.UUID) -> ResponseReturnValue:
    """View a single user's details, with their names edited in place and their role in a dialog."""
    try:
        return _user_page(user_id), 200

    except UserNotFoundError as e:
        logger.warning(
            "User not found for admin", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e)
        )
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InsufficientPermissions as e:
        logger.warning("Unauthorized access to user view", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error(
            "Error viewing user for admin", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while loading the user details"), "error")
        return redirect(url_for("admin.list_users"))


def _user_page(
    user_id: uuid.UUID, name_errors: dict[str, str] | None = None, name_submitted: dict[str, str] | None = None
) -> str:
    """The user's page, optionally with a refused name's row left open with the reason."""
    uow = bootstrap.get_flask_uow()
    with uow:
        user = get_user_by_id(uow, user_id, current_user.id)
        survey = get_signup_survey(uow, user_id, current_user.id)

    return render_template(
        "admin/user_view.html",
        user=user,
        survey=survey,
        survey_questions=SIGNUP_SURVEY_QUESTIONS,
        leftover_answer_keys=leftover_answer_keys(survey.answers) if survey else [],
        role_form=EditUserRoleForm(obj=user),
        name_errors=name_errors or {},
        name_submitted=name_submitted or {},
    )


@admin_bp.route("/users/<uuid:user_id>/edit")
@login_required
@require_admin
def edit_user(user_id: uuid.UUID) -> ResponseReturnValue:
    """A user is edited on their own page; this address is kept for old links."""
    return redirect(url_for("admin.view_user", user_id=user_id))


@admin_bp.route("/users/<uuid:user_id>/name", methods=["POST"])
@login_required
@require_admin
def edit_user_name(user_id: uuid.UUID) -> ResponseReturnValue:
    """Save one of a user's names, edited in place on their page.

    Each name's row posts its own field, named by `field`. Over htmx the answer
    is that row again: at rest with the saved name, the success flash appended
    to the page's alerts, or still open with the reason under the field (422).
    Without htmx a save goes back to the user's page, and a refusal renders the
    page with that row open.
    """
    field = request.form.get("field", "")
    if field not in NAME_FIELDS:
        abort(400)

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            stored = get_user_by_id(uow, user_id, current_user.id)
    except UserNotFoundError:
        flash(_("User not found"), "error")
        return _redirect(url_for("admin.list_users"))

    # Built over the stored user, so the name this row did not post keeps its stored value.
    form = EditUserNamesForm(obj=stored)
    if form.validate_on_submit():
        value = form[field].data or ""
        try:
            with uow:
                user = update_user(
                    uow=uow,
                    user_id=user_id,
                    admin_user_id=current_user.id,
                    first_name=value if field == "first_name" else None,
                    last_name=value if field == "last_name" else None,
                )
        except Exception as e:
            logger.error(
                "Error updating user name", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e)
            )
            error = _("An error occurred while updating the user")
        else:
            flash(_("User '%(email)s' updated successfully", email=user.email), "success")
            if _is_htmx():
                return _name_row_response(user, field, return_focus=request.form.get("return_focus") == "1"), 200
            return redirect(url_for("admin.view_user", user_id=user_id))
    else:
        error = "\n".join(form[field].errors) or _("An error occurred while updating the user")

    submitted = request.form.get(field, "")
    if _is_htmx():
        return _name_row_response(stored, field, submitted=submitted, error=error), 422
    return _user_page(user_id, name_errors={field: error}, name_submitted={field: submitted}), 200


@admin_bp.route("/users/<uuid:user_id>/role", methods=["POST"])
@login_required
@require_admin
def edit_user_role(user_id: uuid.UUID) -> ResponseReturnValue:
    """Change a user's global role, from the dialog on their page."""
    form = EditUserRoleForm()
    if not form.validate_on_submit():
        flash(_("Choose a role for this user"), "error")
        return redirect(url_for("admin.view_user", user_id=user_id))

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            user = update_user(
                uow=uow,
                user_id=user_id,
                admin_user_id=current_user.id,
                global_role=form.global_role.data,
            )
    except UserNotFoundError as e:
        logger.warning(
            "User not found for role change by admin",
            user_id=str(user_id),
            admin_user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except ValueError as e:
        logger.warning("Refused role change", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e))
        flash(_("You cannot change your own role"), "error")
    except Exception as e:
        logger.error("Error changing user role", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while updating the user"), "error")
    else:
        flash(_("User '%(email)s' updated successfully", email=user.email), "success")
    return redirect(url_for("admin.view_user", user_id=user_id))


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _redirect(location: str) -> ResponseReturnValue:
    """Redirect, telling htmx to load the page rather than swap it into the row."""
    if _is_htmx():
        response = make_response("", 200)
        response.headers["HX-Redirect"] = location
        return response
    return redirect(location)


def _name_row_response(
    user: User, field: str, submitted: str | None = None, error: str = "", return_focus: bool = False
) -> str:
    return render_template_string(
        _NAME_ROW_RESPONSE, user=user, field=field, submitted=submitted, error=error, return_focus=return_focus
    )


@admin_bp.route("/users/<uuid:user_id>/disable", methods=["POST"])
@login_required
@require_admin
def disable_user_account(user_id: uuid.UUID) -> ResponseReturnValue:
    """Lock a user out: end their sessions, make their password unusable, clear their 2FA."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            user = disable_user(uow, user_id, current_user.id)

        if user.oauth_provider:
            flash(
                _(
                    "Account disabled for '%(email)s'. Every session has been ended. Their %(provider)s "
                    "account still exists — if that is how they were compromised, it needs attention too.",
                    email=user.email,
                    provider=user.oauth_provider.capitalize(),
                ),
                "success",
            )
        else:
            flash(
                _(
                    "Account disabled for '%(email)s'. Every session has been ended and their password "
                    "permanently removed.",
                    email=user.email,
                ),
                "success",
            )
        return redirect(url_for("admin.view_user", user_id=user_id))

    except CannotDisableSelf as e:
        logger.warning("Admin attempted to disable own account", user_id=str(current_user.id), error=str(e))
        flash(e.user_msg(), "error")
        return redirect(url_for("admin.view_user", user_id=user_id))
    except UserNotFoundError as e:
        logger.warning(
            "User not found for disable by admin",
            user_id=str(user_id),
            admin_user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InsufficientPermissions as e:
        logger.warning("Unauthorized account disable attempt", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to perform this action"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error(
            "Error disabling user account", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while disabling the account"), "error")
        return redirect(url_for("admin.view_user", user_id=user_id))


@admin_bp.route("/users/<uuid:user_id>/enable", methods=["POST"])
@login_required
@require_admin
def enable_user_account(user_id: uuid.UUID) -> ResponseReturnValue:
    """Let a disabled user back in, and email them to say how they get back to signing in."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            user = enable_user(uow, user_id, current_user.id)
            totp_cleared = totp_cleared_by_lockout(uow, user)

        flash(_("Account enabled for '%(email)s'", email=user.email), "success")

        email_sent = send_account_reenabled_email(
            email_adapter=get_email_adapter(),
            template_renderer=get_template_renderer(current_app),
            url_generator=get_url_generator(current_app),
            user=user,
            totp_cleared=totp_cleared,
        )
        if email_sent and user.has_usable_password():
            flash(_("An email has been sent telling them their account is back"), "success")
        elif email_sent and user.oauth_provider:
            flash(
                _(
                    "An email has been sent telling them their account is back, and that they sign in "
                    "with %(provider)s as before",
                    provider=user.oauth_provider.capitalize(),
                ),
                "success",
            )
        elif email_sent:
            flash(
                _("An email has been sent telling them to request a password reset — their old password is gone"),
                "success",
            )
        else:
            flash(
                _("The account is enabled, but the email to the user could not be sent. Please contact them directly."),
                "warning",
            )

        return redirect(url_for("admin.view_user", user_id=user_id))

    except UserNotFoundError as e:
        logger.warning(
            "User not found for enable by admin",
            user_id=str(user_id),
            admin_user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InsufficientPermissions as e:
        logger.warning("Unauthorized account enable attempt", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to perform this action"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error(
            "Error enabling user account", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while enabling the account"), "error")
        return redirect(url_for("admin.view_user", user_id=user_id))


@admin_bp.route("/users/<uuid:user_id>/2fa/disable", methods=["POST"])
@login_required
@require_admin
def disable_user_2fa(user_id: uuid.UUID) -> ResponseReturnValue:
    """Admin route to disable 2FA for a user."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            two_factor_service.admin_disable_2fa(uow, user_id, current_user.id)

        flash(_("Two-factor authentication has been disabled for this user"), "success")
        return redirect(url_for("admin.view_user", user_id=user_id))

    except TwoFactorSetupError as e:
        logger.warning(
            "Error disabling 2FA for user", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e)
        )
        flash(str(e), "error")
        return redirect(url_for("admin.view_user", user_id=user_id))
    except UserNotFoundError as e:
        logger.warning(
            "User not found for 2FA disable by admin",
            user_id=str(user_id),
            admin_user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InsufficientPermissions as e:
        logger.warning("Unauthorized 2FA disable attempt", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to perform this action"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error(
            "Error disabling 2FA for user", user_id=str(user_id), admin_user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while disabling two-factor authentication"), "error")
        return redirect(url_for("admin.view_user", user_id=user_id))


@admin_bp.route("/users/<uuid:user_id>/2fa/audit-log")
@login_required
@require_admin
def view_user_2fa_audit_log(user_id: uuid.UUID) -> ResponseReturnValue:
    """Admin route to view 2FA audit log for a user."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            user = get_user_by_id(uow, user_id, current_user.id)
            audit_logs = two_factor_service.get_2fa_audit_logs(uow, user_id, limit=100)

        # Get performer details for audit log entries
        with uow:
            performer_cache = {}
            for log in audit_logs:
                if log.performed_by and log.performed_by not in performer_cache:
                    performer = uow.users.get(log.performed_by)
                    if performer:
                        performer_cache[log.performed_by] = performer.email

        return render_template(
            "admin/user_2fa_audit_log.html",
            user=user,
            audit_logs=audit_logs,
            performer_cache=performer_cache,
        ), 200

    except UserNotFoundError as e:
        logger.warning(
            "User not found for 2FA audit log by admin",
            user_id=str(user_id),
            admin_user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InsufficientPermissions as e:
        logger.warning("Unauthorized 2FA audit log access", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error(
            "Error viewing 2FA audit log for user",
            user_id=str(user_id),
            admin_user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("An error occurred while loading the audit log"), "error")
        return redirect(url_for("admin.view_user", user_id=user_id))


@admin_bp.route("/invites")
@login_required
@require_admin
def list_invites_page() -> ResponseReturnValue:
    """List all invites with statistics."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            # Get all invites (include expired to show full history)
            invites = list_invites(uow=uow, user_id=current_user.id, include_expired=True)

            # Get invite statistics
            stats = get_invite_statistics(uow, current_user.id)

        return render_template("admin/invites.html", invites=invites, stats=stats), 200

    except InsufficientPermissions as e:
        logger.warning("Unauthorized access to invite list", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error("Error listing invites for admin", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while loading the invite list"), "error")
        return render_template("errors/500.html"), 500


@admin_bp.route("/invites/create", methods=["GET", "POST"])
@login_required
@require_admin
def create_invite() -> ResponseReturnValue:
    """Create a new user invite."""
    try:
        form = CreateInviteForm()

        if form.validate_on_submit():
            try:
                # Form coerce function already converts to GlobalRole enum
                global_role = form.global_role.data

                # Get expiry hours, use default if not provided
                expires_in_hours = form.expires_in_hours.data or 168

                uow = bootstrap.get_flask_uow()
                with uow:
                    invite = generate_invite(
                        uow=uow,
                        created_by_user_id=current_user.id,
                        global_role=global_role,
                        expires_in_hours=expires_in_hours,
                        email=form.email.data or "",
                    )

                flash(
                    _("Invite created successfully. Code: %(code)s", code=invite.code),
                    "success",
                )

                # Send invite email if email is provided
                if form.email.data:
                    try:
                        email_sent = _send_invite_email(
                            email_address=form.email.data,
                            invite_code=invite.code,
                            expires_in_hours=expires_in_hours,
                        )
                        if email_sent:
                            flash(
                                _("Invitation email sent to %(email)s", email=form.email.data),
                                "success",
                            )
                        else:
                            flash(
                                _("Failed to send invitation email. Please share the invite code manually."),
                                "warning",
                            )
                    except Exception as e:
                        logger.error("Error sending invite email", invite_id=str(invite.id), error=str(e))
                        flash(
                            _("Error sending invitation email. Please share the invite code manually."),
                            "warning",
                        )

                return redirect(url_for("admin.view_invite", invite_id=invite.id))

            except UserNotFoundError as e:
                logger.warning("User not found while creating invite", user_id=str(current_user.id), error=str(e))
                flash(_("An error occurred while creating the invite"), "error")
            except InsufficientPermissions as e:
                logger.warning("Unauthorized invite creation attempt", user_id=str(current_user.id), error=str(e))
                flash(_("You don't have permission to perform this action"), "error")
                return redirect(url_for("admin.list_invites_page"))
            except Exception as e:
                logger.error("Error creating invite", user_id=str(current_user.id), error=str(e))
                flash(_("An error occurred while creating the invite"), "error")

        return render_template("admin/invite_create.html", form=form), 200

    except Exception as e:
        logger.error("Error loading invite creation page", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while loading the page"), "error")
        return redirect(url_for("admin.list_invites_page"))


@admin_bp.route("/invites/<uuid:invite_id>")
@login_required
@require_admin
def view_invite(invite_id: uuid.UUID) -> ResponseReturnValue:
    """View a single invite's details."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            invite = get_invite_details(uow, invite_id, current_user.id)

        return render_template("admin/invite_view.html", invite=invite), 200

    except InviteNotFoundError as e:
        logger.warning(
            "Invite not found for admin", invite_id=str(invite_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Invite not found"), "error")
        return redirect(url_for("admin.list_invites_page"))
    except InsufficientPermissions as e:
        logger.warning("Unauthorized access to invite view", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error(
            "Error viewing invite for admin", invite_id=str(invite_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while loading the invite details"), "error")
        return redirect(url_for("admin.list_invites_page"))


@admin_bp.route("/invites/<uuid:invite_id>/revoke", methods=["POST"])
@login_required
@require_admin
def revoke_invite_route(invite_id: uuid.UUID) -> ResponseReturnValue:
    """Revoke an invite to prevent its use."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            invite = revoke_invite(uow=uow, invite_id=invite_id, user_id=current_user.id)

        flash(_("Invite '%(code)s' has been revoked", code=invite.code), "success")
        return redirect(url_for("admin.list_invites_page"))

    except InviteNotFoundError as e:
        logger.warning(
            "Invite not found for revocation by admin",
            invite_id=str(invite_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("Invite not found"), "error")
        return redirect(url_for("admin.list_invites_page"))
    except InsufficientPermissions as e:
        logger.warning("Unauthorized invite revocation attempt", user_id=str(current_user.id), error=str(e))
        flash(_("You don't have permission to perform this action"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        logger.error("Error revoking invite", invite_id=str(invite_id), user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while revoking the invite"), "error")
        return redirect(url_for("admin.list_invites_page"))


@admin_bp.route("/invites/cleanup", methods=["POST"])
@login_required
@require_admin
def cleanup_invites() -> ResponseReturnValue:
    """Clean up expired invites."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            count = cleanup_expired_invites(uow=uow)

        if count == 0:
            flash(_("No expired invites to clean up"), "info")
        elif count == 1:
            flash(_("Cleaned up 1 expired invite"), "success")
        else:
            flash(_("Cleaned up %(count)s expired invites", count=count), "success")

        return redirect(url_for("admin.list_invites_page"))

    except Exception as e:
        logger.error("Error cleaning up invites by admin", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while cleaning up invites"), "error")
        return redirect(url_for("admin.list_invites_page"))


def _send_invite_email(
    email_address: str,
    invite_code: str,
    expires_in_hours: int,
) -> bool:
    """
    Send invitation email to user.

    Args:
        email_address: Email address to send invite to
        invite_code: The invite code to include in registration URL
        expires_in_hours: Hours until invite expires (for email message)

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Get dependencies from Flask app
        email_adapter = get_email_adapter()
        template_renderer = get_template_renderer(current_app)
        url_generator = get_url_generator(current_app)

        # Generate registration URL with invite code in path
        registration_url = url_generator.generate_url(
            "auth.register",
            invite_code=invite_code,
            _external=True,
        )

        # Prepare template context
        context = {
            "recipient_name": None,  # We don't have the recipient's name yet
            "email_address": email_address,
            "registration_url": registration_url,
            "expiry_hours": expires_in_hours,
        }

        # Render email templates
        text_body = template_renderer.render_template("emails/user_invite.txt", **context)
        html_body = template_renderer.render_template("emails/user_invite.html", **context)

        # Send email
        success = email_adapter.send_email(
            to=[email_address],
            subject="You're Invited to Join OpenDLP",
            text_body=text_body,
            html_body=html_body,
        )

        # No user/invite UUID is available in this helper and the invite code is
        # a sensitive token, so we deliberately log no identifier here. The
        # censor_pii processor is the backstop for any address that does appear.
        if success:
            logger.info("Invite email sent")
        else:
            logger.error("Failed to send invite email")

        return success

    except Exception as e:
        logger.error("Error sending invite email", error=str(e))
        return False
