"""ABOUTME: Public registration page routes for assembly registration forms
ABOUTME: Handles form rendering, submission, and URL resolution without login"""

import logging
from datetime import UTC, datetime

from flask import Blueprint, Response, abort, current_app, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_wtf.csrf import generate_csrf, validate_csrf
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from wtforms import ValidationError

from opendlp import bootstrap
from opendlp.domain.registration_image import IMAGE_CONTENT_TYPE
from opendlp.entrypoints.decorators import require_feature
from opendlp.entrypoints.extensions import csrf
from opendlp.service_layer.email_send_service import send_registration_auto_reply
from opendlp.service_layer.exceptions import RateLimitExceeded
from opendlp.service_layer.registration_bot_protection_service import (
    check_registration_rate_limit,
    record_registration_submission,
)
from opendlp.service_layer.registration_image_service import get_registration_image_for_serving
from opendlp.service_layer.registration_page_service import (
    RegistrationPageVisibilityState,
    find_registration_page_by_short_url_slug,
    find_registration_page_by_url_slug,
    render_registration_form,
    render_thank_you_html,
    resolve_visibility,
)
from opendlp.service_layer.registration_submission_service import (
    RegistrationClosedError,
    RegistrationNotFoundError,
    submit_registration,
)
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork
from opendlp.translations import gettext as _

logger = logging.getLogger(__name__)

_TIMING_TOKEN_SALT = "reg-timing"  # noqa: S105 - this is a signer salt, not a password
_TIMING_TOKEN_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days, matches session lifetime


def _generate_timing_token(secret_key: str) -> str:
    signer = TimestampSigner(secret_key, salt=_TIMING_TOKEN_SALT)
    return signer.sign("t").decode()


def _validate_timing_token(token: str, secret_key: str, min_fill_seconds: int, max_age_seconds: int) -> None:
    signer = TimestampSigner(secret_key, salt=_TIMING_TOKEN_SALT)
    _unsigned, timestamp = signer.unsign(token, max_age=max_age_seconds, return_timestamp=True)
    age_seconds = (datetime.now(UTC) - timestamp.replace(tzinfo=UTC)).total_seconds()
    if age_seconds < min_fill_seconds:
        raise ValueError("too fast")


def _secret_key() -> str:
    """Return the application secret key as a plain string."""
    key = current_app.secret_key
    if isinstance(key, bytes):
        return key.decode()
    return key or ""


def _build_security_form_elements() -> str:
    """Build the hidden security elements injected into every registration form."""
    csrf_input = f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">'
    timing_input = f'<input type="hidden" name="_timing_token" value="{_generate_timing_token(_secret_key())}">'
    # _opendlp_ttoken_ is a honeypot field — see docs/bot-protection.md
    honeypot = (
        '<div aria-hidden="true" style="position:absolute;left:-9999px;'
        'width:1px;height:1px;overflow:hidden">'
        '<label for="_opendlp_ttoken_">Leave this blank</label>'
        '<input type="text" id="_opendlp_ttoken_" name="_opendlp_ttoken_" '
        'tabindex="-1" autocomplete="off" value="">'
        "</div>"
    )
    return csrf_input + timing_input + honeypot


registration_bp = Blueprint("registration", __name__)


def registration_url(url_slug: str) -> str:
    """External URL of the public registration form for a slug."""
    return url_for("registration.show_registration_form", url_slug=url_slug, _external=True)


def short_url(short_url_slug: str) -> str:
    """External short URL that redirects to the registration form."""
    return url_for("registration.short_url_redirect", short_url_slug=short_url_slug, _external=True)


def registration_url_prefix() -> str:
    """External URL up to but not including the slug, for prefixed inputs."""
    return registration_url("")


def short_url_prefix() -> str:
    """External short URL up to but not including the slug, for prefixed inputs."""
    return short_url("")


