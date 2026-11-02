"""ABOUTME: Integration tests that the email template's reply-to and the send record's reply-to persist
ABOUTME: Reads back in a fresh UnitOfWork, so the values must come from the database, not the identity map"""

import uuid

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_send_record import EmailSendOutcome, RespondentEmailSendRecord
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.respondents import Respondent
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


def test_email_template_reply_to_round_trips(postgres_session_factory):
    assembly = Assembly(title="Climate Assembly")
    template = EmailTemplate(
        assembly_id=assembly.id,
        name="Reply",
        subject="Thanks",
        body_html="<p>Thanks</p>",
        reply_to_name="The Team",
        reply_to_email="team@example.com",
    )
    template_id = template.id
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.assemblies.add(assembly)
        uow.email_templates.add(template)
        uow.commit()

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        retrieved = uow.email_templates.get(template_id)
        assert retrieved is not None
        assert retrieved.reply_to_name == "The Team"
        assert retrieved.reply_to_email == "team@example.com"


def test_send_record_reply_to_email_round_trips(postgres_session_factory):
    assembly = Assembly(title="Climate Assembly")
    respondent = Respondent(assembly_id=assembly.id, external_id=f"ext-{uuid.uuid4()}", email="ada@example.com")
    record = RespondentEmailSendRecord(
        respondent_id=respondent.id,
        to_email="ada@example.com",
        reply_to_email="team@example.com",
        subject="Thanks",
        outcome=EmailSendOutcome.SENT,
    )
    record_id = record.id
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        uow.assemblies.add(assembly)
        uow.respondents.add(respondent)
        uow.commit()
        uow.respondent_email_send_records.add(record)
        uow.commit()

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        retrieved = uow.respondent_email_send_records.get(record_id)
        assert retrieved is not None
        assert retrieved.reply_to_email == "team@example.com"
