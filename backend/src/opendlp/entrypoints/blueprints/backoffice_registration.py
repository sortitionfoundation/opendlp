"""ABOUTME: Backoffice registration-page editor routes
ABOUTME: View / save / create / skeleton / QR-download routes for the assembly registration tab"""

import uuid
from typing import cast

from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from opendlp import bootstrap
from opendlp.domain.registration_page import (
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageStatus,
)
from opendlp.entrypoints.blueprints.registration import registration_url, short_url
from opendlp.entrypoints.scroll_utils import redirect_preserving_scroll
from opendlp.service_layer.assembly_service import get_assembly_nav_context
from opendlp.service_layer.exceptions import (
    InsufficientPermissions,
    NotFoundError,
    RegistrationPageNotFoundError,
)
from opendlp.service_layer.qr_codes import generate_qr_code_base64, generate_qr_code_png
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    generate_starter_form_html,
    get_registration_page_with_source,
    publish_registration_page,
    reopen_registration_page,
    unpublish_registration_page,
    update_registration_page_html,
)
from opendlp.translations import gettext as _

backoffice_registration_bp = Blueprint("backoffice_registration", __name__)


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration")
@login_required
def view_assembly_registration(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice registration form configuration page."""
    try:
        nav = get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            request.args.get("source", ""),
        )

        # Get registration page and HTML source from service layer
        uow = bootstrap.bootstrap()
        result = get_registration_page_with_source(uow, current_user.id, assembly_id)

        # HTML content
        has_registration_page = result is not None
        registration_page = result[0] if result else None
        if result:
            html = cast(RegistrationPageHtml, result[1])
            html_content = html.form_html
            thank_you_html = result[0].thank_you_html
            registration_status = result[0].status.value  # "TEST", "PUBLISHED", or "CLOSED"
        else:
            html_content = ""
            thank_you_html = ""
            registration_status = "TEST"  # Default for new pages

        # Build registration URLs and a QR code for the short URL, when configured
        registration_page_url = None
        registration_short_url = None
        qr_code_data_url = None
        if registration_page:
            registration_page_url = registration_url(registration_page.url_slug)
            if registration_page.short_url_slug:
                registration_short_url = short_url(registration_page.short_url_slug)
                qr_code_data_url = generate_qr_code_base64(registration_short_url)

        return render_template(
            "backoffice/assembly_registration.html",
            assembly=nav.assembly,
            data_source=nav.data_source,
            gsheet=nav.gsheet,
            targets_enabled=nav.targets_enabled,
            respondents_enabled=nav.respondents_enabled,
            selection_enabled=nav.selection_enabled,
            registration_page=registration_page,
            registration_url=registration_page_url,
            short_url=registration_short_url,
            qr_code_data_url=qr_code_data_url,
            registration_status=registration_status,
            html_content=html_content,
            thank_you_html=thank_you_html,
            has_registration_page=has_registration_page,
        ), 200
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(
            f"View assembly registration error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        flash(_("An error occurred while loading registration settings"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _handle_registration_action(action: str, user_id: uuid.UUID, assembly_id: uuid.UUID) -> str:
    """Handle publish/unpublish/close/reopen/save action for registration page. Returns flash message."""
    if action == "publish":
        uow = bootstrap.bootstrap()
        result = get_registration_page_with_source(uow, user_id, assembly_id)
        if result and result[0].status == RegistrationPageStatus.TEST:
            uow = bootstrap.bootstrap()
            publish_registration_page(uow, user_id, assembly_id)
            return _("Registration form published successfully")
        return _("Registration form HTML updated successfully")
    if action == "unpublish":
        uow = bootstrap.bootstrap()
        unpublish_registration_page(uow, user_id, assembly_id)
        return _("Registration form unpublished")
    if action == "close":
        uow = bootstrap.bootstrap()
        close_registration_page(uow, user_id, assembly_id)
        return _("Registration form closed")
    if action == "reopen":
        uow = bootstrap.bootstrap()
        reopen_registration_page(uow, user_id, assembly_id)
        return _("Registration form reopened")
    uow = bootstrap.bootstrap()
    result = get_registration_page_with_source(uow, user_id, assembly_id)
    if result and result[0].status == RegistrationPageStatus.PUBLISHED:
        return _("Registration form saved and republished")
    return _("Registration form saved")


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/save", methods=["POST"])
@login_required
def save_assembly_registration(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save and publish registration form HTML content."""
    try:
        # Verify user has permission to access this assembly (side effect: raises if unauthorized)
        get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            "",
        )

        html_content = request.form.get("html_content", "")
        action = request.form.get("action", "save")

        # Update HTML content (will raise RegistrationPageNotFoundError if page doesn't exist)
        uow = bootstrap.bootstrap()
        update_registration_page_html(uow, current_user.id, assembly_id, html_content)

        flash_message = _handle_registration_action(action, current_user.id, assembly_id)
        flash(flash_message, "success")
        return redirect_preserving_scroll(
            url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id)
        )
    except RegistrationPageNotReady as e:
        # Show specific validation errors for publishing
        error_message = "; ".join(e.problems)
        current_app.logger.warning(f"Registration page not ready for assembly {assembly_id}: {error_message}")
        flash(error_message, "error")
        return redirect_preserving_scroll(
            url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id)
        )
    except RegistrationPageNotFoundError:
        # Registration page doesn't exist yet - redirect to Details tab to create it
        flash(_("Please create a registration page first from the Details tab."), "warning")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to modify this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except ValueError as e:
        current_app.logger.warning(f"Validation error for assembly {assembly_id}: {e}")
        flash(str(e), "error")
        return redirect_preserving_scroll(
            url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id)
        )
    except Exception as e:
        current_app.logger.error(
            f"Save assembly registration error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        current_app.logger.exception("Full traceback:")
        flash(_("An error occurred while saving registration settings"), "error")
        return redirect_preserving_scroll(
            url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id)
        )


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/create", methods=["POST"])
@login_required
def create_assembly_registration_page(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Create a registration page with auto-generated slugs from the assembly name."""
    try:
        uow = bootstrap.bootstrap()
        create_registration_page_with_slugs(uow, current_user.id, assembly_id)
        flash(
            _("Registration page created. URLs have been generated automatically and can be edited below."),
            "success",
        )
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to modify this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except ValueError as e:
        # Already has a registration page
        current_app.logger.warning(f"Cannot create registration page for assembly {assembly_id}: {e}")
        flash(_("This assembly already has a registration page."), "warning")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except Exception as e:
        current_app.logger.error(f"Error creating registration page for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full traceback:")
        flash(_("An error occurred while creating the registration page"), "error")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/skeleton")
@login_required
def get_registration_skeleton(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Generate starter HTML form skeleton based on assembly's field definitions."""
    try:
        uow = bootstrap.bootstrap()
        html = generate_starter_form_html(uow, current_user.id, assembly_id)
        return jsonify({"html": html})
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to access this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        current_app.logger.error(f"Generate skeleton error for assembly {assembly_id}: {e}")
        return jsonify({"error": _("An error occurred while generating the form skeleton")}), 500


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/qr-code.png")
@login_required
def download_registration_qr_code(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Download registration QR code as PNG image."""
    try:
        # Verify user has permission to access this assembly
        get_assembly_nav_context(
            bootstrap.bootstrap,
            current_user.id,
            assembly_id,
            "",
        )

        # The QR code encodes the short URL, so a short slug must be configured
        uow = bootstrap.bootstrap()
        result = get_registration_page_with_source(uow, current_user.id, assembly_id)
        registration_page = result[0] if result else None
        if not registration_page or not registration_page.short_url_slug:
            abort(404)

        qr_png = generate_qr_code_png(short_url(registration_page.short_url_slug))

        return Response(
            qr_png,
            mimetype="image/png",
            headers={
                "Content-Disposition": f'attachment; filename="registration-qr-{str(assembly_id)[:8]}.png"',
                "Cache-Control": "no-cache",
            },
        )
    except HTTPException:
        # abort(404) for a missing short URL should surface as a real 404, not a redirect
        raise
    except InsufficientPermissions as e:
        current_app.logger.warning(f"Insufficient permissions for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("You don't have permission to access this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        current_app.logger.warning(f"Assembly {assembly_id} not found for user {current_user.id}: {e}")
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        current_app.logger.error(f"Download QR code error for assembly {assembly_id} user {current_user.id}: {e}")
        flash(_("An error occurred while generating QR code"), "error")
        return redirect(url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id))
