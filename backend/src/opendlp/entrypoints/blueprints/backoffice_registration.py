"""ABOUTME: Backoffice registration-page editor routes
ABOUTME: View / save / create / skeleton / QR-download / image upload routes for the assembly registration tab"""

import json
import uuid
from typing import Any, cast

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from opendlp import bootstrap
from opendlp.config import get_max_image_upload_mb
from opendlp.domain.registration_image import (
    ALLOWED_INPUT_FORMATS,
    IMAGE_FILE_EXTENSION,
    ImageValidationError,
    RegistrationImage,
    generate_image_html,
)
from opendlp.domain.registration_page import (
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageStatus,
)
from opendlp.entrypoints.blueprints.registration import registration_url, short_url
from opendlp.entrypoints.scroll_utils import redirect_preserving_scroll
from opendlp.service_layer.assembly_service import get_assembly_nav_context
from opendlp.service_layer.exceptions import (
    ImageQuotaExceeded,
    InsufficientPermissions,
    NotFoundError,
    RegistrationImageNotFoundError,
    RegistrationPageNotFoundError,
)
from opendlp.service_layer.qr_codes import generate_qr_code_base64, generate_qr_code_png
from opendlp.service_layer.registration_image_service import (
    add_registration_image,
    delete_registration_image,
    list_registration_images,
    set_registration_image_alt,
)
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


def _is_htmx() -> bool:
    return request.headers.get("HX-Request") == "true"


