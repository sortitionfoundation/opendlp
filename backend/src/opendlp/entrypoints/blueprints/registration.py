"""ABOUTME: Public registration page routes for assembly registration forms
ABOUTME: Handles form rendering, submission, and URL resolution without login"""

from flask import Blueprint, Response, abort, current_app, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_wtf.csrf import generate_csrf, validate_csrf
from wtforms import ValidationError

from opendlp import bootstrap
from opendlp.domain.registration_image import IMAGE_CONTENT_TYPE
from opendlp.entrypoints.decorators import require_feature
from opendlp.entrypoints.extensions import csrf
from opendlp.service_layer.email_send_service import send_registration_auto_reply
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
    uow = bootstrap.bootstrap()

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
        csrf_form_element=f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">',
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
        csrf_form_element=f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">',
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
    validate_csrf call below.
    """
    uow = bootstrap.bootstrap()

    # Gate on WTF_CSRF_ENABLED exactly as the global CSRFProtect hook does, so
    # disabling CSRF (e.g. in tests) skips validation here too.
    if current_app.config.get("WTF_CSRF_ENABLED", True):
        try:
            validate_csrf(request.form.get("csrf_token"))
        except ValidationError:
            return _rerender_form_with_values(
                uow,
                url_slug,
                values=dict(request.form),
                form_errors=[
                    _(
                        "Your form had been open too long and couldn't be submitted securely. "
                        "Please check your answers and submit again."
                    )
                ],
            )

    try:
        result = submit_registration(uow, url_slug=url_slug, form_data=request.form)
    except RegistrationNotFoundError:
        abort(404)
    except RegistrationClosedError:
        return redirect(url_for("registration.registration_closed"), 302)

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
            bootstrap.bootstrap(),
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
    uow = bootstrap.bootstrap()

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
    uow = bootstrap.bootstrap()

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
    uow = bootstrap.bootstrap()

    page = find_registration_page_by_short_url_slug(uow, short_url_slug)
    if page is None or not page.url_slug:
        abort(404)

    return redirect(url_for("registration.show_registration_form", url_slug=page.url_slug), 302)


@registration_bp.route("/registration-closed", methods=["GET"])
@require_feature("registration_page")
def registration_closed() -> ResponseReturnValue:
    """Display the static registration closed page."""
    return render_template("register/closed.html")
