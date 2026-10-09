"""ABOUTME: Service layer for rendering and sending templated emails to respondents
ABOUTME: Builds the context, sends via the adapter and writes a respondent send record"""

import uuid
from dataclasses import dataclass

import structlog

from opendlp.adapters.email import EmailAdapter
from opendlp.domain.assembly import Assembly
from opendlp.domain.email_context import (
    AssemblyContext,
    RespondentContext,
    build_context,
    sample_respondent_context,
)
from opendlp.domain.email_send_record import EmailSendOutcome, RespondentEmailSendRecord
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.respondents import Respondent

from .exceptions import (
    EmailTemplateNotFoundError,
    InsufficientPermissions,
    RegistrationPageNotFoundError,
)
from .permissions import MANAGE_ROLE, can_manage_assembly, load_user_and_assembly
from .unit_of_work import AbstractUnitOfWork

logger = structlog.get_logger(__name__)


def build_email_context(assembly: Assembly, respondent: Respondent) -> dict:
    return build_context(AssemblyContext.from_assembly(assembly), RespondentContext.from_respondent(respondent))


def _reply_to(assembly: Assembly) -> str | tuple[str, str] | None:
    if not assembly.reply_to_email:
        return None
    if assembly.reply_to_name:
        return (assembly.reply_to_name, assembly.reply_to_email)
    return assembly.reply_to_email


def _build_and_send(
    uow: AbstractUnitOfWork,
    email_adapter: EmailAdapter,
    template: EmailTemplate,
    assembly: Assembly,
    respondent: Respondent,
) -> RespondentEmailSendRecord:
    rendered = template.render(build_email_context(assembly, respondent))
    if rendered.missing_variables:
        logger.warning("Email template %s rendered with missing variables: %s", template.id, rendered.missing_variables)
    try:
        ok = email_adapter.send_email(
            to=[respondent.email],
            subject=rendered.subject,
            text_body=rendered.text_body,
            html_body=rendered.html_body,
            reply_to=_reply_to(assembly),
        )
    except Exception:
        logger.exception("Failed to send templated email for template %s", template.id)
        ok = False
    record = RespondentEmailSendRecord(
        respondent_id=respondent.id,
        email_template_id=template.id,
        to_email=respondent.email,
        from_email=assembly.reply_to_email,
        subject=rendered.subject,
        outcome=EmailSendOutcome.SENT if ok else EmailSendOutcome.FAILED,
        missing_variables=rendered.missing_variables,
    )
    uow.respondent_email_send_records.add(record)
    return record


