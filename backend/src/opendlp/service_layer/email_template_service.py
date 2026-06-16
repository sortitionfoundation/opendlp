"""ABOUTME: Service layer for managing assembly-scoped email templates
ABOUTME: Handles CRUD with permission checks, validation and auto-reply assignment"""

import logging
import uuid
from dataclasses import dataclass
from enum import Enum

from opendlp.config import get_email_template_body_max_bytes
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.respondent_field_schema import FieldOnRegistrationPage
from opendlp.translations import gettext as _

from .exceptions import (
    AssemblyNotFoundError,
    EmailTemplateInvalid,
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
_EMAIL_FIELD_KEY = "email"


class AutoReplyReadinessSeverity(Enum):
    """Severity of an auto-reply configuration readiness problem."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class AutoReplyReadinessProblem:
    """A readiness problem with the auto-reply configuration for display to a manager."""

    severity: AutoReplyReadinessSeverity
    message: str


def _auto_reply_readiness_problems(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> list[AutoReplyReadinessProblem]:
    email_field = uow.respondent_field_definitions.get_by_assembly_and_key(assembly_id, _EMAIL_FIELD_KEY)
    if email_field is None or email_field.on_registration_page == FieldOnRegistrationPage.NO:
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


def auto_reply_readiness_problems(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> list[AutoReplyReadinessProblem]:
    """Readiness problems for sending an auto-reply, based on how the page collects email.

    Returns an ERROR when no email is collected (the auto-reply can never send), a
    WARNING when email is optional, and an empty list when email is required.
    """
    with uow:
        return _auto_reply_readiness_problems(uow, assembly_id)


def _load_user_and_assembly(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID):  # type: ignore[no-untyped-def]
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    return user, assembly


def _validate(template: EmailTemplate) -> None:
    problems = template.validation_problems()
    max_bytes = get_email_template_body_max_bytes()
    if len(template.body_html.encode("utf-8")) > max_bytes:
        problems.append(f"The email body must be at most {max_bytes} bytes")
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
) -> EmailTemplate:
    """Create an email template for an assembly. Raises EmailTemplateInvalid on bad input."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="create email template", required_role=_MANAGE_ROLE)
        template = EmailTemplate(assembly_id=assembly_id, name=name, subject=subject, body_html=body_html)
        _validate(template)
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
    """Update an email template. Raises EmailTemplateInvalid on bad input."""
    with uow:
        template = _load_template(uow, template_id)
        user, assembly = _load_user_and_assembly(uow, user_id, template.assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="update email template", required_role=_MANAGE_ROLE)
        template.update(name=name, subject=subject, body_html=body_html)
        _validate(template)
        uow.commit()
        return template.create_detached_copy()


def get_email_template(uow: AbstractUnitOfWork, user_id: uuid.UUID, template_id: uuid.UUID) -> EmailTemplate:
    """Get an email template if the user may view its assembly."""
    with uow:
        template = _load_template(uow, template_id)
        user, assembly = _load_user_and_assembly(uow, user_id, template.assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view email template", required_role=_VIEW_ROLE)
        return template.create_detached_copy()


def list_email_templates(uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID) -> list[EmailTemplate]:
    """List the email templates for an assembly the user may view."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view email templates", required_role=_VIEW_ROLE)
        return [t.create_detached_copy() for t in uow.email_templates.list_by_assembly(assembly_id)]


def delete_email_template(uow: AbstractUnitOfWork, user_id: uuid.UUID, template_id: uuid.UUID) -> None:
    """Delete an email template. The registration-page FK is cleared by ON DELETE SET NULL."""
    with uow:
        template = _load_template(uow, template_id)
        user, assembly = _load_user_and_assembly(uow, user_id, template.assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="delete email template", required_role=_MANAGE_ROLE)
        uow.email_templates.delete(template)
        uow.commit()


def assign_auto_reply_template(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    template_id: uuid.UUID | None,
) -> None:
    """Set (or clear, with None) the registration page's auto-reply template."""
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="assign auto-reply template", required_role=_MANAGE_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if page is None:
            raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")
        if template_id is not None:
            template = uow.email_templates.get(template_id)
            if template is None or template.assembly_id != assembly_id:
                raise EmailTemplateNotFoundError(f"Email template {template_id} not found for this assembly")
            # Advisory only - never block configuring the auto-reply. The eventual
            # config UI surfaces these via auto_reply_readiness_problems().
            for problem in _auto_reply_readiness_problems(uow, assembly_id):
                logger.warning(
                    "Auto-reply readiness (%s) for assembly %s: %s",
                    problem.severity.value,
                    assembly_id,
                    problem.message,
                )
        page.set_auto_reply_template(template_id)
        uow.commit()
