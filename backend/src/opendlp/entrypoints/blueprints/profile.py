"""ABOUTME: Profile management routes for users to view and edit their own account
ABOUTME: Handles profile viewing, editing, and password changes for self-service"""

from flask import Blueprint, current_app, flash, redirect, render_template, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.extensions import oauth
from opendlp.entrypoints.forms import ChangeOwnPasswordForm, EditOwnProfileForm
from opendlp.service_layer.exceptions import CannotRemoveLastAuthMethod, InvalidCredentials, PasswordTooWeak
from opendlp.service_layer.security import password_validators_help_text_html
from opendlp.service_layer.user_service import (
    change_own_password,
    link_oauth_to_user,
    remove_oauth_auth,
    remove_password_auth,
    update_own_profile,
)
from opendlp.translations import gettext as _

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/profile")
@login_required
def view() -> ResponseReturnValue:
    """View own profile."""
    return render_template("profile/view.html"), 200


@profile_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit() -> ResponseReturnValue:
    """Edit own profile."""
    form = EditOwnProfileForm(obj=current_user)

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                updated_user = update_own_profile(
                    uow=uow,
                    user_id=current_user.id,
                    first_name=form.first_name.data or "",
                    last_name=form.last_name.data or "",
                )

            # Update current_user object with new values
            current_user.first_name = updated_user.first_name
            current_user.last_name = updated_user.last_name

            flash(_("Profile updated successfully"), "success")
            return redirect(url_for("profile.view"))

        except Exception as e:
            current_app.logger.error(f"Unexpected profile update error for user {current_user.id}: {e}")
            flash(_("An error occurred while updating your profile"), "error")

    return render_template("profile/edit.html", form=form), 200


@profile_bp.route("/profile/change-password", methods=["GET", "POST"])
@login_required
def change_password() -> ResponseReturnValue:
    """Change own password."""
    # OAuth users don't have passwords, redirect them to profile view
    if current_user.oauth_provider:
        flash(
            _("You cannot change your password as you sign in with %(provider)s", provider=current_user.oauth_provider),
            "info",
        )
        return redirect(url_for("profile.view"))

    form = ChangeOwnPasswordForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                # After form validation, required fields are guaranteed to be non-None
                assert form.current_password.data is not None
                assert form.new_password.data is not None

                change_own_password(
                    uow=uow,
                    user_id=current_user.id,
                    current_password=form.current_password.data,
                    new_password=form.new_password.data,
                )

            flash(_("Password changed successfully"), "success")
            return redirect(url_for("profile.view"))

        except InvalidCredentials:
            flash(_("Current password is incorrect"), "error")
        except PasswordTooWeak as e:
            flash(_("New password is too weak: %(error)s", error=str(e)), "error")
        except Exception as e:
            current_app.logger.error(f"Unexpected password change error for user {current_user.id}: {e}")
            flash(_("An error occurred while changing your password"), "error")

    return render_template(
        "profile/change_password.html", form=form, password_help=password_validators_help_text_html()
    ), 200


@profile_bp.route("/profile/link-google")
@login_required
def link_google() -> ResponseReturnValue:
    """Link Google account to existing user."""
    if current_user.oauth_provider:
        flash(_("You already have an OAuth account linked"), "info")
        return redirect(url_for("profile.view"))

    # Store action in session for callback
    session["oauth_action"] = "link"

    # Redirect to Google OAuth
    redirect_uri = url_for("profile.google_link_callback", _external=True)
    from werkzeug.wrappers import Response

    response = oauth.google.authorize_redirect(redirect_uri)
    assert isinstance(response, Response)
    return response


@profile_bp.route("/profile/link-google/callback")
@login_required
def google_link_callback() -> ResponseReturnValue:
    """Handle Google OAuth linking callback."""
    try:
        # Verify this is a linking action
        if session.get("oauth_action") != "link":
            flash(_("Invalid OAuth linking request"), "error")
            return redirect(url_for("profile.view"))

        session.pop("oauth_action", None)

        # Get OAuth token
        token = oauth.google.authorize_access_token()
        user_info = token.get("userinfo")
        if not user_info:
            user_info = oauth.google.userinfo()

        google_id = user_info.get("sub")
        email = user_info.get("email")

        if not google_id or not email:
            flash(_("Failed to get user information from Google"), "error")
            return redirect(url_for("profile.view"))

        uow = bootstrap.bootstrap()

        # Link OAuth to current user
        updated_user = link_oauth_to_user(
            uow=uow, user_id=current_user.id, provider="google", oauth_id=google_id, oauth_email=email
        )

        # Update current_user
        current_user.oauth_provider = updated_user.oauth_provider
        current_user.oauth_id = updated_user.oauth_id

        flash(_("Google account linked successfully"), "success")
        return redirect(url_for("profile.view"))

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("profile.view"))
    except Exception as e:
        current_app.logger.error(f"Google linking error: {e}")
        flash(_("An error occurred while linking your Google account"), "error")
        return redirect(url_for("profile.view"))


@profile_bp.route("/profile/remove-password", methods=["POST"])
@login_required
def remove_password() -> ResponseReturnValue:
    """Remove password authentication (requires OAuth)."""
    try:
        uow = bootstrap.bootstrap()
        remove_password_auth(uow=uow, user_id=current_user.id)

        # Update current_user
        current_user.password_hash = None

        flash(_("Password authentication removed successfully"), "success")
    except CannotRemoveLastAuthMethod as e:
        flash(str(e), "error")
    except Exception as e:
        current_app.logger.error(f"Remove password error: {e}")
        flash(_("An error occurred while removing password authentication"), "error")

    return redirect(url_for("profile.view"))


@profile_bp.route("/profile/remove-oauth", methods=["POST"])
@login_required
def remove_oauth() -> ResponseReturnValue:
    """Remove OAuth authentication (requires password)."""
    try:
        uow = bootstrap.bootstrap()
        remove_oauth_auth(uow=uow, user_id=current_user.id)

        # Update current_user
        current_user.oauth_provider = None
        current_user.oauth_id = None

        flash(_("OAuth authentication removed successfully"), "success")
    except CannotRemoveLastAuthMethod as e:
        flash(str(e), "error")
    except Exception as e:
        current_app.logger.error(f"Remove OAuth error: {e}")
        flash(_("An error occurred while removing OAuth authentication"), "error")

    return redirect(url_for("profile.view"))
