"""ABOUTME: Service layer for creating, updating and sending database-stored email templates
ABOUTME: Covers template CRUD, registration auto-reply wiring, and building the render context"""

import logging
import uuid
from collections.abc import Sequence

from opendlp.adapters.email import EmailAdapter
from opendlp.domain.assembly import Assembly
from opendlp.domain.email_template import (
    AssemblyContext,
    EmailTemplate,
    RespondentContext,
)
from opendlp.domain.respondents import Respondent, normalise_field_name

from .exceptions import (
    AssemblyNotFoundError,
    EmailTemplateNotFoundError,
    InsufficientPermissions,
    RegistrationPageNotFoundError,
    UserNotFoundError,
)
from .permissions import can_manage_assembly, can_view_assembly
from .unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)

_MANAGE_ROLE = "assembly-manager, global-organiser or admin"
_VIEW_ROLE = "assembly role or global privileges"


def _load_user_and_assembly(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    return user, assembly


def _load_template(uow: AbstractUnitOfWork, template_id: uuid.UUID) -> EmailTemplate:
    template = uow.email_templates.get(template_id)
    if template is None:
        raise EmailTemplateNotFoundError(f"Email template {template_id} not found")
    assert isinstance(template, EmailTemplate)
    return template


# --- Template CRUD -------------------------------------------------------------


def create_email_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    name: str,
    subject: str,
    body_html: str,
) -> EmailTemplate:
    """Create an email template for an assembly.

    Raises InsufficientPermissions if the user cannot manage the assembly and
    ValueError if the template fails validation (empty/invalid subject or body).
    """
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="create email template", required_role=_MANAGE_ROLE)

        template = EmailTemplate(
            assembly_id=assembly_id,
            name=name,
            subject=subject,
            body_html=body_html,
        )
        problems = template.validation_problems()
        if problems:
            raise ValueError("; ".join(problems))

        uow.email_templates.add(template)
        uow.commit()
        return template.create_detached_copy()


def update_email_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
    *,
    name: str | None = None,
    subject: str | None = None,
    body_html: str | None = None,
) -> EmailTemplate:
    """Update an email template. Fields left as None are unchanged.

    Raises InsufficientPermissions, EmailTemplateNotFoundError, or ValueError
    if the resulting template fails validation.
    """
    with uow:
        template = _load_template(uow, template_id)
        user, assembly = _load_user_and_assembly(uow, user_id, template.assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="update email template", required_role=_MANAGE_ROLE)

        template.update(name=name, subject=subject, body_html=body_html)
        problems = template.validation_problems()
        if problems:
            raise ValueError("; ".join(problems))

        uow.commit()
        return template.create_detached_copy()