@registration_bp.route("/register/<url_slug>", methods=["GET"])
@require_feature("registration_page")
def show_registration_form(url_slug: str) -> ResponseReturnValue:
    """Render the public registration form for the given URL slug."""
    uow = bootstrap.get_flask_uow()

    page = find_registration_page_by_url_slug(uow, url_slug)
    visibility = resolve_visibility(page)

    if visibility.state == RegistrationPageVisibilityState.NOT_FOUND:
        abort(404)

    if visibility.state == RegistrationPageVisibilityState.CLOSED:
        return redirect(url_for("registration.registration_closed"), 302)

    # LIVE or TEST - render the form
    assert page is not None  # Guaranteed by visibility state
    rendered_form = render_registration_form(
        uow,
        page,
        csrf_form_element=_build_security_form_elements(),
        form_action=url_for("registration.submit_registration_form", url_slug=url_slug),
    )

    return render_template(
        "register/form.html",
        rendered_form=rendered_form,
        is_test=visibility.is_test,
    )


def _rerender_form_with_values(
    uow: AbstractUnitOfWork,
    url_slug: str,
    *,
    values: dict[str, str],
    field_errors: dict[str, list[str]] | None = None,
    form_errors: list[str] | None = None,
) -> ResponseReturnValue:
    """Re-render the registration form with the submitted values and any errors.

    Shared by the validation-failure and expired-CSRF-token paths so a user
    never loses what they typed. A fresh CSRF token is issued each time.
    """
    page = find_registration_page_by_url_slug(uow, url_slug)
    if page is None:
        abort(404)

    visibility = resolve_visibility(page)

    rendered_form = render_registration_form(
        uow,
        page,
        csrf_form_element=_build_security_form_elements(),
        form_action=url_for("registration.submit_registration_form", url_slug=url_slug),
        values=values,
        errors=field_errors,
        form_level_errors=form_errors,
    )

    return render_template(
        "register/form.html",
        rendered_form=rendered_form,
        is_test=visibility.is_test,
    )


_FORM_EXPIRED_ERROR = (
    "Your form had been open too long and couldn't be submitted securely. Please check your answers and submit again."
)


def _check_form_tokens(uow: AbstractUnitOfWork, url_slug: str) -> ResponseReturnValue | None:
    """Validate CSRF and timing tokens from the submitted form.

    Returns None when both tokens are acceptable. Returns a response (redirect
    or re-rendered form) when a problem is detected. Skipped entirely when
    WTF_CSRF_ENABLED is False (e.g. in tests).
    """
    if not current_app.config.get("WTF_CSRF_ENABLED", True):
        return None

    try:
        validate_csrf(request.form.get("csrf_token"))
    except ValidationError:
        return _rerender_form_with_values(
            uow,
            url_slug,
            values=dict(request.form),
            form_errors=[_(_FORM_EXPIRED_ERROR)],
        )

    timing_token = request.form.get("_timing_token", "")
    try:
        _validate_timing_token(
            timing_token,
            _secret_key(),
            min_fill_seconds=current_app.config["REGISTRATION_MIN_FILL_SECONDS"],
            max_age_seconds=_TIMING_TOKEN_MAX_AGE_SECONDS,
        )
    except ValueError:
        logger.warning(
            "Bot protection: timing check failed (IP: %s, slug: %s)",
            request.remote_addr,
            url_slug,
        )
        return redirect(url_for("registration.thank_you", url_slug=url_slug), 302)
    except (SignatureExpired, BadSignature):
        return _rerender_form_with_values(
            uow,
            url_slug,
            values=dict(request.form),
            form_errors=[_(_FORM_EXPIRED_ERROR)],
        )

    return None


