"""ABOUTME: Admin routes for user management and system administration
ABOUTME: Handles admin-only features like viewing and editing users, requires admin role"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.decorators import require_admin
from opendlp.entrypoints.forms import CreateInviteForm, EditUserForm
from opendlp.service_layer.exceptions import (
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
from opendlp.service_layer.user_service import get_user_by_id, get_user_stats, list_users_paginated, update_user
from opendlp.translations import gettext as _

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/")
@login_required
@require_admin
def index() -> ResponseReturnValue:
    """Site admin overview page with links to admin sections."""
    return render_template("admin/index.html"), 200


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

        uow = bootstrap.bootstrap()
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
        current_app.logger.warning(f"Unauthorized access to user list by user {current_user.id}: {e}")
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error listing users for admin {current_user.id}: {e}")
        flash(_("An error occurred while loading the user list"), "error")
        return render_template("errors/500.html"), 500


@admin_bp.route("/users/<uuid:user_id>")
@login_required
@require_admin
def view_user(user_id: uuid.UUID) -> ResponseReturnValue:
    """View a single user's details."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            user = get_user_by_id(uow, user_id, current_user.id)

        return render_template("admin/user_view.html", user=user), 200

    except UserNotFoundError as e:
        current_app.logger.warning(f"User {user_id} not found for admin {current_user.id}: {e}")
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Unauthorized access to user view by user {current_user.id}: {e}")
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error viewing user {user_id} for admin {current_user.id}: {e}")
        flash(_("An error occurred while loading the user details"), "error")
        return redirect(url_for("admin.list_users"))


@admin_bp.route("/users/<uuid:user_id>/edit", methods=["GET", "POST"])
@login_required
@require_admin
def edit_user(user_id: uuid.UUID) -> ResponseReturnValue:
    """Edit a user's details."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            user = get_user_by_id(uow, user_id, current_user.id)

        form = EditUserForm(obj=user)

        if form.validate_on_submit():
            try:
                # Form coerce function already converts to GlobalRole enum
                global_role = form.global_role.data

                with uow:
                    updated_user = update_user(
                        uow=uow,
                        user_id=user_id,
                        admin_user_id=current_user.id,
                        first_name=form.first_name.data or "",
                        last_name=form.last_name.data or "",
                        global_role=global_role,
                        is_active=form.is_active.data,
                    )

                flash(
                    _("User '%(email)s' updated successfully", email=updated_user.email),
                    "success",
                )
                return redirect(url_for("admin.view_user", user_id=user_id))

            except UserNotFoundError as e:
                current_app.logger.warning(f"User {user_id} not found for edit by admin {current_user.id}: {e}")
                flash(_("User not found"), "error")
                return redirect(url_for("admin.list_users"))
            except InsufficientPermissions as e:
                current_app.logger.warning(f"Unauthorized user update attempt by user {current_user.id}: {e}")
                flash(_("You don't have permission to perform this action"), "error")
                return redirect(url_for("admin.view_user", user_id=user_id))
            except ValueError as e:
                current_app.logger.warning(f"Validation error updating user {user_id} by admin {current_user.id}: {e}")
                flash(str(e), "error")
            except Exception as e:
                current_app.logger.error(f"Error updating user {user_id} by admin {current_user.id}: {e}")
                flash(_("An error occurred while updating the user"), "error")

        return render_template("admin/user_edit.html", form=form, user=user), 200

    except UserNotFoundError as e:
        current_app.logger.warning(f"User {user_id} not found for edit by admin {current_user.id}: {e}")
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Unauthorized access to user edit by user {current_user.id}: {e}")
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error loading user edit page for user {user_id}, admin {current_user.id}: {e}")
        flash(_("An error occurred while loading the edit page"), "error")
        return redirect(url_for("admin.list_users"))


@admin_bp.route("/invites")
@login_required
@require_admin
def list_invites_page() -> ResponseReturnValue:
    """List all invites with statistics."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            # Get all invites (include expired to show full history)
            invites = list_invites(uow=uow, user_id=current_user.id, include_expired=True)

            # Get invite statistics
            stats = get_invite_statistics(uow, current_user.id)

        return render_template("admin/invites.html", invites=invites, stats=stats), 200

    except InsufficientPermissions as e:
        current_app.logger.warning(f"Unauthorized access to invite list by user {current_user.id}: {e}")
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error listing invites for admin {current_user.id}: {e}")
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

                uow = bootstrap.bootstrap()
                with uow:
                    invite = generate_invite(
                        uow=uow,
                        created_by_user_id=current_user.id,
                        global_role=global_role,
                        expires_in_hours=expires_in_hours,
                    )

                flash(
                    _("Invite created successfully. Code: %(code)s", code=invite.code),
                    "success",
                )

                # TODO: If email is provided, send invite email
                if form.email.data:
                    flash(
                        _("Email sending not yet implemented. Please share the invite code manually."),
                        "info",
                    )

                return redirect(url_for("admin.view_invite", invite_id=invite.id))

            except UserNotFoundError as e:
                current_app.logger.warning(f"User not found while creating invite by admin {current_user.id}: {e}")
                flash(_("An error occurred while creating the invite"), "error")
            except InsufficientPermissions as e:
                current_app.logger.warning(f"Unauthorized invite creation attempt by user {current_user.id}: {e}")
                flash(_("You don't have permission to perform this action"), "error")
                return redirect(url_for("admin.list_invites_page"))
            except Exception as e:
                current_app.logger.error(f"Error creating invite by admin {current_user.id}: {e}")
                flash(_("An error occurred while creating the invite"), "error")

        return render_template("admin/invite_create.html", form=form), 200

    except Exception as e:
        current_app.logger.error(f"Error loading invite creation page for admin {current_user.id}: {e}")
        flash(_("An error occurred while loading the page"), "error")
        return redirect(url_for("admin.list_invites_page"))


