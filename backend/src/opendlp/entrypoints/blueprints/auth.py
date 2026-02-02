"""ABOUTME: Authentication routes for login, logout, and registration
ABOUTME: Handles user authentication flow with invite-based registration"""

import uuid
from datetime import UTC, datetime, timedelta

import markdown
from django.utils.http import url_has_allowed_host_and_scheme
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask.typing import ResponseReturnValue
from flask_babel import get_locale
from flask_login import current_user, login_required, login_user, logout_user
from markupsafe import Markup
from werkzeug.wrappers import Response

from opendlp import bootstrap
from opendlp.bootstrap import get_email_adapter, get_template_renderer, get_url_generator
from opendlp.domain.user_data_agreement import get_user_data_agreement_content
from opendlp.entrypoints.extensions import oauth
from opendlp.entrypoints.forms import (
    LoginForm,
    PasswordResetForm,
    PasswordResetRequestForm,
    RegistrationForm,
    ResendConfirmationForm,
)
from opendlp.service_layer import totp_service
from opendlp.service_layer.email_confirmation_service import (
    confirm_email_with_token,
    resend_confirmation_email,
    send_confirmation_email,
)
from opendlp.service_layer.exceptions import (
    EmailNotConfirmed,
    InvalidConfirmationToken,
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
from opendlp.service_layer.two_factor_service import TwoFactorVerificationError
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.service_layer.user_service import authenticate_user, create_user, find_or_create_oauth_user
from opendlp.translations import gettext as _

auth_bp = Blueprint("auth", __name__)


def get_safe_next_page(next_page: str | None, default: str = "") -> str:
    """
    Check if the next page link is safe, using the django function.

    Safe means that the link is a relative or absolute link, but does not have a netloc or host.
    """
    next_page = next_page or ""
    return next_page if url_has_allowed_host_and_scheme(next_page, allowed_hosts=None) else default


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

                # Check if user requires 2FA
                if user.requires_2fa():
                    # Store user info in session for 2FA verification
                    session["pending_2fa_user_id"] = str(user.id)
                    session["pending_2fa_remember_me"] = form.remember_me.data
                    session["pending_2fa_timestamp"] = request.utcnow.timestamp() if hasattr(request, "utcnow") else 0

                    # Store next page if specified
                    safe_next_page = get_safe_next_page(request.args.get("next"))
                    if safe_next_page:
                        session["pending_2fa_next"] = safe_next_page

                    return redirect(url_for("auth.verify_2fa"))

                # No 2FA required - log in directly
                login_user(user, remember=form.remember_me.data)

                flash(_("Signed in successfully"), "success")

                # Redirect to next page if specified, otherwise dashboard
                next_page = request.args.get("next")
                return redirect(get_safe_next_page(next_page, default=url_for("main.dashboard")))

        except InvalidCredentials:
            flash(_("Invalid email or password."), "error")
        except EmailNotConfirmed:
            flash(
                _("Please confirm your email address before logging in. Check your inbox for the confirmation link."),
                "error",
            )
            flash(
                Markup(  # noqa: S704
                    _(
                        'Didn\'t receive the email? <a href="%(url)s">Resend confirmation</a>',
                        url=url_for("auth.resend_confirmation"),
                    )
                ),
                "info",
            )
        except Exception as e:
            current_app.logger.error(f"Login error: {e}")
            flash(_("An error occurred during login. Please try again."), "error")

    return render_template("auth/login.html", form=form)


def _validate_2fa_session() -> tuple[bool, str | None]:
    """Validate 2FA session and return (is_valid, user_id_str).

    Returns (False, None) if invalid and sets flash message.
    """
    # Check if user has pending 2FA verification
    pending_user_id_str = session.get("pending_2fa_user_id")
    if not pending_user_id_str:
        flash(_("No pending two-factor authentication. Please log in first."), "error")
        return (False, None)

    # Check session timeout (5 minutes)
    pending_timestamp = session.get("pending_2fa_timestamp", 0)
    if pending_timestamp:
        pending_time = datetime.fromtimestamp(pending_timestamp, UTC)
        if datetime.now(UTC) - pending_time > timedelta(minutes=5):
            # Clear expired session
            session.pop("pending_2fa_user_id", None)
            session.pop("pending_2fa_remember_me", None)
            session.pop("pending_2fa_timestamp", None)
            session.pop("pending_2fa_next", None)
            flash(_("Two-factor authentication session expired. Please log in again."), "error")
            return (False, None)

    # Validate UUID format
    try:
        uuid.UUID(pending_user_id_str)
    except ValueError:
        flash(_("Invalid session. Please log in again."), "error")
        return (False, None)

    return (True, pending_user_id_str)


def _verify_2fa_code_for_user(uow: AbstractUnitOfWork, user_id: uuid.UUID, verification_code: str) -> tuple[bool, bool]:
    """Verify 2FA code (TOTP or backup code) for a user.

    Returns (success, is_backup_code).
    """
    # Try TOTP code first
    success = False
    is_backup_code = False

    with uow:
        user = uow.users.get(user_id)
        if user and user.totp_secret_encrypted:
            decrypted_secret = totp_service.decrypt_totp_secret(user.totp_secret_encrypted, user_id)
            if totp_service.verify_totp_code(decrypted_secret, verification_code):
                success = True
                totp_service.record_totp_attempt(uow, user_id, success=True)

    # If TOTP failed, try backup code
    if not success:
        with uow:
            if totp_service.verify_backup_code(uow, user_id, verification_code):
                success = True
                is_backup_code = True

    return (success, is_backup_code)


def _complete_2fa_login(uow: AbstractUnitOfWork, user_id: uuid.UUID, is_backup_code: bool) -> ResponseReturnValue:
    """Complete 2FA login and redirect to appropriate page."""
    # Clear session and get login details
    remember_me = session.pop("pending_2fa_remember_me", False)
    next_page = session.pop("pending_2fa_next", None)
    session.pop("pending_2fa_user_id", None)
    session.pop("pending_2fa_timestamp", None)

    # Get fresh user object for login
    with uow:
        user = uow.users.get(user_id)
        login_user(user, remember=remember_me)

    # Show backup code warning if used
    if is_backup_code:
        with uow:
            remaining = totp_service.count_remaining_backup_codes(uow, user_id)
        flash(
            _(
                "Backup code used successfully. You have %(remaining)s backup codes remaining.",
                remaining=remaining,
            ),
            "warning",
        )
    else:
        flash(_("Signed in successfully"), "success")

    # Redirect to next page or dashboard
    return redirect(get_safe_next_page(next_page, default=url_for("main.dashboard")))


@auth_bp.route("/login/verify-2fa", methods=["GET", "POST"])
def verify_2fa() -> ResponseReturnValue:
    """Two-factor authentication verification page."""
    # Validate session
    is_valid, pending_user_id_str = _validate_2fa_session()
    if not is_valid:
        return redirect(url_for("auth.login"))

    pending_user_id = uuid.UUID(pending_user_id_str)

    if request.method == "POST":
        verification_code = request.form.get("verification_code", "").strip()

        if not verification_code:
            flash(_("Please enter a verification code"), "error")
            return render_template("auth/verify_2fa.html")

        try:
            uow = bootstrap.bootstrap()

            # Check rate limit
            with uow:
                is_allowed, attempts_remaining = totp_service.check_totp_rate_limit(uow, pending_user_id)

            if not is_allowed:
                flash(
                    _("Too many failed attempts. Please try again in 15 minutes or use a backup code."),
                    "error",
                )
                return render_template("auth/verify_2fa.html", rate_limited=True)

            # Get user
            with uow:
                user = uow.users.get(pending_user_id)
                if not user or not user.totp_enabled:
                    flash(_("Two-factor authentication is not enabled for this account."), "error")
                    return redirect(url_for("auth.login"))

            # Verify code (TOTP or backup code)
            success, is_backup_code = _verify_2fa_code_for_user(uow, pending_user_id, verification_code)

            # Handle failed verification
            if not success:
                with uow:
                    totp_service.record_totp_attempt(uow, pending_user_id, success=False)
                    _rate_limit_allowed, attempts_remaining = totp_service.check_totp_rate_limit(uow, pending_user_id)

                if attempts_remaining > 0:
                    flash(
                        _("Invalid verification code. %(attempts)s attempts remaining.", attempts=attempts_remaining),
                        "error",
                    )
                else:
                    flash(
                        _("Too many failed attempts. Please try again in 15 minutes or use a backup code."),
                        "error",
                    )
                return render_template("auth/verify_2fa.html")

            # Success! Complete login
            return _complete_2fa_login(uow, pending_user_id, is_backup_code)

        except TwoFactorVerificationError as e:
            flash(str(e), "error")
            return render_template("auth/verify_2fa.html")
        except Exception as e:
            current_app.logger.error(f"2FA verification error: {e}")
            flash(_("An error occurred during verification. Please try again."), "error")
            return render_template("auth/verify_2fa.html")

    # GET request - show 2FA form
    return render_template("auth/verify_2fa.html")


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
                user, token = create_user(
                    uow=uow,
                    email=form.email.data,
                    password=form.password.data,
                    invite_code=form.invite_code.data,
                    first_name=form.first_name.data or "",
                    last_name=form.last_name.data or "",
                    accept_data_agreement=form.accept_data_agreement.data or False,
                )

                # If OAuth user (token is None), auto-login as before
                if token is None:
                    login_user(user)
                    flash(_("Registration successful! Welcome to OpenDLP."), "success")
                    return redirect(url_for("main.dashboard"))

                # If password user, send confirmation email
                email_adapter = get_email_adapter()
                template_renderer = get_template_renderer(current_app)
                url_generator = get_url_generator(current_app)
                send_confirmation_email(email_adapter, template_renderer, url_generator, user, token.token)
                flash(
                    _("Registration successful! Please check your email to confirm your account."),
                    "info",
                )
                return redirect(url_for("auth.login"))

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


@auth_bp.route("/confirm-email/<token>")
def confirm_email(token: str) -> ResponseReturnValue:
    """Confirm email with token."""
    try:
        uow = bootstrap.bootstrap()
        user = confirm_email_with_token(uow, token)
        flash(_("Email confirmed successfully! You can now log in."), "success")
        # Auto-login for better UX
        login_user(user)
        return redirect(url_for("main.dashboard"))
    except InvalidConfirmationToken as e:
        flash(str(e), "error")
        return redirect(url_for("auth.login"))
    except Exception as e:
        current_app.logger.error(f"Email confirmation error: {e}")
        flash(_("An error occurred. Please try again."), "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/resend-confirmation", methods=["GET", "POST"])
def resend_confirmation() -> ResponseReturnValue:
    """Resend confirmation email."""
    form = ResendConfirmationForm()

    if form.validate_on_submit():
        try:
            assert form.email.data is not None
            uow = bootstrap.bootstrap()
            email_adapter = get_email_adapter()
            template_renderer = get_template_renderer(current_app)
            url_generator = get_url_generator(current_app)

            # Service layer handles token creation and email sending
            resend_confirmation_email(uow, form.email.data, email_adapter, template_renderer, url_generator)

            # Always show success (anti-enumeration)
            flash(
                _("If that email is registered and unconfirmed, a confirmation link has been sent."),
                "info",
            )
            return redirect(url_for("auth.login"))

        except RateLimitExceeded as e:
            flash(str(e), "error")
        except Exception as e:
            current_app.logger.error(f"Resend confirmation error: {e}")
            flash(_("An error occurred. Please try again."), "error")

    return render_template("auth/resend_confirmation.html", form=form)


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
                            template_renderer = get_template_renderer(current_app)
                            url_generator = get_url_generator(current_app)
                            send_password_reset_email(
                                email_adapter=email_adapter,
                                template_renderer=template_renderer,
                                url_generator=url_generator,
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
    safe_next_page = get_safe_next_page(request.args.get("next"))
    if safe_next_page:
        session["oauth_next"] = safe_next_page

    # Redirect to Google OAuth - it has to be https, so do that
    redirect_uri = url_for("auth.google_callback", _external=True, _scheme="https")
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
        return redirect(get_safe_next_page(next_page, default=url_for("main.dashboard")))

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


@auth_bp.route("/login/microsoft")
def login_microsoft() -> ResponseReturnValue:
    """Initiate Microsoft OAuth login flow."""
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    # Store redirect URL in session for post-OAuth redirect
    safe_next_page = get_safe_next_page(request.args.get("next"))
    if safe_next_page:
        session["oauth_next"] = safe_next_page

    # Redirect to Microsoft OAuth - it has to be https, so do that
    redirect_uri = url_for("auth.microsoft_callback", _external=True, _scheme="https")
    response = oauth.microsoft.authorize_redirect(redirect_uri)
    assert isinstance(response, Response)
    return response


@auth_bp.route("/login/microsoft/callback")
def microsoft_callback() -> ResponseReturnValue:
    """Handle Microsoft OAuth callback."""
    try:
        # Get OAuth token
        # Skip issuer validation for Microsoft /common endpoint since it returns tenant-specific issuer
        token = oauth.microsoft.authorize_access_token(claims_options={"iss": {"essential": False}})

        # Get user info from Microsoft
        user_info = token.get("userinfo")
        if not user_info:
            user_info = oauth.microsoft.userinfo()

        microsoft_id = user_info.get("sub")
        email = user_info.get("email")
        first_name = user_info.get("given_name", "")
        last_name = user_info.get("family_name", "")

        if not microsoft_id or not email:
            flash(_("Failed to get user information from Microsoft"), "error")
            return redirect(url_for("auth.login"))

        uow = bootstrap.bootstrap()

        # Try to find or create OAuth user
        user, created = find_or_create_oauth_user(
            uow=uow,
            provider="microsoft",
            oauth_id=microsoft_id,
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
        return redirect(get_safe_next_page(next_page, default=url_for("main.dashboard")))

    except InvalidInvite as e:
        # User needs invite code - redirect to OAuth registration
        flash(str(e), "error")
        return redirect(url_for("auth.register_microsoft"))
    except Exception as e:
        current_app.logger.error(f"Microsoft OAuth callback error: {e}")
        flash(_("An error occurred during Microsoft sign in. Please try again."), "error")
        return redirect(url_for("auth.login"))


@auth_bp.route("/register/microsoft", methods=["GET", "POST"])
def register_microsoft() -> ResponseReturnValue:
    """Register with Microsoft OAuth (requires invite code)."""
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

        # Redirect to Microsoft OAuth
        return redirect(url_for("auth.login_microsoft"))

    return render_template("auth/register_microsoft.html", form=form)