def get_email_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
) -> EmailTemplate:
    """Return a single email template the user is allowed to view."""
    with uow:
        template = _load_template(uow, template_id)
        user, assembly = _load_user_and_assembly(uow, user_id, template.assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view email template", required_role=_VIEW_ROLE)
        return template.create_detached_copy()


def list_email_templates(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
) -> list[EmailTemplate]:
    """Return all email templates for an assembly, newest first."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="list email templates", required_role=_VIEW_ROLE)
        return [t.create_detached_copy() for t in uow.email_templates.list_by_assembly(assembly_id)]


def delete_email_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
) -> None:
    """Delete an email template.

    The FK from registration_pages.auto_reply_email_template_id is ON DELETE
    SET NULL, so any page using this template as its auto-reply is simply
    detached rather than blocked.
    """
    with uow:
        template = _load_template(uow, template_id)
        user, assembly = _load_user_and_assembly(uow, user_id, template.assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="delete email template", required_role=_MANAGE_ROLE)
        uow.email_templates.delete(template)
        uow.commit()


# --- Registration auto-reply wiring -------------------------------------------


def set_registration_auto_reply_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    template_id: uuid.UUID | None,
) -> None:
    """Set (or clear, with None) the auto-reply template for an assembly's page.

    Raises if the page does not exist, the template is not found, or the
    template belongs to a different assembly.
    """
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="set auto-reply template", required_role=_MANAGE_ROLE)

        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")

        if template_id is not None:
            template = _load_template(uow, template_id)
            if template.assembly_id != assembly_id:
                raise ValueError("The email template belongs to a different assembly")

        page.set_auto_reply_template(template_id)
        uow.commit()


# --- Render context ------------------------------------------------------------


def build_assembly_context(assembly: Assembly) -> AssemblyContext:
    """Build the documented ``{{ assembly.* }}`` context from an Assembly.

    ``info_url`` is intentionally empty: Assembly has no info-URL field yet, so
    the placeholder renders blank until one is added.
    """
    return AssemblyContext(
        title=assembly.title,
        question=assembly.question,
        info_url="",
        first_assembly_date=(assembly.first_assembly_date.isoformat() if assembly.first_assembly_date else ""),
        number_to_select=assembly.number_to_select,
    )


def build_respondent_context(respondent: Respondent) -> RespondentContext:
    """Build the documented ``{{ respondent.* }}`` context from a Respondent.

    Names are derived from the submitted attributes by loosely matching common
    field keys (firstname/lastname/surname/fullname/name). All submitted
    attributes are also exposed under ``attributes`` keyed by their field key,
    so an author can reference any assembly-specific field.
    """
    normalised = {
        normalise_field_name(key): str(value).strip()
        for key, value in respondent.attributes.items()
        if value is not None and str(value).strip()
    }
    first_name = normalised.get("firstname") or normalised.get("first") or ""
    last_name = normalised.get("lastname") or normalised.get("surname") or normalised.get("last") or ""
    full_name = (
        normalised.get("fullname")
        or normalised.get("name")
        or " ".join(part for part in (first_name, last_name) if part)
    )
    return RespondentContext(
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        email=respondent.email,
        attributes=dict(respondent.attributes),
    )


def build_respondent_email_context(assembly: Assembly, respondent: Respondent) -> dict[str, object]:
    """Assemble the full context dict passed to ``EmailTemplate.render``."""
    return {
        "assembly": build_assembly_context(assembly),
        "respondent": build_respondent_context(respondent),
    }


# --- Sending -------------------------------------------------------------------


def send_templated_email(
    email_adapter: EmailAdapter,
    template: EmailTemplate,
    context: dict[str, object],
    recipients: Sequence[str | tuple[str, str]],
    from_email: str | tuple[str, str] | None = None,
) -> bool:
    """Render a template against a context and send it to the given recipients.

    Returns True on success. Rendering or sending errors are logged and return
    False rather than propagating, so a single bad send never aborts a caller
    that is processing many recipients.
    """
    try:
        rendered = template.render(context)
    except Exception:
        logger.exception("Failed to render email template %s", template.id)
        return False

    return email_adapter.send_email(
        to=list(recipients),
        subject=rendered.subject,
        text_body=rendered.text_body,
        html_body=rendered.html_body,
        from_email=from_email,
    )


def send_registration_auto_reply(
    uow: AbstractUnitOfWork,
    email_adapter: EmailAdapter,
    *,
    assembly_id: uuid.UUID,
    respondent: Respondent,
) -> bool:
    """Send the registration auto-reply for a freshly submitted respondent.

    Returns False (without error) when there is nothing to do — no registration
    page, no auto-reply template configured, or no respondent email address.
    This is best-effort: it is safe to call from the submission flow and never
    raises on a missing template or a failed send.
    """
    if not respondent.email:
        return False

    with uow:
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if page is None or page.auto_reply_email_template_id is None:
            return False

        template = uow.email_templates.get(page.auto_reply_email_template_id)
        assembly = uow.assemblies.get(assembly_id)
        if template is None or assembly is None:
            return False

        detached_template = template.create_detached_copy()
        context = build_respondent_email_context(assembly, respondent)

    # Send outside the transaction: the read above is complete and we don't want
    # to hold a DB transaction open across the (potentially slow) SMTP call.
    success = send_templated_email(email_adapter, detached_template, context, recipients=[respondent.email])
    if success:
        logger.info("Sent registration auto-reply to %s for assembly %s", respondent.email, assembly_id)
    else:
        logger.error("Failed to send registration auto-reply for assembly %s", assembly_id)
    return success
