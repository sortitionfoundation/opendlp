"""ABOUTME: Backoffice registration-page editor routes
ABOUTME: View / save / create / skeleton / QR-download / image upload routes for the assembly registration tab"""

import uuid
from typing import Any, cast

import structlog
from flask import Blueprint, Response, abort, flash, jsonify, redirect, render_template, request, url_for
from flask.typing import ResponseReturnValue
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException

from opendlp import bootstrap
from opendlp.config import get_max_image_upload_mb, get_max_pdf_upload_mb
from opendlp.domain.registration_document import (
    PDF_FILE_EXTENSION,
    DocumentValidationError,
    RegistrationDocument,
    generate_document_html,
)
from opendlp.domain.registration_image import (
    ALLOWED_INPUT_FORMATS,
    IMAGE_FILE_EXTENSION,
    ImageValidationError,
    RegistrationImage,
    generate_image_html,
)
from opendlp.domain.registration_page import (
    HtmlSource,
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageStatus,
)
from opendlp.domain.uploads import human_size
from opendlp.entrypoints.blueprints.registration import registration_url, short_url
from opendlp.entrypoints.scroll_utils import redirect_preserving_scroll
from opendlp.service_layer.assembly_service import get_assembly_nav_context
from opendlp.service_layer.email_template_service import (
    assign_auto_reply_template,
    auto_reply_readiness_problems,
    create_email_template,
    get_email_template,
    list_email_templates,
    update_email_template,
)
from opendlp.service_layer.exceptions import (
    DocumentQuotaExceeded,
    EmailTemplateInvalid,
    EmailTemplateNotFoundError,
    ImageQuotaExceeded,
    InsufficientPermissions,
    NotFoundError,
    RegistrationDocumentNotFoundError,
    RegistrationImageNotFoundError,
    RegistrationPageNotFoundError,
)
from opendlp.service_layer.qr_codes import generate_qr_code_base64, generate_qr_code_png
from opendlp.service_layer.registration_document_service import (
    add_registration_document,
    delete_registration_document,
    list_registration_documents,
    set_registration_document_label,
)
from opendlp.service_layer.registration_image_service import (
    add_registration_image,
    delete_registration_image,
    list_registration_images,
    set_registration_image_alt,
)
from opendlp.service_layer.registration_page_service import (
    close_registration_page,
    create_registration_page_with_slugs,
    generate_starter_form_html_variants,
    get_registration_page_with_source,
    list_registration_pages,
    publish_registration_page,
    render_registration_form,
    reopen_registration_page,
    unpublish_registration_page,
    update_registration_page_html,
)
from opendlp.translations import gettext as _

backoffice_registration_bp = Blueprint("backoffice_registration", __name__)

logger = structlog.get_logger(__name__)


def _sole_page(uow: Any, assembly_id: uuid.UUID) -> RegistrationPage | None:
    """The registration page these assembly-scoped routes act on, or None if there is none."""
    pages = list_registration_pages(uow, current_user.id, assembly_id)
    return pages[0] if pages else None


def _require_page(uow: Any, assembly_id: uuid.UUID) -> RegistrationPage:
    page = _sole_page(uow, assembly_id)
    if page is None:
        raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")
    return page


def _page_with_source(uow: Any, assembly_id: uuid.UUID) -> tuple[RegistrationPage, HtmlSource] | None:
    page = _sole_page(uow, assembly_id)
    return get_registration_page_with_source(uow, current_user.id, page.id) if page else None


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
        # Pre-computed accessible labels — built server-side with %(name)s placeholders
        # so translators can reorder the parts. Concatenating in the template
        # (e.g. "Delete " + display_name) hard-codes English word order.
        "aria_label_details": _("Details for %(name)s", name=display_name),
        "aria_label_copy_snippet": _("Copy <img> snippet for %(name)s", name=display_name),
        "aria_label_delete": _("Delete %(name)s", name=display_name),
    }


