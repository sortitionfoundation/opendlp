"""ABOUTME: Admin routes for user management and system administration
ABOUTME: Handles admin-only features like viewing and editing users, requires admin role"""

import uuid

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.decorators import require_admin
from opendlp.entrypoints.forms import EditUserForm
from opendlp.service_layer.exceptions import InvalidCredentials
from opendlp.service_layer.user_service import get_user_by_id, get_user_stats, list_users_paginated, update_user
from opendlp.translations import gettext as _

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


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

    except InvalidCredentials as e:
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

    except ValueError as e:
        current_app.logger.warning(f"User {user_id} not found for admin {current_user.id}: {e}")
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InvalidCredentials as e:
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
                # Convert role string to GlobalRole enum
                global_role = GlobalRole(form.global_role.data.lower()) if form.global_role.data else None

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

            except ValueError as e:
                current_app.logger.warning(f"Validation error updating user {user_id} by admin {current_user.id}: {e}")
                flash(str(e), "error")
            except InvalidCredentials as e:
                current_app.logger.warning(f"Unauthorized user update attempt by user {current_user.id}: {e}")
                flash(_("You don't have permission to perform this action"), "error")
                return redirect(url_for("admin.view_user", user_id=user_id))
            except Exception as e:
                current_app.logger.error(f"Error updating user {user_id} by admin {current_user.id}: {e}")
                flash(_("An error occurred while updating the user"), "error")

        return render_template("admin/user_edit.html", form=form, user=user), 200

    except ValueError as e:
        current_app.logger.warning(f"User {user_id} not found for edit by admin {current_user.id}: {e}")
        flash(_("User not found"), "error")
        return redirect(url_for("admin.list_users"))
    except InvalidCredentials as e:
        current_app.logger.warning(f"Unauthorized access to user edit by user {current_user.id}: {e}")
        flash(_("You don't have permission to view this page"), "error")
        return redirect(url_for("main.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Error loading user edit page for user {user_id}, admin {current_user.id}: {e}")
        flash(_("An error occurred while loading the edit page"), "error")
        return redirect(url_for("admin.list_users"))
