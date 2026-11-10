"""ABOUTME: Profile management routes for users to view and edit their own account
ABOUTME: Handles profile viewing, editing, and password changes for self-service"""

from typing import Any

import structlog
from flask import Blueprint, abort, flash, redirect, render_template, render_template_string, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from werkzeug.wrappers import Response

from opendlp import bootstrap
from opendlp.domain.value_objects import global_role_descriptions, global_role_labels
from opendlp.entrypoints.extensions import oauth
from opendlp.entrypoints.forms import ChangeOwnPasswordForm, EditOwnProfileForm, SetPasswordForm
from opendlp.service_layer import two_factor_service
from opendlp.service_layer.exceptions import CannotRemoveLastAuthMethod, InvalidCredentials, PasswordTooWeak
from opendlp.service_layer.security import (
    TempUser,
    hash_password,
    password_validators_help_text_html,
    validate_password_strength,
)
from opendlp.service_layer.two_factor_service import TwoFactorSetupError, TwoFactorVerificationError
from opendlp.service_layer.user_service import (
    change_own_password,
    link_oauth_to_user,
    remove_oauth_auth,
    remove_password_auth,
    update_own_profile,
)
from opendlp.translations import gettext as _

profile_bp = Blueprint("profile", __name__)

logger = structlog.get_logger(__name__)

# The names on My account, each edited in place in a row of its own
# (templates/backoffice/profile/_name_row.html).
NAME_FIELDS = ("first_name", "last_name")

# One name's row on its own, as htmx swaps it in for the row on the page, with
# any flash appended out of band to the page's floating alerts.
_NAME_ROW_RESPONSE = (
    '{% from "backoffice/profile/_name_row.html" import name_row %}'
    '{% from "backoffice/components/floating_alerts.html" import floating_alerts %}'
    "{{ name_row(field, value, submitted=submitted, error=error, return_focus=return_focus) }}"
    "{{ floating_alerts(oob=true) }}"
)


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _view_context() -> dict[str, Any]:
    """What My account renders from, besides current_user."""
    return {
        "role_label": global_role_labels[current_user.global_role],
        "role_description": global_role_descriptions[current_user.global_role],
    }


@profile_bp.route("/profile")
@login_required
def view() -> ResponseReturnValue:
    """View own profile."""
    return render_template("backoffice/profile/view.html", **_view_context()), 200


@profile_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit() -> ResponseReturnValue:
    """Save one name, edited in place on My account.

    Each name's row posts its own field, named by `field`. Over htmx the answer
    is that row again: at rest with the saved name, the success flash appended
    to the page's alerts, or still open with the reason under the field (422).
    Without htmx a save goes back to My account, and a refusal renders My
    account with that row open. There is no edit page, so a GET goes to My
    account.
    """
    if request.method == "GET":
        return redirect(url_for("profile.view"))

    field = request.form.get("field", "")
    if field not in NAME_FIELDS:
        abort(400)

    # Built over the stored user, so the name this row did not post keeps its stored value.
    form = EditOwnProfileForm(obj=current_user)
    if form.validate_on_submit():
        value = form[field].data or ""
        try:
            uow = bootstrap.get_flask_uow()
            with uow:
                user = update_own_profile(
                    uow=uow,
                    user_id=current_user.id,
                    first_name=value if field == "first_name" else None,
                    last_name=value if field == "last_name" else None,
                )
        except Exception as e:
            logger.error("Unexpected profile update error", user_id=str(current_user.id), error=str(e))
            error = _("An error occurred while updating your profile")
        else:
            flash(_("Profile updated successfully"), "success")
            if _is_htmx():
                return _name_row_response(
                    field, getattr(user, field), return_focus=request.form.get("return_focus") == "1"
                ), 200
            return redirect(url_for("profile.view"))
    else:
        error = "\n".join(form[field].errors) or _("An error occurred while updating your profile")

    submitted = request.form.get(field, "")
    if _is_htmx():
        return _name_row_response(field, getattr(current_user, field), submitted=submitted, error=error), 422
    return render_template(
        "backoffice/profile/view.html",
        name_errors={field: error},
        name_submitted={field: submitted},
        **_view_context(),
    ), 200


def _name_row_response(
    field: str, value: str, submitted: str | None = None, error: str = "", return_focus: bool = False
) -> str:
    return render_template_string(
        _NAME_ROW_RESPONSE, field=field, value=value, submitted=submitted, error=error, return_focus=return_focus
    )