def send_templated_email(
    uow: AbstractUnitOfWork,
    email_adapter: EmailAdapter,
    *,
    template: EmailTemplate,
    assembly: Assembly,
    respondent: Respondent,
) -> RespondentEmailSendRecord:
    """Render and send a template to a respondent, recording the outcome. Never raises on send failure.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    record = _build_and_send(uow, email_adapter, template, assembly, respondent)
    return record.create_detached_copy()


@dataclass(frozen=True)
class TestAutoReplySend:
    """Outcome of a test send: whether the adapter accepted it, and which template
    variables rendered blank (a hint the template references something that
    doesn't exist)."""

    sent: bool
    missing_variables: list[str]


@dataclass(frozen=True)
class PreparedTestAutoReply:
    """A rendered test auto-reply, ready for the email adapter.

    Produced inside the uow by prepare_test_auto_reply and consumed outside it by
    deliver_test_auto_reply, so the pooled DB connection is released before the
    SMTP round trip rather than pinned across it.
    """

    user_id: uuid.UUID
    page_id: uuid.UUID
    template_id: uuid.UUID
    to_email: str
    subject: str
    text_body: str
    html_body: str
    reply_to: str | tuple[str, str] | None
    missing_variables: list[str]


def prepare_test_auto_reply(
    uow: AbstractUnitOfWork,
    *,
    user_id: uuid.UUID,
    page_id: uuid.UUID,
    to_email: str,
) -> PreparedTestAutoReply:
    """Load and render a page's auto-reply for a test send, using a made-up respondent.

    Lets a manager see the email in a real inbox without registering. The
    respondent data is synthesised from the assembly's field schema (see
    sample_respondent_context); the assembly context is real. Does no sending and
    writes no RespondentEmailSendRecord — there is no respondent for the record to
    hang off, and test sends are not part of the delivery history.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    page = uow.registration_pages.get(page_id)
    if page is None:
        raise RegistrationPageNotFoundError(f"Registration page {page_id} not found")
    user, assembly = load_user_and_assembly(uow, user_id, page.assembly_id)
    if not can_manage_assembly(user, assembly):
        raise InsufficientPermissions(action="send test auto-reply email", required_role=MANAGE_ROLE)
    if page.auto_reply_email_template_id is None:
        raise EmailTemplateNotFoundError(f"Registration page {page.id} has no auto-reply template")
    template = uow.email_templates.get(page.auto_reply_email_template_id)
    if template is None:
        raise EmailTemplateNotFoundError(f"Email template {page.auto_reply_email_template_id} not found")

    field_definitions = uow.respondent_field_definitions.list_by_assembly(page.assembly_id)
    respondent_ctx = sample_respondent_context(field_definitions, to_email)
    rendered = template.render(build_context(AssemblyContext.from_assembly(assembly), respondent_ctx))
    return PreparedTestAutoReply(
        user_id=user_id,
        page_id=page.id,
        template_id=template.id,
        to_email=to_email,
        subject=rendered.subject,
        text_body=rendered.text_body,
        html_body=rendered.html_body,
        reply_to=_reply_to(assembly),
        missing_variables=rendered.missing_variables,
    )


def deliver_test_auto_reply(email_adapter: EmailAdapter, prepared: PreparedTestAutoReply) -> TestAutoReplySend:
    """Send an already-rendered test auto-reply. Touches no DB and never raises on send failure.

    Kept out of the uow so the pooled DB connection is not held across the SMTP
    round trip (up to the adapter's timeout) for a send that records nothing.
    """
    try:
        ok = email_adapter.send_email(
            to=[prepared.to_email],
            subject=prepared.subject,
            text_body=prepared.text_body,
            html_body=prepared.html_body,
            reply_to=prepared.reply_to,
        )
    except Exception:
        logger.exception("Failed to send test auto-reply for template %s", prepared.template_id)
        ok = False
    logger.info(
        "Test auto-reply send",
        template_id=str(prepared.template_id),
        page_id=str(prepared.page_id),
        user_id=str(prepared.user_id),
        sent=ok,
        missing_variables=prepared.missing_variables,
    )
    return TestAutoReplySend(sent=ok, missing_variables=prepared.missing_variables)


def send_test_auto_reply(
    uow: AbstractUnitOfWork,
    email_adapter: EmailAdapter,
    *,
    user_id: uuid.UUID,
    page_id: uuid.UUID,
    to_email: str,
) -> TestAutoReplySend:
    """Render and send a page's auto-reply to a manager-chosen address in one call.

    Convenience wrapper over prepare_test_auto_reply + deliver_test_auto_reply for
    callers that do not need to release the uow across the send. Entrypoints that
    want the DB connection freed during the SMTP round trip should call the two
    steps directly: render inside `with uow:`, deliver outside it.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    prepared = prepare_test_auto_reply(uow, user_id=user_id, page_id=page_id, to_email=to_email)
    return deliver_test_auto_reply(email_adapter, prepared)


def send_registration_auto_reply(
    uow: AbstractUnitOfWork,
    email_adapter: EmailAdapter,
    *,
    respondent: Respondent,
) -> RespondentEmailSendRecord | None:
    """Send the auto-reply of the page the respondent registered through.

    The template comes from that page, not the assembly: an assembly's variants
    each carry their own auto-reply, so resolving by assembly could send a
    registrant the wrong language. Returns None (no record) when skipped -
    a respondent that came from anywhere but a registration page has no
    auto-reply to send. When an auto-reply *is* configured but the respondent
    has no email address, logs a warning (a likely page misconfiguration) and
    writes no record.

    The caller is expected to manage the `uow` context (`with uow: ...`).
    """
    if respondent.registration_page_id is None:
        return None
    page = uow.registration_pages.get(respondent.registration_page_id)
    if page is None or page.auto_reply_email_template_id is None:
        return None
    if not respondent.email:
        logger.warning(
            "Auto-reply is configured for registration page %s but respondent %s has no email; skipping send",
            page.id,
            respondent.id,
        )
        return None
    template = uow.email_templates.get(page.auto_reply_email_template_id)
    assembly = uow.assemblies.get(page.assembly_id)
    if template is None or assembly is None:
        return None
    record = _build_and_send(uow, email_adapter, template, assembly, respondent)
    return record.create_detached_copy()