@admin_bp.route("/invites/<uuid:invite_id>")
@login_required
@require_admin
def view_invite(invite_id: uuid.UUID) -> ResponseReturnValue:
    """View a single invite's details."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            invite = get_invite_details(uow, invite_id, current_user.id)

        return render_template("admin/invite_view.html", invite=invite), 200

    except InviteNotFoundError as e:
        current_app.logger.warning(f"Invite {invite_id} not found for admin {current_user.id}: {e}")
        flash(_("Invite not found"), "error")
        return redirect(url_for("admin.list_invites_page"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Unauthorized access to invite view by user {current_user.id}: {e}")
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error viewing invite {invite_id} for admin {current_user.id}: {e}")
        flash(_("An error occurred while loading the invite details"), "error")
        return redirect(url_for("admin.list_invites_page"))


@admin_bp.route("/invites/<uuid:invite_id>/revoke", methods=["POST"])
@login_required
@require_admin
def revoke_invite_route(invite_id: uuid.UUID) -> ResponseReturnValue:
    """Revoke an invite to prevent its use."""
    try:
        uow = bootstrap.bootstrap()
        with uow:
            invite = revoke_invite(uow=uow, invite_id=invite_id, user_id=current_user.id)

        flash(_("Invite '%(code)s' has been revoked", code=invite.code), "success")
        return redirect(url_for("admin.list_invites_page"))

    except InviteNotFoundError as e:
        current_app.logger.warning(f"Invite {invite_id} not found for revocation by admin {current_user.id}: {e}")
        flash(_("Invite not found"), "error")
        return redirect(url_for("admin.list_invites_page"))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Unauthorized invite revocation attempt by user {current_user.id}: {e}")
        flash(_("You don't have permission to perform this action"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error revoking invite {invite_id} by admin {current_user.id}: {e}")
        flash(_("An error occurred while revoking the invite"), "error")
        return redirect(url_for("admin.list_invites_page"))


@admin_bp.route("/invites/cleanup", methods=["POST"])
@login_required
@require_admin
def cleanup_invites() -> ResponseReturnValue:
    """Clean up expired invites."""
    try:
        uow = bootstrap.bootstrap()
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
        current_app.logger.error(f"Error cleaning up invites by admin {current_user.id}: {e}")
        flash(_("An error occurred while cleaning up invites"), "error")
        return redirect(url_for("admin.list_invites_page"))