@profile_bp.route("/profile/change-password", methods=["GET", "POST"])
@login_required
def change_password() -> ResponseReturnValue:
    """Change own password."""
    # OAuth users without a usable password should use set-password instead -
    # there is no current password for them to type into this form.
    if current_user.oauth_provider and not current_user.has_usable_password():
        flash(_("You need to set a password first"), "info")
        return redirect(url_for("profile.set_password"))

    form = ChangeOwnPasswordForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.get_flask_uow()
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
            logger.error("Unexpected password change error", user_id=str(current_user.id), error=str(e))
            flash(_("An error occurred while changing your password"), "error")

    return render_template(
        "backoffice/profile/change_password.html", form=form, password_help=password_validators_help_text_html()
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

        uow = bootstrap.get_flask_uow()

        # Link OAuth to current user
        with uow:
            link_oauth_to_user(
                uow=uow, user_id=current_user.id, provider="google", oauth_id=google_id, oauth_email=email
            )

        flash(_("Google account linked successfully"), "success")
        return redirect(url_for("profile.view"))

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("profile.view"))
    except Exception as e:
        logger.error("Google linking error", error=str(e))
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

        uow = bootstrap.get_flask_uow()

        # Link OAuth to current user
        with uow:
            link_oauth_to_user(
                uow=uow, user_id=current_user.id, provider="microsoft", oauth_id=microsoft_id, oauth_email=email
            )

        flash(_("Microsoft account linked successfully"), "success")
        return redirect(url_for("profile.view"))

    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("profile.view"))
    except Exception as e:
        logger.error("Microsoft linking error", error=str(e))
        flash(_("An error occurred while linking your Microsoft account"), "error")
        return redirect(url_for("profile.view"))


@profile_bp.route("/profile/remove-password", methods=["POST"])
@login_required
def remove_password() -> ResponseReturnValue:
    """Remove password authentication (requires OAuth)."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            remove_password_auth(uow=uow, user_id=current_user.id)

        flash(_("Password authentication removed successfully"), "success")
    except CannotRemoveLastAuthMethod as e:
        flash(str(e), "error")
    except Exception as e:
        logger.error("Remove password error", error=str(e))
        flash(_("An error occurred while removing password authentication"), "error")

    return redirect(url_for("profile.view"))


@profile_bp.route("/profile/remove-oauth", methods=["POST"])
@login_required
def remove_oauth() -> ResponseReturnValue:
    """Remove OAuth authentication (requires password)."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            remove_oauth_auth(uow=uow, user_id=current_user.id)

        flash(_("OAuth authentication removed successfully"), "success")
    except CannotRemoveLastAuthMethod as e:
        flash(str(e), "error")
    except Exception as e:
        logger.error("Remove OAuth error", error=str(e))
        flash(_("An error occurred while removing OAuth authentication"), "error")

    return redirect(url_for("profile.view"))


@profile_bp.route("/profile/set-password", methods=["GET", "POST"])
@login_required
def set_password() -> ResponseReturnValue:
    """Set password for OAuth users who don't have one."""
    # Redirect if user already has a password they can sign in with. One made
    # unusable by a lockout does not count - setting a new one is the point.
    if current_user.has_usable_password():
        flash(_("You already have a password. Use 'Change password' instead."), "info")
        return redirect(url_for("profile.view"))

    # Require OAuth provider (can't have no auth methods)
    if not current_user.oauth_provider:
        flash(_("Cannot set password without another authentication method"), "error")
        return redirect(url_for("profile.view"))

    form = SetPasswordForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.get_flask_uow()
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

            flash(_("Password set successfully"), "success")
            return redirect(url_for("profile.view"))

        except PasswordTooWeak as e:
            flash(_("Password is too weak: %(error)s", error=str(e)), "error")
        except Exception as e:
            logger.error("Unexpected set password error", user_id=str(current_user.id), error=str(e))
            flash(_("An error occurred while setting your password"), "error")

    return render_template(
        "backoffice/profile/set_password.html", form=form, password_help=password_validators_help_text_html()
    ), 200


