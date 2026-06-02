"""ABOUTME: Public registration page routes for assembly registration forms
ABOUTME: Handles form rendering, submission, and URL resolution without login"""

from collections.abc import Callable
from functools import wraps
from typing import Any

from flask import Blueprint, abort, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_wtf.csrf import generate_csrf

from opendlp import bootstrap
from opendlp.domain.registration_page import RenderContext
from opendlp.feature_flags import has_feature
from opendlp.service_layer.registration_page_service import (
    RegistrationPageVisibilityState,
    find_registration_page_by_short_url_slug,
    find_registration_page_by_url_slug,
    get_page_and_source_for_render,
    render_thank_you_html,
    resolve_visibility,
)
from opendlp.service_layer.registration_submission_service import (
    RegistrationClosedError,
    RegistrationNotFoundError,
    submit_registration,
)

registration_bp = Blueprint("registration", __name__)


def require_registration_feature(f: Callable[..., ResponseReturnValue]) -> Callable[..., ResponseReturnValue]:
    """Return 404 unless FF_REGISTRATION_PAGE is enabled."""

    @wraps(f)
    def decorated(*args: Any, **kwargs: Any) -> ResponseReturnValue:
        if not has_feature("registration_page"):
            abort(404)
        return f(*args, **kwargs)

    return decorated


@registration_bp.route("/register/<url_slug>", methods=["GET"])
@require_registration_feature
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
    source = get_page_and_source_for_render(uow, page)
    assembly = uow.assemblies.get(page.assembly_id)

    ctx = RenderContext(
        csrf_form_element=f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">',
        form_action=url_for("registration.submit_registration_form", url_slug=url_slug),
        assembly_title=assembly.title if assembly else "",
        assembly_question=assembly.question if assembly else "",
    )

    rendered_form = source.render(ctx)

    return render_template(
        "register/form.html",
        rendered_form=rendered_form,
        is_test=visibility.is_test,
    )


@registration_bp.route("/register/<url_slug>", methods=["POST"])
@require_registration_feature
def submit_registration_form(url_slug: str) -> ResponseReturnValue:
    """Handle form submission for the registration page."""
    uow = bootstrap.bootstrap()

    try:
        result = submit_registration(uow, url_slug=url_slug, form_data=request.form)
    except RegistrationNotFoundError:
        abort(404)
    except RegistrationClosedError:
        return redirect(url_for("registration.registration_closed"), 302)

    if result.is_valid:
        return redirect(url_for("registration.thank_you", url_slug=url_slug), 302)

    # Validation failed - re-render form with errors
    page = find_registration_page_by_url_slug(uow, url_slug)
    if page is None:
        abort(404)

    source = get_page_and_source_for_render(uow, page)
    visibility = resolve_visibility(page)
    assembly = uow.assemblies.get(page.assembly_id)

    ctx = RenderContext(
        csrf_form_element=f'<input type="hidden" name="csrf_token" value="{generate_csrf()}">',
        form_action=url_for("registration.submit_registration_form", url_slug=url_slug),
        assembly_title=assembly.title if assembly else "",
        assembly_question=assembly.question if assembly else "",
        values=result.values,
        errors=result.field_errors,
        form_level_errors=result.form_errors,
    )

    rendered_form = source.render(ctx)

    return render_template(
        "register/form.html",
        rendered_form=rendered_form,
        is_test=visibility.is_test,
    )


@registration_bp.route("/register/<url_slug>/thank-you", methods=["GET"])
@require_registration_feature
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
@require_registration_feature
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
@require_registration_feature
def registration_closed() -> ResponseReturnValue:
    """Display the static registration closed page."""
    return render_template("register/closed.html")
