"""ABOUTME: Profile management routes for users to view and edit their own account
ABOUTME: Handles profile viewing, editing, and password changes for self-service"""

from flask import Blueprint, current_app, flash, redirect, render_template, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required

from opendlp import bootstrap
from opendlp.entrypoints.extensions import oauth
from opendlp.entrypoints.forms import ChangeOwnPasswordForm, EditOwnProfileForm, SetPasswordForm
from opendlp.service_layer.exceptions import CannotRemoveLastAuthMethod, InvalidCredentials, PasswordTooWeak
from opendlp.service_layer.security import (
    TempUser,
    hash_password,
    password_validators_help_text_html,
    validate_password_strength,
)
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
    # OAuth users without password should use set-password instead
    if current_user.oauth_provider and not current_user.password_hash:
        flash(_("You need to set a password first"), "info")
        return redirect(url_for("profile.set_password"))

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
    # Note: We allow linking even if user has another OAuth provider
    # The single-provider choice model means linking Google will replace
    # any existing OAuth provider (e.g., Microsoft)

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


@profile_bp.route("/profile/link-microsoft")
@login_required
def link_microsoft() -> ResponseReturnValue:
    """Link Microsoft account to existing user."""
    # Note: We allow linking even if user has another OAuth provider
    # The single-provider choice model means linking Microsoft will replace
    # any existing OAuth provider (e.g., Google)

    # Store action in session for callback
    session["oauth_action"] = "link"

    # Redirect to Microsoft OAuth
    redirect_uri = url_for("profile.microsoft_link_callback", _external=True)
    from werkzeug.wrappers import Response

    response = oauth.microsoft.authorize_redirect(redirect_uri)
    assert isinstance(response, Response)
    return response


@profile_bp.route("/profile/link-microsoft/callback")
@login_required
def microsoft_link_callback() -> ResponseReturnValue:
    """Handle Microsoft OAuth linking callback."""
    try:
        # Verify this is a linking action
        if session.get("oauth_action") != "link":
            flash(_("Invalid OAuth linking request"), "error")
            return redirect(url_for("profile.view"))

        session.pop("oauth_action", None)

        # Get OAuth token
        # Skip issuer validation for Microsoft /common endpoint since it returns tenant-specific issuer
        token = oauth.microsoft.authorize_access_token(claims_options={"iss": {"essential": False}})
        user_info = token.get("userinfo")
        if not user_info:
            user_info = oauth.microsoft.userinfo()

        microsoft_id = user_info.get("sub")
        email = user_info.get("email")

        if not microsoft_id or not email:
            flash(_("Failed to get user information from Microsoft"), "error")
            return redirect(url_for("profile.view"))

        uow = bootstrap.bootstrap()

        # Link OAuth to current user
        updated_user = link_oauth_to_user(
            uow=uow, user_id=current_user.id, provider="microsoft", oauth_id=microsoft_id, oauth_email=email
        )

        # Update current_user
        current_user.oauth_provider = updated_user.oauth_provider
        current_user.oauth_id = updated_user.oauth_id

        flash(_("Microsoft account linked successfully"), "success")
        return redirect(url_for("profile.view"))

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("profile.view"))
    except Exception as e:
        current_app.logger.error(f"Microsoft linking error: {e}")
        flash(_("An error occurred while linking your Microsoft account"), "error")
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


@profile_bp.route("/profile/set-password", methods=["GET", "POST"])
@login_required
def set_password() -> ResponseReturnValue:
    """Set password for OAuth users who don't have one."""
    # Redirect if user already has password
    if current_user.password_hash:
        flash(_("You already have a password. Use 'Change password' instead."), "info")
        return redirect(url_for("profile.view"))

    # Require OAuth provider (can't have no auth methods)
    if not current_user.oauth_provider:
        flash(_("Cannot set password without another authentication method"), "error")
        return redirect(url_for("profile.view"))

    form = SetPasswordForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                assert form.new_password.data is not None

                # Get user from database
                user = uow.users.get(current_user.id)
                if not user:
                    raise ValueError("User not found")

                # Validate password strength
                temp_user = TempUser(email=user.email, first_name=user.first_name, last_name=user.last_name)
                is_valid, error_msg = validate_password_strength(form.new_password.data, temp_user)
                if not is_valid:
                    raise PasswordTooWeak(error_msg)

                # Hash and set password
                user.password_hash = hash_password(form.new_password.data)

                uow.commit()

            # Update current_user session object
            current_user.password_hash = user.password_hash

            flash(_("Password set successfully"), "success")
            return redirect(url_for("profile.view"))

        except PasswordTooWeak as e:
            flash(_("Password is too weak: %(error)s", error=str(e)), "error")
        except Exception as e:
            current_app.logger.error(f"Unexpected set password error for user {current_user.id}: {e}")
            flash(_("An error occurred while setting your password"), "error")

    return render_template(
        "profile/set_password.html", form=form, password_help=password_validators_help_text_html()
    ), 200