def _document_to_dict(document: RegistrationDocument, url_slug: str) -> dict[str, Any]:
    """Serialise a PDF document for the Assets panel.

    ``public_url`` is the public ``/register/<slug>/documents/<sha>.pdf`` route. If the
    page has no slug yet (newly created), we return a placeholder so the front-end
    can still render the row.
    """
    file_name = f"{document.sha256}.{PDF_FILE_EXTENSION}"
    public_url = (
        url_for("registration.serve_registration_document", url_slug=url_slug, document_name=file_name)
        if url_slug
        else ""
    )
    if document.label and document.label.strip():
        display_name = document.label.strip()
    elif document.original_filename:
        display_name = document.original_filename
    else:
        display_name = f"{document.sha256[:8]}.{PDF_FILE_EXTENSION}"
    snippet_text = f"{display_name} (PDF, {human_size(document.byte_size)})"
    return {
        "id": str(document.id),
        "label": document.label,
        "original_filename": document.original_filename,
        "file_name": file_name,
        "display_name": display_name,
        "public_url": public_url,
        "a_snippet": generate_document_html(public_url, snippet_text) if public_url else "",
        "byte_size": document.byte_size,
        "aria_label_details": _("Details for %(name)s", name=display_name),
        "aria_label_copy_snippet": _("Copy download link snippet for %(name)s", name=display_name),
        "aria_label_delete": _("Delete %(name)s", name=display_name),
    }


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration")
@login_required
def view_assembly_registration(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Backoffice registration form configuration page."""
    try:
        nav_uow = bootstrap.get_flask_uow()
        with nav_uow:
            nav = get_assembly_nav_context(
                nav_uow,
                current_user.id,
                assembly_id,
                request.args.get("source", ""),
            )

        # Get registration page and HTML source from service layer
        uow = bootstrap.get_flask_uow()
        with uow:
            result = _page_with_source(uow, assembly_id)

            # HTML content
            has_registration_page = result is not None
            registration_page = result[0] if result else None
            if result:
                html = cast("RegistrationPageHtml", result[1])
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

            # Load registration images and PDF documents for the Assets panel
            images: list[dict[str, Any]] = []
            documents: list[dict[str, Any]] = []
            if has_registration_page and registration_page:
                # Reuse the UnitOfWork from the page lookup above.
                stored_images = list_registration_images(uow, current_user.id, assembly_id)
                images = [_image_to_dict(image, registration_page.url_slug) for image in stored_images]
                stored_documents = list_registration_documents(uow, current_user.id, assembly_id)
                documents = [_document_to_dict(document, registration_page.url_slug) for document in stored_documents]

        # The HTML editor is read-only by default; ?edit=1 unlocks it. CLOSED pages
        # have no save path so we always keep them read-only regardless of the param.
        edit_mode = request.args.get("edit") == "1" and registration_status != "CLOSED"

        # Sub-section within the Registration tab (stepper). Default to the form editor.
        active_section = request.args.get("section", "form")
        if active_section not in ("form", "email", "preview"):
            active_section = "form"

        # Auto-reply email data — the template (if assigned) plus readiness problems.
        email_template, email_readiness_problems = _load_auto_reply_context(registration_page, assembly_id)

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
            documents=documents,
            max_image_upload_mb=get_max_image_upload_mb(),
            max_pdf_upload_mb=get_max_pdf_upload_mb(),
            allowed_image_formats=sorted(ALLOWED_INPUT_FORMATS),
            edit_mode=edit_mode,
            active_section=active_section,
            email_template=email_template,
            email_readiness_problems=email_readiness_problems,
        ), 200
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to view this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.error(
            "View assembly registration error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while loading registration settings"), "error")
        return redirect(url_for("backoffice.dashboard"))


def _handle_registration_action(action: str, user_id: uuid.UUID, assembly_id: uuid.UUID) -> str:
    """Handle publish/unpublish/close/reopen/save action for registration page. Returns flash message."""
    uow = bootstrap.get_flask_uow()
    with uow:
        if action == "publish":
            result = _page_with_source(uow, assembly_id)
            if result and result[0].status == RegistrationPageStatus.TEST:
                publish_registration_page(uow, user_id, result[0].id)
                return _("Registration form published successfully")
            return _("Registration form HTML updated successfully")
        if action == "unpublish":
            unpublish_registration_page(uow, user_id, _require_page(uow, assembly_id).id)
            return _("Registration form unpublished")
        if action == "close":
            close_registration_page(uow, user_id, _require_page(uow, assembly_id).id)
            return _("Registration form closed")
        if action == "reopen":
            reopen_registration_page(uow, user_id, _require_page(uow, assembly_id).id)
            return _("Registration form reopened")
        result = _page_with_source(uow, assembly_id)
    if result and result[0].status == RegistrationPageStatus.PUBLISHED:
        return _("Registration form saved and republished")
    return _("Registration form saved")


_SAVE_ACTIONS = frozenset({"save", "save_and_next"})
_LIFECYCLE_ACTIONS = frozenset({"publish", "unpublish", "close", "reopen"})


def _post_action_section(action: str) -> str:
    """Where to land after a successful action: save_and_next advances to the email
    step, lifecycle actions return to the preview step (where their buttons live),
    and plain save returns to the form step."""
    if action == "save_and_next":
        return "email"
    if action in _LIFECYCLE_ACTIONS:
        return "preview"
    return "form"


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/save", methods=["POST"])
@login_required
def save_assembly_registration(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Save the registration HTML and/or trigger a lifecycle transition.

    Actions:
      - save            → update HTML; land back in read-only on the form step.
      - save_and_next   → update HTML; advance to the auto-reply email step.
      - publish         → transition TEST → PUBLISHED. No HTML update.
      - unpublish       → transition PUBLISHED → TEST (back to test mode).
      - close           → transition to CLOSED. Terminal from the UI's point of
                          view: reopen exists only for backwards compatibility
                          with older POSTs and is not offered anywhere.
    """
    action = request.form.get("action", "save")
    # On failure of a save action, land back in edit mode of the form step so the
    # user can fix and retry. Lifecycle actions come from the read-only preview
    # step, so failure just lands them back on the preview step.
    error_kwargs: dict[str, Any] = {"assembly_id": assembly_id, "section": "form"}
    if action in _SAVE_ACTIONS:
        error_kwargs["edit"] = "1"
    elif action in _LIFECYCLE_ACTIONS:
        error_kwargs["section"] = "preview"
    error_redirect_url = url_for("backoffice_registration.view_assembly_registration", **error_kwargs)
    try:
        # Verify user has permission to access this assembly (side effect: raises if unauthorized)
        nav_uow = bootstrap.get_flask_uow()
        with nav_uow:
            get_assembly_nav_context(
                nav_uow,
                current_user.id,
                assembly_id,
                "",
            )

        # Only save-family actions carry HTML content. Publish/close/etc post from
        # buttons that don't render the editor, so guard against blanking the HTML.
        if "html_content" in request.form:
            uow = bootstrap.get_flask_uow()
            with uow:
                update_registration_page_html(
                    uow, current_user.id, _require_page(uow, assembly_id).id, request.form["html_content"]
                )

        flash_message = _handle_registration_action(action, current_user.id, assembly_id)
        flash(flash_message, "success")
        next_section = _post_action_section(action)
        return redirect_preserving_scroll(
            url_for(
                "backoffice_registration.view_assembly_registration",
                assembly_id=assembly_id,
                section=next_section,
            )
        )
    except RegistrationPageNotReady as e:
        # Show specific validation errors for publishing
        error_message = "; ".join(e.problems)
        logger.warning(
            "Registration page not ready for assembly", assembly_id=str(assembly_id), error_message=error_message
        )
        flash(error_message, "error")
        return redirect_preserving_scroll(error_redirect_url)
    except RegistrationPageNotFoundError:
        # Registration page doesn't exist yet - redirect to Details tab to create it
        flash(_("Please create a registration page first from the Details tab."), "warning")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except InsufficientPermissions as e:
        logger.warning(
            "Insufficient permissions for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to modify this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except ValueError as e:
        logger.warning("Validation error for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(str(e), "error")
        return redirect_preserving_scroll(error_redirect_url)
    except Exception as e:
        logger.exception(
            "Save assembly registration error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("An error occurred while saving registration settings"), "error")
        return redirect_preserving_scroll(error_redirect_url)


def _load_auto_reply_context(registration_page: Any, assembly_id: uuid.UUID) -> tuple[Any, list[dict[str, str]]]:
    """Load the auto-reply template and readiness problems for the view route.

    Prefers the template currently assigned to the page. When nothing is assigned
    (a legacy state from before the auto-reply became always-on) falls back to the
    first template stored for the assembly, so the editor still shows the
    pre-created copy for the manager to work on.
    """
    email_template = None
    email_readiness_problems: list[dict[str, str]] = []
    if registration_page is None:
        return email_template, email_readiness_problems

    uow = bootstrap.get_flask_uow()
    template_id = registration_page.auto_reply_email_template_id
    if template_id is not None:
        try:
            with uow:
                email_template = get_email_template(uow, current_user.id, template_id)
        except EmailTemplateNotFoundError:
            logger.debug(
                "auto_reply_template_load_failed",
                assembly_id=str(assembly_id),
                template_id=str(template_id),
                reason="not_found",
            )
            email_template = None
        except InsufficientPermissions:
            logger.debug(
                "auto_reply_template_load_failed",
                assembly_id=str(assembly_id),
                template_id=str(template_id),
                user_id=str(current_user.id),
                reason="forbidden",
            )
            email_template = None

    if email_template is None:
        try:
            with uow:
                templates = list_email_templates(uow, current_user.id, assembly_id)
            if templates:
                email_template = templates[0]
        except InsufficientPermissions:
            logger.debug(
                "auto_reply_template_list_failed",
                assembly_id=str(assembly_id),
                user_id=str(current_user.id),
                reason="forbidden",
            )
            email_template = None

    with uow:
        problems = auto_reply_readiness_problems(uow, assembly_id)
    email_readiness_problems = [{"severity": p.severity.value, "message": p.message} for p in problems]
    return email_template, email_readiness_problems


def _default_email_template_content() -> dict[str, str]:
    """Sensible starter values for a freshly-created auto-reply template.

    The name is not shown to respondents; it's a manager-facing label. When we
    later support multiple templates per assembly we'll expose it in the UI —
    for now it's a stable default so the domain-level requirement is satisfied
    without any manager input.
    """
    return {
        "name": _("Registration auto-reply"),
        "subject": _("Thanks for registering for {{ assembly.title }}"),
        "body_html": _(
            "<p>Hi {{ respondent.first_name_or_friend }},</p>\n"
            "<p>Thanks for registering for <strong>{{ assembly.title }}</strong>.</p>\n"
            "<p>We'll be in touch about the assembly on {{ assembly.first_assembly_date }}.</p>\n"
            "<p>Best wishes,<br>The team</p>"
        ),
    }


def _email_section_url(assembly_id: uuid.UUID, edit: bool = False) -> str:
    kwargs: dict[str, Any] = {"assembly_id": assembly_id, "section": "email"}
    if edit:
        kwargs["edit"] = "1"
    return url_for("backoffice_registration.view_assembly_registration", **kwargs)


def _create_and_assign_default_template(assembly_id: uuid.UUID) -> None:
    """Create the default auto-reply template and assign it to the assembly's page.

    The auto-reply is always-on: a created template is an assigned template, and
    this helper is the single place that enforces that invariant.
    """
    defaults = _default_email_template_content()
    uow = bootstrap.get_flask_uow()
    with uow:
        template = create_email_template(
            uow,
            current_user.id,
            assembly_id,
            name=defaults["name"],
            subject=defaults["subject"],
            body_html=defaults["body_html"],
        )
        assign_auto_reply_template(uow, current_user.id, assembly_id, template.id)


def _handle_email_action_create(assembly_id: uuid.UUID) -> str:
    """Create a stub auto-reply template, assign it, and return the redirect URL (edit mode)."""
    _create_and_assign_default_template(assembly_id)
    flash(_("Auto-reply email created. Edit it below and click Save."), "success")
    return _email_section_url(assembly_id, edit=True)


def _handle_email_action_save(
    assembly_id: uuid.UUID,
    template_id: uuid.UUID | None,
    *,
    advance: bool = False,
) -> str:
    if template_id is None:
        flash(_("There is no auto-reply email to save yet — set one up first."), "warning")
        return _email_section_url(assembly_id)
    # Name is intentionally not overwritten here — the UI doesn't expose it yet,
    # so we keep the value that was set at auto-creation time. Once multi-template
    # support ships we'll add name to the form and pass it here.
    uow = bootstrap.get_flask_uow()
    with uow:
        update_email_template(
            uow,
            current_user.id,
            template_id,
            subject=request.form.get("template_subject", "").strip(),
            body_html=request.form.get("template_body_html", ""),
        )
    flash(_("Auto-reply email saved."), "success")
    if advance:
        return url_for(
            "backoffice_registration.view_assembly_registration",
            assembly_id=assembly_id,
            section="preview",
        )
    return _email_section_url(assembly_id)


def _dispatch_email_action(action: str, assembly_id: uuid.UUID) -> str:
    """Run the requested action and return the URL to redirect to.

    Raises the service-layer exceptions the caller handles centrally.
    """
    nav_uow = bootstrap.get_flask_uow()
    with nav_uow:
        get_assembly_nav_context(nav_uow, current_user.id, assembly_id, "")
        page = _sole_page(nav_uow, assembly_id)
    if page is None:
        raise RegistrationPageNotFoundError(f"No registration page for assembly {assembly_id}")

    if action == "create":
        return _handle_email_action_create(assembly_id)
    if action not in ("save", "save_and_next"):
        flash(_("Unknown action — nothing was changed."), "warning")
        return _email_section_url(assembly_id)
    # Save always targets the page's assigned template. The form does not choose a
    # template, so a posted template_id is deliberately ignored — trusting it would
    # let a request update a template belonging to a different assembly.
    return _handle_email_action_save(
        assembly_id,
        page.auto_reply_email_template_id,
        advance=(action == "save_and_next"),
    )


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/email/save", methods=["POST"])
@login_required
def save_assembly_registration_email(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Create or update the auto-reply email template.

    Action-based POST endpoint:

    - create   → create a template with default copy and assign it as the auto-reply.
                 Lands the user in edit mode so they can immediately customise it.
    - save     → update subject / body_html on the page's assigned template.

    There is deliberately no enable/disable: the product currently always sends the
    auto-reply. If a real need to switch it off emerges, that gets a first-class
    service-layer method — not the old assign/unassign-as-a-toggle trick.
    """
    action = request.form.get("action", "save")
    try:
        return redirect_preserving_scroll(_dispatch_email_action(action, assembly_id))
    except EmailTemplateInvalid as e:
        for problem in e.problems:
            flash(problem, "error")
        return redirect_preserving_scroll(_email_section_url(assembly_id, edit=True))
    except EmailTemplateNotFoundError:
        flash(_("The auto-reply email could not be found."), "error")
        return redirect_preserving_scroll(_email_section_url(assembly_id))
    except RegistrationPageNotFoundError:
        flash(_("Please create a registration page first from the Details tab."), "warning")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except InsufficientPermissions:
        flash(_("You don't have permission to modify this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError:
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.exception(
            "Save assembly registration email error",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("An error occurred while saving the auto-reply email"), "error")
        return redirect_preserving_scroll(_email_section_url(assembly_id))


def _create_default_auto_reply_template(assembly_id: uuid.UUID) -> None:
    """Best-effort: seed a default auto-reply email template for a new page.

    Not fatal — if this fails (validation, race, etc.) we log and let the manager
    hit the "Set up auto-reply" fallback in the UI. The template is assigned
    straight away: the auto-reply is always-on, so a page with a template sends it.
    """
    try:
        _create_and_assign_default_template(assembly_id)
    except Exception as e:
        # Non-fatal: log with traceback per code_quality_rules for catch-all blocks.
        logger.exception(
            "Failed to seed default auto-reply email template",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/create", methods=["POST"])
@login_required
def create_assembly_registration_page(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Create a registration page with auto-generated slugs from the assembly name."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            create_registration_page_with_slugs(uow, current_user.id, assembly_id, name=_("Registration page"))
        _create_default_auto_reply_template(assembly_id)
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
        logger.warning("Cannot create registration page for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("This assembly already has a registration page."), "warning")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))
    except Exception as e:
        logger.exception("Error creating registration page for assembly", assembly_id=str(assembly_id), error=str(e))
        flash(_("An error occurred while creating the registration page"), "error")
        return redirect(url_for("backoffice.view_assembly", assembly_id=assembly_id))


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/skeleton")
@login_required
def get_registration_skeleton(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Generate starter HTML form skeleton based on assembly's field definitions."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            variants = generate_starter_form_html_variants(uow, current_user.id, assembly_id)
        return jsonify({"html": variants.plain, "html_govuk": variants.govuk})
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to access this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        logger.error("Generate skeleton error for assembly", assembly_id=str(assembly_id), error=str(e))
        return jsonify({"error": _("An error occurred while generating the form skeleton")}), 500


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/form-preview")
@login_required
def preview_registration_form(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Read-only render of the saved registration form, embedded in the preview step.

    Renders the last saved HTML through the same pipeline as the public route, so
    organisers see exactly what visitors will see without opening the public URL.
    Submission is neutralised twice over: the empty form action posts back to this
    GET-only route (405), and the preview template's script blocks submit events so
    interactions (dropdowns etc.) remain testable without ever leaving the page.
    The security form elements (CSRF/timing/honeypot) are deliberately omitted —
    they only exist to protect real submissions. The endpoint is exempted from the
    global frame-ancestors 'none' policy (see SAME_ORIGIN_FRAMEABLE_ENDPOINTS) so
    the backoffice can iframe it same-origin.
    """
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            page = _sole_page(uow, assembly_id)
            if page is None:
                abort(404)
            rendered_form = render_registration_form(
                uow,
                page,
                csrf_form_element="<!-- preview: submission disabled, security fields omitted -->",
                form_action="",
            )
        return render_template(
            "register/form_preview.html",
            rendered_form=rendered_form,
            is_test=page.status == RegistrationPageStatus.TEST,
        )
    except HTTPException:
        raise
    except InsufficientPermissions:
        abort(403)
    except NotFoundError:
        abort(404)
    except Exception:
        logger.exception("Registration form preview error", assembly_id=str(assembly_id))
        abort(500)


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/qr-code.png")
@login_required
def download_registration_qr_code(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Download registration QR code as PNG image."""
    try:
        # Verify user has permission to access this assembly
        nav_uow = bootstrap.get_flask_uow()
        with nav_uow:
            get_assembly_nav_context(
                nav_uow,
                current_user.id,
                assembly_id,
                "",
            )

        # The QR code encodes the short URL, so a short slug must be configured
        uow = bootstrap.get_flask_uow()
        with uow:
            result = _page_with_source(uow, assembly_id)
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
        logger.warning(
            "Insufficient permissions for assembly",
            assembly_id=str(assembly_id),
            user_id=str(current_user.id),
            error=str(e),
        )
        flash(_("You don't have permission to access this assembly"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except NotFoundError as e:
        logger.warning(
            "Assembly not found for user", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e)
        )
        flash(_("Assembly not found"), "error")
        return redirect(url_for("backoffice.dashboard"))
    except Exception as e:
        logger.error("Download QR code error", assembly_id=str(assembly_id), user_id=str(current_user.id), error=str(e))
        flash(_("An error occurred while generating QR code"), "error")
        return redirect(url_for("backoffice_registration.view_assembly_registration", assembly_id=assembly_id))


def _resolve_page_url_slug(assembly_id: uuid.UUID) -> str:
    """Look up the registration page's url_slug for serialising image URLs.

    Returns an empty string when the page doesn't exist yet — the caller can
    decide whether to omit the public URL.
    """
    uow = bootstrap.get_flask_uow()
    with uow:
        result = _page_with_source(uow, assembly_id)
    if result is None:
        return ""
    return result[0].url_slug


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/images", methods=["POST"])
@login_required
def upload_registration_image(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Accept a multipart image upload and return the stored image metadata as JSON.

    The Assets panel calls this from the registration tab so uploads don't disturb
    the HTML editor's unsaved state — no full-page reload is required.
    """
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        return jsonify({"error": _("No file was selected")}), 400

    try:
        raw = upload.read()
    except Exception as e:
        logger.warning("Failed to read uploaded image for assembly", assembly_id=str(assembly_id), error=str(e))
        return jsonify({"error": _("Failed to read the uploaded file")}), 400

    alt = (request.form.get("alt") or "").strip()
    if not alt:
        return jsonify({"error": _("Alt text is required for accessibility")}), 400

    uow = bootstrap.get_flask_uow()
    try:
        with uow:
            image = add_registration_image(
                uow,
                current_user.id,
                assembly_id,
                raw,
                alt=alt,
                original_filename=upload.filename or "",
            )
    except ImageValidationError as e:
        return jsonify({"error": e.message, "reason": e.reason}), 400
    except ImageQuotaExceeded as e:
        return jsonify({"error": str(e)}), 400
    except RegistrationPageNotFoundError:
        return jsonify({"error": _("Please create a registration page first from the Details tab.")}), 400
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to modify this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        logger.exception("Image upload error for assembly", assembly_id=str(assembly_id), error=str(e))
        return jsonify({"error": _("An error occurred while uploading the image")}), 500

    return jsonify({"image": _image_to_dict(image, _resolve_page_url_slug(assembly_id))}), 201


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/images/<uuid:image_id>", methods=["PATCH"])
@login_required
def update_assembly_registration_image(assembly_id: uuid.UUID, image_id: uuid.UUID) -> ResponseReturnValue:
    """Update an image's alt text. Returns the updated image metadata as JSON."""
    data = request.get_json(silent=True) or {}
    alt = (data.get("alt") or "").strip()
    if not alt:
        return jsonify({"error": _("Alt text is required for accessibility")}), 400

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            image = set_registration_image_alt(uow, current_user.id, assembly_id, image_id, alt=alt)
    except RegistrationImageNotFoundError:
        return jsonify({"error": _("Image not found")}), 404
    except RegistrationPageNotFoundError:
        return jsonify({"error": _("Registration page not found")}), 404
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to modify this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        logger.error("Update image alt error", assembly_id=str(assembly_id), image_id=str(image_id), error=str(e))
        return jsonify({"error": _("An error occurred while updating the image")}), 500

    return jsonify({"image": _image_to_dict(image, _resolve_page_url_slug(assembly_id))}), 200


@backoffice_registration_bp.route(
    "/assembly/<uuid:assembly_id>/registration/images/<uuid:image_id>", methods=["DELETE"]
)
@login_required
def delete_assembly_registration_image(assembly_id: uuid.UUID, image_id: uuid.UUID) -> ResponseReturnValue:
    """Delete a registration image. Returns 204 on success."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            delete_registration_image(uow, current_user.id, assembly_id, image_id)
    except RegistrationImageNotFoundError:
        return jsonify({"error": _("Image not found")}), 404
    except RegistrationPageNotFoundError:
        return jsonify({"error": _("Registration page not found")}), 404
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to modify this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        logger.error("Delete image error", assembly_id=str(assembly_id), image_id=str(image_id), error=str(e))
        return jsonify({"error": _("An error occurred while deleting the image")}), 500

    return "", 204


@backoffice_registration_bp.route("/assembly/<uuid:assembly_id>/registration/documents", methods=["POST"])
@login_required
def upload_registration_document(assembly_id: uuid.UUID) -> ResponseReturnValue:
    """Accept a multipart PDF upload and return the stored document metadata as JSON.

    The Assets panel calls this from the registration tab so uploads don't disturb
    the HTML editor's unsaved state — no full-page reload is required.
    """
    upload = request.files.get("document")
    if upload is None or not upload.filename:
        return jsonify({"error": _("No file was selected")}), 400

    try:
        raw = upload.read()
    except Exception as e:
        logger.warning("Failed to read uploaded document for assembly", assembly_id=str(assembly_id), error=str(e))
        return jsonify({"error": _("Failed to read the uploaded file")}), 400

    label = (request.form.get("label") or "").strip()

    uow = bootstrap.get_flask_uow()
    try:
        with uow:
            document = add_registration_document(
                uow,
                current_user.id,
                assembly_id,
                raw,
                original_filename=upload.filename or "",
                label=label,
            )
    except DocumentValidationError as e:
        return jsonify({"error": e.message, "reason": e.reason}), 400
    except DocumentQuotaExceeded as e:
        return jsonify({"error": str(e)}), 400
    except RegistrationPageNotFoundError:
        return jsonify({"error": _("Please create a registration page first from the Details tab.")}), 400
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to modify this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        logger.exception("Document upload error for assembly", assembly_id=str(assembly_id), error=str(e))
        return jsonify({"error": _("An error occurred while uploading the document")}), 500

    return jsonify({"document": _document_to_dict(document, _resolve_page_url_slug(assembly_id))}), 201


@backoffice_registration_bp.route(
    "/assembly/<uuid:assembly_id>/registration/documents/<uuid:document_id>", methods=["PATCH"]
)
@login_required
def update_assembly_registration_document(assembly_id: uuid.UUID, document_id: uuid.UUID) -> ResponseReturnValue:
    """Update a document's label. Returns the updated document metadata as JSON."""
    data = request.get_json(silent=True) or {}
    label = (data.get("label") or "").strip()
    if not label:
        return jsonify({"error": _("Label is required")}), 400

    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            document = set_registration_document_label(uow, current_user.id, assembly_id, document_id, label=label)
    except RegistrationDocumentNotFoundError:
        return jsonify({"error": _("Document not found")}), 404
    except RegistrationPageNotFoundError:
        return jsonify({"error": _("Registration page not found")}), 404
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to modify this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        logger.error(
            "Update document label error", assembly_id=str(assembly_id), document_id=str(document_id), error=str(e)
        )
        return jsonify({"error": _("An error occurred while updating the document")}), 500

    return jsonify({"document": _document_to_dict(document, _resolve_page_url_slug(assembly_id))}), 200


@backoffice_registration_bp.route(
    "/assembly/<uuid:assembly_id>/registration/documents/<uuid:document_id>", methods=["DELETE"]
)
@login_required
def delete_assembly_registration_document(assembly_id: uuid.UUID, document_id: uuid.UUID) -> ResponseReturnValue:
    """Delete a registration document. Returns 204 on success."""
    try:
        uow = bootstrap.get_flask_uow()
        with uow:
            delete_registration_document(uow, current_user.id, assembly_id, document_id)
    except RegistrationDocumentNotFoundError:
        return jsonify({"error": _("Document not found")}), 404
    except RegistrationPageNotFoundError:
        return jsonify({"error": _("Registration page not found")}), 404
    except InsufficientPermissions:
        return jsonify({"error": _("You don't have permission to modify this assembly")}), 403
    except NotFoundError:
        return jsonify({"error": _("Assembly not found")}), 404
    except Exception as e:
        logger.error("Delete document error", assembly_id=str(assembly_id), document_id=str(document_id), error=str(e))
        return jsonify({"error": _("An error occurred while deleting the document")}), 500

    return "", 204