@profile_bp.route("/profile/2fa")
@login_required
def two_factor_settings() -> ResponseReturnValue:
    """View 2FA settings and status."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            status = two_factor_service.get_2fa_status(uow, current_user.id)

        return render_template("backoffice/profile/2fa_settings.html", status=status), 200

    except Exception as e:
        logger.error("Error loading 2FA settings", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while loading 2FA settings"), "error")
        return redirect(url_for("profile.view"))


@profile_bp.route("/profile/2fa/setup")
@login_required
def setup_2fa() -> ResponseReturnValue:
    """Start 2FA setup - show QR code and backup codes."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            totp_secret, qr_code_url, backup_codes = two_factor_service.setup_2fa(uow, current_user.id)

        # Store the secret and backup codes in session for the enable step
        session["totp_setup_secret"] = totp_secret
        session["totp_setup_backup_codes"] = backup_codes

        return render_template(
            "backoffice/profile/2fa_setup.html",
            qr_code_url=qr_code_url,
            totp_secret=totp_secret,
            backup_codes=backup_codes,
        ), 200

    except TwoFactorSetupError as e:
        flash(str(e), "error")
        return redirect(url_for("profile.two_factor_settings"))
    except Exception as e:
        logger.error("Error starting 2FA setup", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while setting up 2FA"), "error")
        return redirect(url_for("profile.two_factor_settings"))


@profile_bp.route("/profile/2fa/enable", methods=["POST"])
@login_required
def enable_2fa() -> ResponseReturnValue:
    """Complete 2FA setup by verifying TOTP code."""
    totp_code = request.form.get("totp_code", "").strip()

    if not totp_code:
        flash(_("Please enter the verification code from your authenticator app"), "error")
        return redirect(url_for("profile.setup_2fa"))

    # Get the secret and backup codes from session
    totp_secret = session.get("totp_setup_secret")
    backup_codes = session.get("totp_setup_backup_codes")

    if not totp_secret or not backup_codes:
        flash(_("Setup session expired. Please start over."), "error")
        return redirect(url_for("profile.two_factor_settings"))

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            two_factor_service.enable_2fa(uow, current_user.id, totp_secret, totp_code, backup_codes)

        # Clear setup session data
        session.pop("totp_setup_secret", None)
        session.pop("totp_setup_backup_codes", None)

        flash(_("Two-factor authentication has been enabled successfully"), "success")
        return redirect(url_for("profile.two_factor_settings"))

    except TwoFactorVerificationError as e:
        flash(str(e), "error")
        return redirect(url_for("profile.setup_2fa"))
    except Exception as e:
        logger.error("Error enabling 2FA", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while enabling 2FA"), "error")
        return redirect(url_for("profile.two_factor_settings"))


@profile_bp.route("/profile/2fa/disable", methods=["POST"])
@login_required
def disable_2fa() -> ResponseReturnValue:
    """Disable 2FA (requires TOTP code)."""
    totp_code = request.form.get("totp_code", "").strip()

    if not totp_code:
        flash(_("Please enter your verification code to disable 2FA"), "error")
        return redirect(url_for("profile.two_factor_settings"))

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            two_factor_service.disable_2fa(uow, current_user.id, totp_code)

        flash(_("Two-factor authentication has been disabled"), "success")
        return redirect(url_for("profile.two_factor_settings"))

    except TwoFactorVerificationError as e:
        flash(str(e), "error")
        return redirect(url_for("profile.two_factor_settings"))
    except Exception as e:
        logger.error("Error disabling 2FA", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while disabling 2FA"), "error")
        return redirect(url_for("profile.two_factor_settings"))


@profile_bp.route("/profile/2fa/backup-codes/regenerate", methods=["POST"])
@login_required
def regenerate_backup_codes() -> ResponseReturnValue:
    """Regenerate backup codes (requires TOTP code)."""
    totp_code = request.form.get("totp_code", "").strip()

    if not totp_code:
        flash(_("Please enter your verification code to regenerate backup codes"), "error")
        return redirect(url_for("profile.two_factor_settings"))

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            backup_codes = two_factor_service.regenerate_backup_codes(uow, current_user.id, totp_code)

        return render_template("backoffice/profile/2fa_backup_codes.html", backup_codes=backup_codes), 200

    except TwoFactorVerificationError as e:
        flash(str(e), "error")
        return redirect(url_for("profile.two_factor_settings"))
    except Exception as e:
        logger.error("Error regenerating backup codes", user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while regenerating backup codes"), "error")
        return redirect(url_for("profile.two_factor_settings"))
