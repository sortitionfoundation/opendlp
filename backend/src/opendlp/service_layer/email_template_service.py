"""ABOUTME: Service layer for managing assembly-scoped email templates
ABOUTME: Handles CRUD with permission checks, validation and auto-reply assignment"""

import uuid
from dataclasses import dataclass
from enum import Enum

import structlog

from opendlp.config import get_email_template_body_max_bytes
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.respondent_field_schema import FieldOnRegistrationPage, registration_email_field
from opendlp.translations import gettext as _

from .email_send_service import resolve_reply_to
from .exceptions import (
    EmailTemplateInvalid,
    EmailTemplateNotFoundError,
    InsufficientPermissions,
    RegistrationPageNotFoundError,
)
from .permissions import MANAGE_ROLE, can_manage_assembly, can_view_assembly, load_user_and_assembly
from .registration_page_service import page_for_assembly
from .unit_of_work import AbstractUnitOfWork

logger = structlog.get_logger(__name__)

_VIEW_ROLE = "assembly role or admin"


class AutoReplyReadinessSeverity(Enum):
    """Severity of an auto-reply configuration readiness problem."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class AutoReplyReadinessProblem:
    """A readiness problem with the auto-reply configuration for display to a manager."""

    severity: AutoReplyReadinessSeverity
    message: str


def _email_field_problems(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> list[AutoReplyReadinessProblem]:
    email_field = registration_email_field(uow.respondent_field_definitions.list_by_assembly(assembly_id))
    if email_field is None:
        return [
            AutoReplyReadinessProblem(
                AutoReplyReadinessSeverity.ERROR,
                _(
                    "The registration page does not collect an email address, so the auto-reply "
                    "can never be sent. Add a required email field to the page."
                ),
            )
        ]
    if email_field.on_registration_page == FieldOnRegistrationPage.YES_OPTIONAL:
        return [
            AutoReplyReadinessProblem(
                AutoReplyReadinessSeverity.WARNING,
                _(
                    "The email address is optional on the registration page, so respondents who "
                    "leave it blank will not receive the auto-reply."
                ),
            )
        ]
    return []


def _reply_to_problems(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, page_id: uuid.UUID
) -> list[AutoReplyReadinessProblem]:
    page = uow.registration_pages.get(page_id)
    if page is None or page.auto_reply_email_template_id is None:
        return []
    template = uow.email_templates.get(page.auto_reply_email_template_id)
    assembly = uow.assemblies.get(assembly_id)
    if template is None or assembly is None or resolve_reply_to(template, assembly) is not None:
        return []
    return [
        AutoReplyReadinessProblem(
            AutoReplyReadinessSeverity.WARNING,
            _(
                "Replies to the auto-reply will go to the address it is sent from, which may not be "
                "monitored. Set where replies go so they reach your team."
            ),
        )
    ]


def _auto_reply_readiness_problems(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, page_id: uuid.UUID | None = None
) -> list[AutoReplyReadinessProblem]:
    problems = _email_field_problems(uow, assembly_id)
    if page_id is not None:
        problems.extend(_reply_to_problems(uow, assembly_id, page_id))
    return problems


def auto_reply_readiness_problems(
    uow: AbstractUnitOfWork, assembly_id: uuid.UUID, page_id: uuid.UUID | None = None
) -> list[AutoReplyReadinessProblem]:
    """Readiness problems for sending an auto-reply.

    Checks how the page collects email: an ERROR when no email is collected (the
    auto-reply can never send), a WARNING when email is optional. Given a page_id,
    also warns when the page's auto-reply has nowhere for replies to go - no
    reply-to on its template or on the assembly. Returns every problem found.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    return _auto_reply_readiness_problems(uow, assembly_id, page_id)


def _validate(template: EmailTemplate) -> None:
    problems = template.validation_problems()
    max_bytes = get_email_template_body_max_bytes()
    if len(template.body_html.encode("utf-8")) > max_bytes:
        problems.append(_("The email body must be at most %(max_bytes)s bytes", max_bytes=max_bytes))
    if problems:
        raise EmailTemplateInvalid(problems)


def _load_template(uow: AbstractUnitOfWork, template_id: uuid.UUID) -> EmailTemplate:
    template: EmailTemplate | None = uow.email_templates.get(template_id)
    if template is None:
        raise EmailTemplateNotFoundError(f"Email template {template_id} not found")
    return template


