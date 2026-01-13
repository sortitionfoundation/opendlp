"""ABOUTME: Authentication routes for login, logout, and registration
ABOUTME: Handles user authentication flow with invite-based registration"""

import markdown
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_babel import get_locale
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.wrappers import Response

from opendlp import bootstrap
from opendlp.bootstrap import get_email_adapter
from opendlp.domain.user_data_agreement import get_user_data_agreement_content
from opendlp.entrypoints.extensions import oauth
from opendlp.entrypoints.forms import LoginForm, PasswordResetForm, PasswordResetRequestForm, RegistrationForm
from opendlp.service_layer.exceptions import (
    InvalidCredentials,
    InvalidInvite,
    InvalidResetToken,
    PasswordTooWeak,
    RateLimitExceeded,
    UserAlreadyExists,
)
from opendlp.service_layer.password_reset_service import (
    request_password_reset,
    reset_password_with_token,
    send_password_reset_email,
    validate_reset_token,
)
from opendlp.service_layer.security import password_validators_help_text_html
from opendlp.service_layer.user_service import authenticate_user, create_user, find_or_create_oauth_user
from opendlp.translations import gettext as _

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> ResponseReturnValue:
    """User login page."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                # After form validation, these fields are guaranteed to be non-None
                assert form.email.data is not None
                assert form.password.data is not None
                user = authenticate_user(uow, form.email.data, form.password.data)
                login_user(user, remember=form.remember_me.data)

                # Redirect to next page if specified, otherwise dashboard
                next_page = request.args.get("next")
                if next_page and next_page.startswith("/"):
                    return redirect(next_page)
                return redirect(url_for("main.dashboard"))

        except InvalidCredentials:
            flash(_("Invalid email or password."), "error")
        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            flash(_("An error occurred during login. Please try again."), "error")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout() -> ResponseReturnValue:
    """User logout."""
    logout_user()
    flash(_("You have been logged out."), "info")
    return redirect(url_for("main.index"))


@auth_bp.route("/register", methods=["GET", "POST"])
@auth_bp.route("/register/<invite_code>", methods=["GET", "POST"])
def register(invite_code: str = "") -> ResponseReturnValue:
    """User registration with invite code."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegistrationForm()

    # Pre-populate invite code from URL
    if invite_code and not form.invite_code.data:
        form.invite_code.data = invite_code

    if form.validate_on_submit():
        try:
            uow = bootstrap.bootstrap()
            with uow:
                # After form validation, required fields are guaranteed to be non-None
                assert form.email.data is not None
                assert form.password.data is not None
                assert form.invite_code.data is not None
                user = create_user(
                    uow=uow,
                    email=form.email.data,
                    password=form.password.data,
                    invite_code=form.invite_code.data,
                    first_name=form.first_name.data or "",
                    last_name=form.last_name.data or "",
                    accept_data_agreement=form.accept_data_agreement.data or False,
                )

                # Log the user in immediately after registration
                login_user(user)
                flash(_("Registration successful! Welcome to OpenDLP."), "success")
                return redirect(url_for("main.dashboard"))

        except UserAlreadyExists as e:
            flash(str(e), "error")
        except InvalidInvite as e:
            flash(str(e), "error")
        except PasswordTooWeak as e:
            flash(_("Password is too weak: %(error)s", error=str(e)), "error")
        except Exception as e:
            current_app.logger.error(f"Registration error: {e}")
            flash(_("An error occurred during registration. Please try again."), "error")

    return render_template("auth/register.html", form=form, password_help=password_validators_help_text_html())