def _image_to_dict(image: RegistrationImage, url_slug: str) -> dict[str, Any]:
    """Serialise an image for the Assets panel.

    ``public_url`` is the public ``/register/<slug>/assets/<sha>.png`` route. If the
    page has no slug yet (newly created), we return a placeholder so the front-end
    can still render the row.
    """
    file_name = f"{image.sha256}.{IMAGE_FILE_EXTENSION}"
    public_url = (
        url_for("registration.serve_registration_image", url_slug=url_slug, image_name=file_name) if url_slug else ""
    )
    if image.alt and image.alt.strip():
        display_name = image.alt.strip()
    elif image.original_filename:
        display_name = image.original_filename
    else:
        display_name = f"{image.sha256[:8]}.{IMAGE_FILE_EXTENSION}"
    return {
        "id": str(image.id),
        "alt": image.alt,
        "original_filename": image.original_filename,
        "file_name": file_name,
        "display_name": display_name,
        "public_url": public_url,
        "img_snippet": generate_image_html(public_url, alt=image.alt) if public_url else "",
        "width": image.width,
        "height": image.height,
        "byte_size": image.byte_size,
    }


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration")
@login_required
def view_assembly_registration(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice registration form configuration page."""
    return _render_registration_page(assembly_id, open_modal=request.args.get("modal", ""))


def _render_registration_page(
    assembly_id: uuid.UUID, open_modal: str = "", open_image_id: uuid.UUID | None = None
) -> ResponseReturnValue:
    """Render the registration configuration page.

    ``open_modal`` names a modal to render already-open server-side ("upload" or
    "details"), which is the no-JS fallback for the HTMX-loaded modals — the page
    degrades to a full reload that shows the requested modal. For "details",
    ``open_image_id`` selects which image's modal to open.
    """
    try:
        nav = get_assembly_nav_context(
            bootstrap.get_flask_uow,
            current_user.id,
            assembly_id,
            request.args.get("source", ""),
        )

        # Get registration page and HTML source from service layer
        uow = bootstrap.get_flask_uow()
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

        # Load registration images for the Assets panel
        images: list[dict[str, Any]] = []
        if has_registration_page and registration_page:
            # Reuse the UnitOfWork from the page lookup above.
            stored_images = list_registration_images(uow, current_user.id, assembly_id)
            images = [_image_to_dict(image, registration_page.url_slug) for image in stored_images]

        # When falling back to a full page with the details modal open, pick out the
        # image whose modal should be shown from the list we just built.
        open_image = None
        if open_modal == "details" and open_image_id is not None:
            open_image = next((img for img in images if img["id"] == str(open_image_id)), None)

        # The HTML editor is read-only by default; ?edit=1 unlocks it. CLOSED pages
        # have no save path so we always keep them read-only regardless of the param.
        edit_mode = request.args.get("edit") == "1" and registration_status != "CLOSED"

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
            images=images,
            max_image_upload_mb=get_max_image_upload_mb(),
            allowed_image_formats=sorted(ALLOWED_INPUT_FORMATS),
            edit_mode=edit_mode,
            open_modal=open_modal,
            open_image=open_image,
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
    uow = bootstrap.get_flask_uow()
    if action == "publish":
        result = get_registration_page_with_source(uow, user_id, assembly_id)
        if result and result[0].status == RegistrationPageStatus.TEST:
            publish_registration_page(uow, user_id, assembly_id)
            return _("Registration form published successfully")
        return _("Registration form HTML updated successfully")
    if action == "unpublish":
        unpublish_registration_page(uow, user_id, assembly_id)
        return _("Registration form unpublished")
    if action == "close":
        close_registration_page(uow, user_id, assembly_id)
        return _("Registration form closed")
    if action == "reopen":
        reopen_registration_page(uow, user_id, assembly_id)
        return _("Registration form reopened")
    result = get_registration_page_with_source(uow, user_id, assembly_id)
    if result and result[0].status == RegistrationPageStatus.PUBLISHED:
        return _("Registration form saved and republished")
    return _("Registration form saved")


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/save", methods=["POST"])
@login_required
def save_assembly_registration(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save and publish registration form HTML content."""
    action = request.form.get("action", "save")
    # If the user was editing (action="save") and the request fails, keep them in
    # edit mode so they can fix and retry. Status transitions only fire from
    # read-only mode (the dropdown is disabled while editing), so they land back
    # in read-only on error.
    view_kwargs: dict[str, Any] = {"assembly_id": assembly_id}
    if action == "save":
        view_kwargs["edit"] = "1"
    error_redirect_url = url_for("backoffice_registration.view_assembly_registration", **view_kwargs)
    try:
        # Verify user has permission to access this assembly (side effect: raises if unauthorized)
        get_assembly_nav_context(
            bootstrap.get_flask_uow,
            current_user.id,
            assembly_id,
            "",
        )

        html_content = request.form.get("html_content", "")

        # Update HTML content (will raise RegistrationPageNotFoundError if page doesn't exist)
        uow = bootstrap.get_flask_uow()
        update_registration_page_html(uow, current_user.id, assembly_id, html_content)

        flash_message = _handle_registration_action(action, current_user.id, assembly_id)
        flash(flash_message, "success")
        # Success drops ?edit=1 — the user lands back in read-only.
        return redirect_preserving_scroll(
            url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id)
        )
    except RegistrationPageNotReady as e:
        # Show specific validation errors for publishing
        error_message = "; ".join(e.problems)
        current_app.logger.warning(f"Registration page not ready for assembly {assembly_id}: {error_message}")
        flash(error_message, "error")
        return redirect_preserving_scroll(error_redirect_url)
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
        return redirect_preserving_scroll(error_redirect_url)
    except Exception as e:
        current_app.logger.error(
            f"Save assembly registration error for assembly {assembly_id} user {current_user.id}: {e}"
        )
        current_app.logger.exception("Full traceback:")
        flash(_("An error occurred while saving registration settings"), "error")
        return redirect_preserving_scroll(error_redirect_url)


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/create", methods=["POST"])
@login_required
def create_assembly_registration_page(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Create a registration page with auto-generated slugs from the assembly name."""
    try:
        uow = bootstrap.get_flask_uow()
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
        uow = bootstrap.get_flask_uow()
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
            bootstrap.get_flask_uow,
            current_user.id,
            assembly_id,
            "",
        )

        # The QR code encodes the short URL, so a short slug must be configured
        uow = bootstrap.get_flask_uow()
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


def _resolve_page_url_slug(assembly_id: uuid.UUID) -> str:
    """Look up the registration page's url_slug for serialising image URLs.

    Returns an empty string when the page doesn't exist yet — the caller can
    decide whether to omit the public URL.
    """
    uow = bootstrap.get_flask_uow()
    result = get_registration_page_with_source(uow, current_user.id, assembly_id)
    if result is None:
        return ""
    return result[0].url_slug


def _list_images_as_dicts(assembly_id: uuid.UUID) -> list[dict[str, Any]]:
    """Serialise all of an assembly's registration images for the Assets panel."""
    uow = bootstrap.get_flask_uow()
    images = list_registration_images(uow, current_user.id, assembly_id)
    url_slug = _resolve_page_url_slug(assembly_id)
    return [_image_to_dict(image, url_slug) for image in images]


def _find_image_dict(assembly_id: uuid.UUID, image_id: uuid.UUID) -> dict[str, Any] | None:
    """Return the serialised image with ``image_id`` for this assembly, or None."""
    return next((img for img in _list_images_as_dicts(assembly_id) if img["id"] == str(image_id)), None)


def _image_list_response(
    assembly_id: uuid.UUID, *, toast: str = "", toast_type: str = "success"
) -> ResponseReturnValue:
    """Render the Assets list as an out-of-band fragment after a mutation.

    Swapping ``#image-asset-list`` out of band refreshes the panel; because the
    rest of the response body is empty it also clears ``#image-modal-container``,
    closing whichever modal triggered the mutation. An optional toast is fired via
    ``HX-Trigger`` for the page to surface.
    """
    html = render_template(
        "backoffice/registration/image_asset_list.html",
        assembly_id=assembly_id,
        images=_list_images_as_dicts(assembly_id),
        oob=True,
    )
    response = make_response(html)
    if toast:
        response.headers["HX-Trigger"] = json.dumps({"show-toast": {"message": toast, "type": toast_type}})
    return response


def _render_image_details_modal(
    assembly_id: uuid.UUID, image: dict[str, Any], *, error: str = "", alt_value: str = "", status: int = 200
) -> ResponseReturnValue:
    """Render the per-image details/edit modal fragment."""
    return render_template(
        "backoffice/registration/image_details_modal.html",
        assembly_id=assembly_id,
        image=image,
        error=error,
        alt_value=alt_value,
    ), status


def _image_action_error_message(error: Exception) -> str:
    """Map a known edit/delete failure to a user-facing message."""
    if isinstance(error, RegistrationImageNotFoundError):
        return _("Image not found")
    if isinstance(error, RegistrationPageNotFoundError):
        return _("Registration page not found")
    if isinstance(error, InsufficientPermissions):
        return _("You don't have permission to modify this assembly")
    return _("Assembly not found")


def _upload_error_message(error: Exception) -> str:
    """Map a known image-upload failure to a user-facing message."""
    if isinstance(error, ImageValidationError):
        return error.message
    if isinstance(error, ImageQuotaExceeded):
        return str(error)
    if isinstance(error, RegistrationPageNotFoundError):
        return _("Please create a registration page first from the Details tab.")
    if isinstance(error, InsufficientPermissions):
        return _("You don't have permission to modify this assembly")
    return _("Assembly not found")


def _render_image_upload_modal(
    assembly_id: uuid.UUID, *, error: str = "", alt_value: str = "", status: int = 200
) -> ResponseReturnValue:
    """Render the upload-modal fragment (swapped into ``#image-modal-container`` by HTMX)."""
    return render_template(
        "backoffice/registration/image_upload_modal.html",
        assembly_id=assembly_id,
        allowed_image_formats=sorted(ALLOWED_INPUT_FORMATS),
        max_image_upload_mb=get_max_image_upload_mb(),
        error=error,
        alt_value=alt_value,
    ), status


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/images/upload-modal")
@login_required
def image_upload_modal(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the image-upload modal.

    HTMX requests get just the modal fragment to swap into the Assets panel; a
    plain navigation gets the whole registration page with the modal already open,
    so opening the modal still works (via a full page load) when JS is unavailable.
    """
    if _is_htmx():
        return _render_image_upload_modal(assembly_id)
    return _render_registration_page(assembly_id, open_modal="upload")


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/images/<uuid:image_id>/details-modal")
@login_required
def image_details_modal(assembly_id: uuid.UUID, image_id: uuid.UUID) -> ResponseReturnValue:
    """Serve the per-image details/edit modal.

    HTMX requests get the modal fragment to swap into the Assets panel; a plain
    navigation gets the whole registration page with the modal already open.
    """
    try:
        image = _find_image_dict(assembly_id, image_id)
    except InsufficientPermissions:
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))

    if image is None:
        flash(_("Image not found"), "error")
        return redirect(url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id))

    if _is_htmx():
        return _render_image_details_modal(assembly_id, image)
    return _render_registration_page(assembly_id, open_modal="details", open_image_id=image_id)


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/images", methods=["POST"])
@login_required
def upload_registration_image(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Accept a multipart image upload from the Assets panel modal.

    Content-negotiates on HTMX: an HX-Request returns an empty body plus an
    ``HX-Trigger`` carrying the new image (the page appends it client-side and
    closes the modal), while a failure re-renders the modal with the error (422,
    swapped back by the htmx-422 handler). A plain form post redirects back to the
    registration page with a flash — the no-JS full-reload path.
    """
    upload = request.files.get("image")
    alt = (request.form.get("alt") or "").strip()

    def _fail(message: str) -> ResponseReturnValue:
        if _is_htmx():
            # 422 so the htmx-422-swap handler re-renders the modal with the error inline
            return _render_image_upload_modal(assembly_id, error=message, alt_value=alt, status=422)
        flash(message, "error")
        return redirect(
            url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id, modal="upload")
        )

    if upload is None or not upload.filename:
        return _fail(_("No file was selected"))

    try:
        raw = upload.read()
    except Exception as e:
        current_app.logger.warning(f"Failed to read uploaded image for assembly {assembly_id}: {e}")
        return _fail(_("Failed to read the uploaded file"))

    if not alt:
        return _fail(_("Alt text is required for accessibility"))

    try:
        add_registration_image(
            bootstrap.get_flask_uow(),
            current_user.id,
            assembly_id,
            raw,
            alt=alt,
            original_filename=upload.filename or "",
        )
    except (
        ImageValidationError,
        ImageQuotaExceeded,
        RegistrationPageNotFoundError,
        InsufficientPermissions,
        NotFoundError,
    ) as e:
        return _fail(_upload_error_message(e))
    except Exception as e:
        current_app.logger.error(f"Image upload error for assembly {assembly_id}: {e}")
        current_app.logger.exception("Full traceback:")
        return _fail(_("An error occurred while uploading the image"))

    if _is_htmx():
        # Refresh the Assets list out of band (which also closes the modal); the
        # toast trigger announces success.
        return _image_list_response(assembly_id, toast=_("Image uploaded"))

    flash(_("Image uploaded"), "success")
    return redirect(url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id))


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/images/<uuid:image_id>", methods=["PATCH"])
@login_required
def update_assembly_registration_image(assembly_id: uuid.UUID, image_id: uuid.UUID) -> ResponseReturnValue:
    """Update an image's alt text (PATCH from the details modal, HTMX only).

    Success returns the refreshed Assets list (out of band, which also closes the
    modal); an empty alt re-renders the modal with the error at 422.
    """
    alt = (request.form.get("alt") or "").strip()
    if not alt:
        image = _find_image_dict(assembly_id, image_id)
        if image is None:
            return _image_list_response(assembly_id, toast=_("Image not found"), toast_type="error")
        return _render_image_details_modal(
            assembly_id, image, error=_("Alt text is required for accessibility"), alt_value=alt, status=422
        )

    try:
        set_registration_image_alt(bootstrap.get_flask_uow(), current_user.id, assembly_id, image_id, alt=alt)
    except (RegistrationImageNotFoundError, RegistrationPageNotFoundError, InsufficientPermissions, NotFoundError) as e:
        return _image_list_response(assembly_id, toast=_image_action_error_message(e), toast_type="error")
    except Exception as e:
        current_app.logger.error(f"Update image alt error for assembly {assembly_id} image {image_id}: {e}")
        return _image_list_response(
            assembly_id, toast=_("An error occurred while updating the image"), toast_type="error"
        )

    return _image_list_response(assembly_id, toast=_("Image updated"))


@backoffice_registration_bp.route(
    "/assembly/<uuid:assembly_id>/registration/images/<uuid:image_id>", methods=["DELETE"]
)
@login_required
def delete_assembly_registration_image(assembly_id: uuid.UUID, image_id: uuid.UUID) -> ResponseReturnValue:
    """Delete a registration image (DELETE, HTMX only).

    Returns the refreshed Assets list (out of band, which also closes the modal
    when the delete came from it).
    """
    try:
        delete_registration_image(bootstrap.get_flask_uow(), current_user.id, assembly_id, image_id)
    except (RegistrationImageNotFoundError, RegistrationPageNotFoundError, InsufficientPermissions, NotFoundError) as e:
        return _image_list_response(assembly_id, toast=_image_action_error_message(e), toast_type="error")
    except Exception as e:
        current_app.logger.error(f"Delete image error for assembly {assembly_id} image {image_id}: {e}")
        return _image_list_response(
            assembly_id, toast=_("An error occurred while deleting the image"), toast_type="error"
        )

    return _image_list_response(assembly_id, toast=_("Image deleted"))