@registration_bp.route("/register/<url_slug>", methods=["POST"])
@csrf.exempt
@require_feature("registration_page")
def submit_registration_form(url_slug: str) -> ResponseReturnValue:
    """Handle form submission for the registration page.

    CSRF is validated explicitly here rather than via the global CSRFProtect
    before-request hook. This lets an expired token re-render the form with the
    submitted values preserved (members of the public may take a long time over
    a form) instead of discarding their answers to a generic error page. The
    route is exempt from automatic protection but is NOT unprotected - see the
    _check_form_tokens call below.
    """
    uow = bootstrap.get_flask_uow()

    if request.form.get("_opendlp_ttoken_"):
        logger.warning(
            "Bot protection: honeypot triggered (IP: %s, slug: %s)",
            request.remote_addr,
            url_slug,
        )
        return redirect(url_for("registration.thank_you", url_slug=url_slug), 302)

    token_error = _check_form_tokens(uow, url_slug)
    if token_error is not None:
        return token_error

    ip_address = request.remote_addr or ""
    email = request.form.get("email", "").strip().lower()

    try:
        check_registration_rate_limit(
            ip_address,
            email,
            max_per_ip=current_app.config["REGISTRATION_RATE_LIMIT_PER_IP"],
            max_per_email=current_app.config["REGISTRATION_RATE_LIMIT_PER_EMAIL"],
            ip_window_minutes=current_app.config["REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES"],
            email_window_minutes=current_app.config["REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES"],
        )
    except RateLimitExceeded:
        return _rerender_form_with_values(
            uow,
            url_slug,
            values=dict(request.form),
            form_errors=[_("Too many registrations from your location. Please try again later.")],
        )

    try:
        result = submit_registration(uow, url_slug=url_slug, form_data=request.form)
    except RegistrationNotFoundError:
        abort(404)
    except RegistrationClosedError:
        return redirect(url_for("registration.registration_closed"), 302)

    record_registration_submission(
        ip_address,
        email,
        ip_window_minutes=current_app.config["REGISTRATION_RATE_LIMIT_IP_WINDOW_MINUTES"],
        email_window_minutes=current_app.config["REGISTRATION_RATE_LIMIT_EMAIL_WINDOW_MINUTES"],
    )

    if result.is_valid:
        _send_registration_auto_reply(result.respondent)
        return redirect(url_for("registration.thank_you", url_slug=url_slug), 302)

    # Validation failed - re-render form with errors
    return _rerender_form_with_values(
        uow,
        url_slug,
        values=result.values,
        field_errors=result.field_errors,
        form_errors=result.form_errors,
    )


def _send_registration_auto_reply(respondent) -> None:  # type: ignore[no-untyped-def]
    """Best-effort auto-reply send. Never blocks the redirect to the thank-you page."""
    try:
        send_registration_auto_reply(
            bootstrap.get_flask_uow(),
            bootstrap.get_email_adapter(),
            respondent=respondent,
            assembly_id=respondent.assembly_id,
        )
    except Exception:
        current_app.logger.exception("Failed to send registration auto-reply")


@registration_bp.route("/register/<url_slug>/assets/<image_name>", methods=["GET"])
@require_feature("registration_page")
def serve_registration_image(url_slug: str, image_name: str) -> ResponseReturnValue:
    """Serve a registration page image from the database (public, image-only)."""
    uow = bootstrap.get_flask_uow()

    served = get_registration_image_for_serving(uow, url_slug, image_name)
    if served is None:
        abort(404)

    response = Response(served.data, mimetype=IMAGE_CONTENT_TYPE)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.set_etag(served.sha256)
    return response.make_conditional(request)


@registration_bp.route("/register/<url_slug>/thank-you", methods=["GET"])
@require_feature("registration_page")
def thank_you(url_slug: str) -> ResponseReturnValue:
    """Display the thank-you page after successful registration submission."""
    uow = bootstrap.get_flask_uow()

    page = find_registration_page_by_url_slug(uow, url_slug)
    if page is None:
        abort(404)

    custom_html = render_thank_you_html(page)

    if custom_html.strip():
        return render_template(
            "register/thank_you.html",
            custom_html=custom_html,
        )

    return render_template("register/thank_you_default.html")


@registration_bp.route("/r/<short_url_slug>", methods=["GET"])
@require_feature("registration_page")
def short_url_redirect(short_url_slug: str) -> ResponseReturnValue:
    """Redirect from short URL to canonical registration URL.

    Uses 302 (not 301) because short slugs may be reused.
    """
    uow = bootstrap.get_flask_uow()

    page = find_registration_page_by_short_url_slug(uow, short_url_slug)
    if page is None or not page.url_slug:
        abort(404)

    return redirect(url_for("registration.show_registration_form", url_slug=page.url_slug), 302)


@registration_bp.route("/registration-closed", methods=["GET"])
@require_feature("registration_page")
def registration_closed() -> ResponseReturnValue:
    """Display the static registration closed page."""
    return render_template("register/closed.html")


@registration_bp.after_request
def add_noindex_header(response: Response) -> Response:
    """Prevent search engines from indexing registration pages."""
    response.headers["X-Robots-Tag"] = "noindex"
    return response
