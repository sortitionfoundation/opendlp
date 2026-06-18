"""ABOUTME: Service layer for rendering and sending templated emails to respondents
ABOUTME: Builds the context, sends via the adapter and writes a respondent send record"""

import logging
import uuid

from opendlp.adapters.email import EmailAdapter
from opendlp.domain.assembly import Assembly
from opendlp.domain.email_context import AssemblyContext, RespondentContext, build_context
from opendlp.domain.email_send_record import EmailSendOutcome, RespondentEmailSendRecord
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.respondents import Respondent

from .unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)


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
    """Render and send a template to a respondent, recording the outcome. Never raises on send failure."""
    with uow:
        record = _build_and_send(uow, email_adapter, template, assembly, respondent)
        uow.commit()
        return record.create_detached_copy()


def send_registration_auto_reply(
    uow: AbstractUnitOfWork,
    email_adapter: EmailAdapter,
    *,
    respondent: Respondent,
    assembly_id: uuid.UUID,
) -> RespondentEmailSendRecord | None:
    """Send the registration auto-reply if configured. Returns None (no record) when skipped.

    Skips silently when no auto-reply is configured. When an auto-reply *is*
    configured but the respondent has no email address, logs a warning (a likely
    page misconfiguration) and writes no record.
    """
    with uow:
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if page is None or page.auto_reply_email_template_id is None:
            return None
        if not respondent.email:
            logger.warning(
                "Auto-reply is configured for assembly %s but respondent %s has no email; skipping send",
                assembly_id,
                respondent.id,
            )
            return None
        template = uow.email_templates.get(page.auto_reply_email_template_id)
        assembly = uow.assemblies.get(assembly_id)
        if template is None or assembly is None:
            return None
        record = _build_and_send(uow, email_adapter, template, assembly, respondent)
        uow.commit()
        return record.create_detached_copy()