@auth_bp.route("/user-data-agreement")
def user_data_agreement() -> ResponseReturnValue:
    """Display the user data agreement."""
    # default to English
    locale = get_locale()
    language_code = locale.language if locale else "en"

    try:
        markdown_content = get_user_data_agreement_content(language_code)
        html_content = markdown.markdown(markdown_content)
    except KeyError:
        # Fallback to English if language not available
        markdown_content = get_user_data_agreement_content("en")
        html_content = markdown.markdown(markdown_content)

    return render_template("auth/user_data_agreement.html", agreement_content=html_content)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password() -> ResponseReturnValue:
    """Request password reset page."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = PasswordResetRequestForm()

    if form.validate_on_submit():
        try:
            assert form.email.data is not None
            uow = bootstrap.bootstrap()

            # Request password reset (creates token if valid user)
            success = request_password_reset(uow, form.email.data)

            if success:
                # Get the token and user to send email
                with uow:
                    user = uow.users.get_by_email(form.email.data)
                    if user and user.is_active and not user.oauth_provider:
                        # Get the most recent token for this user
                        tokens = uow.password_reset_tokens.get_active_tokens_for_user(user.id)
                        tokens_list = list(tokens)
                        if tokens_list:
                            # Send the email
                            email_adapter = get_email_adapter()
                            send_password_reset_email(
                                email_adapter=email_adapter,
                                user=user,
                                reset_token=tokens_list[0].token,
                            )

            # Always show success message (anti-enumeration)
            flash(
                _("If an account exists with this email, a password reset link has been sent."),
                "info",
            )
            return redirect(url_for("auth.login"))

        except RateLimitExceeded as e:
            flash(str(e), "error")
        except Exception as e:
            current_app.logger.error(f"Password reset request error: {e}")
            flash(_("An error occurred. Please try again."), "error")

    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token: str) -> ResponseReturnValue:
    """Reset password page with token."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = PasswordResetForm()

    # Validate token on GET request
    if request.method == "GET":
        try:
            uow = bootstrap.bootstrap()
            validate_reset_token(uow, token)
        except InvalidResetToken as e:
            flash(str(e), "error")
            return redirect(url_for("auth.forgot_password"))

    if form.validate_on_submit():
        try:
            assert form.password.data is not None
            uow = bootstrap.bootstrap()

            # Reset the password
            reset_password_with_token(uow, token, form.password.data)

            flash(_("Your password has been reset successfully. You can now log in."), "success")
            return redirect(url_for("auth.login"))

        except InvalidResetToken as e:
            flash(str(e), "error")
            return redirect(url_for("auth.forgot_password"))
        except PasswordTooWeak as e:
            flash(_("Password is too weak: %(error)s", error=str(e)), "error")
        except Exception as e:
            current_app.logger.error(f"Password reset error: {e}")
            flash(_("An error occurred. Please try again."), "error")

    return render_template(
        "auth/reset_password.html", form=form, token=token, password_help=password_validators_help_text_html()
    )


@auth_bp.route("/login/google")
def login_google() -> ResponseReturnValue:
    """Initiate Google OAuth login flow."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    # Store redirect URL in session for post-OAuth redirect
    next_page = request.args.get("next")
    if next_page and next_page.startswith("/"):
        session["oauth_next"] = next_page

    # Redirect to Google OAuth
    redirect_uri = url_for("auth.google_callback", _external=True)
    response = oauth.google.authorize_redirect(redirect_uri)
    assert isinstance(response, Response)
    return response


@auth_bp.route("/login/google/callback")
def google_callback() -> ResponseReturnValue:
    """Handle Google OAuth callback."""
    try:
        # Get OAuth token
        token = oauth.google.authorize_access_token()

        # Get user info from Google
        user_info = token.get("userinfo")
        if not user_info:
            user_info = oauth.google.userinfo()

        google_id = user_info.get("sub")
        email = user_info.get("email")
        first_name = user_info.get("given_name", "")
        last_name = user_info.get("family_name", "")

        if not google_id or not email:
            flash(_("Failed to get user information from Google"), "error")
            return redirect(url_for("auth.login"))

        uow = bootstrap.bootstrap()

        # Try to find or create OAuth user
        user, created = find_or_create_oauth_user(
            uow=uow,
            provider="google",
            oauth_id=google_id,
            email=email,
            first_name=first_name,
            last_name=last_name,
            invite_code=session.get("oauth_invite_code"),
            accept_data_agreement=session.get("oauth_accept_agreement", False),
        )

        # Clear OAuth session data
        session.pop("oauth_invite_code", None)
        session.pop("oauth_accept_agreement", None)

        # Log user in
        login_user(user)

        if created:
            flash(_("Account created successfully! Welcome to OpenDLP."), "success")
        else:
            flash(_("Signed in successfully"), "success")

        # Redirect to next page or dashboard
        next_page = session.pop("oauth_next", None)
        if next_page and next_page.startswith("/"):
            return redirect(next_page)
        return redirect(url_for("main.dashboard"))

    except InvalidInvite as e:
        # User needs invite code - redirect to OAuth registration
        flash(str(e), "error")
        return redirect(url_for("auth.register_google"))
    except Exception as e:
        current_app.logger.error(f"Google OAuth callback error: {e}")
        flash(_("An error occurred during Google sign in. Please try again."), "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/register/google", methods=["GET", "POST"])
def register_google() -> ResponseReturnValue:
    """Register with Google OAuth (requires invite code)."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    # Import here to avoid circular import
    from opendlp.entrypoints.forms import OAuthRegistrationForm

    form = OAuthRegistrationForm()

    if form.validate_on_submit():
        # Store invite code and agreement in session
        assert form.invite_code.data is not None
        session["oauth_invite_code"] = form.invite_code.data
        session["oauth_accept_agreement"] = form.accept_data_agreement.data or False

        # Redirect to Google OAuth
        return redirect(url_for("auth.login_google"))

    return render_template("auth/register_google.html", form=form)