def create_email_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    *,
    name: str,
    subject: str,
    body_html: str,
    reply_to_name: str = "",
    reply_to_email: str = "",
) -> EmailTemplate:
    """Create an email template for an assembly. Raises EmailTemplateInvalid on bad input.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user, assembly = load_user_and_assembly(uow, user_id, assembly_id)
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(action="create email template", required_role=MANAGE_ROLE)
    template = EmailTemplate(
        assembly_id=assembly_id,
        name=name,
        subject=subject,
        body_html=body_html,
        reply_to_name=reply_to_name,
        reply_to_email=reply_to_email,
    )
    _validate(template)
    uow.email_templates.add(template)
    return template.create_detached_copy()


def update_email_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
    *,
    name: str | None = None,
    subject: str | None = None,
    body_html: str | None = None,
    reply_to_name: str | None = None,
    reply_to_email: str | None = None,
) -> EmailTemplate:
    """Update an email template. Raises EmailTemplateInvalid on bad input.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    template = _load_template(uow, template_id)
    user, assembly = load_user_and_assembly(uow, user_id, template.assembly_id)
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(action="update email template", required_role=MANAGE_ROLE)
    template.update(
        name=name,
        subject=subject,
        body_html=body_html,
        reply_to_name=reply_to_name,
        reply_to_email=reply_to_email,
    )
    _validate(template)
    return template.create_detached_copy()


def get_email_template(uow: AbstractUnitOfWork, user_id: uuid.UUID, template_id: uuid.UUID) -> EmailTemplate:
    """Get an email template if the user may view its assembly.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    template = _load_template(uow, template_id)
    user, assembly = load_user_and_assembly(uow, user_id, template.assembly_id)
    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(action="view email template", required_role=_VIEW_ROLE)
    return template.create_detached_copy()


def list_email_templates(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> list[EmailTemplate]:
    """List the email templates for an assembly the user may view.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user, assembly = load_user_and_assembly(uow, user_id, assembly_id)
    if not can_view_assembly(user, assembly):
        raise InsufficientPermissions(action="view email templates", required_role=_VIEW_ROLE)
    return [t.create_detached_copy() for t in uow.email_templates.list_by_assembly(assembly_id)]


def delete_email_template(uow: AbstractUnitOfWork, user_id: uuid.UUID, template_id: uuid.UUID) -> None:
    """Delete an email template. The registration-page FK is cleared by ON DELETE SET NULL.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    template = _load_template(uow, template_id)
    user, assembly = load_user_and_assembly(uow, user_id, template.assembly_id)
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(action="delete email template", required_role=MANAGE_ROLE)
    uow.email_templates.delete(template)


def assign_auto_reply_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    template_id: uuid.UUID | None,
    *,
    page_id: uuid.UUID | None = None,
) -> RegistrationPage:
    """Set (or clear, with None) a registration page's auto-reply template.

    Targets the page_id when given, else the assembly's oldest page. Returns the
    updated page so callers can see which page was targeted.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    user, assembly = load_user_and_assembly(uow, user_id, assembly_id)
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(action="assign auto-reply template", required_role=MANAGE_ROLE)
    if page_id is not None:
        page = uow.registration_pages.get(page_id)
        if page is None or page.assembly_id != assembly_id:
            raise RegistrationPageNotFoundError(f"Registration page {page_id} not found for this assembly")
    else:
        page = page_for_assembly(uow, assembly_id)
        if page is None:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")
    if template_id is not None:
        template = uow.email_templates.get(template_id)
        if template is None or template.assembly_id != assembly_id:
            raise EmailTemplateNotFoundError(f"Email template {template_id} not found for this assembly")
    page.set_auto_reply_template(template_id)
    if template_id is not None:
        # Advisory only - never block configuring the auto-reply. The config UI
        # surfaces these via auto_reply_readiness_problems().
        for problem in _auto_reply_readiness_problems(uow, assembly_id, page.id):
            logger.warning(
                "Auto-reply readiness (%s) for assembly %s: %s",
                problem.severity.value,
                assembly_id,
                problem.message,
            )
    return page.create_detached_copy()
