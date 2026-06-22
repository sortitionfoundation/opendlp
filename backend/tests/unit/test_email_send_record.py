"""ABOUTME: Unit tests for the RespondentEmailSendRecord domain object
ABOUTME: Covers construction defaults and detached copies"""

import uuid

from opendlp.domain.email_send_record import EmailSendOutcome, RespondentEmailSendRecord


def test_construction_defaults() -> None:
    respondent_id = uuid.uuid4()
    record = RespondentEmailSendRecord(
        respondent_id=respondent_id,
        to_email="person@example.com",
        from_email="team@example.com",
        subject="Thanks",
        outcome=EmailSendOutcome.SENT,
    )
    assert record.respondent_id == respondent_id
    assert record.outcome == EmailSendOutcome.SENT
    assert record.missing_variables == []
    assert record.email_template_id is None
    assert record.id is not None


def test_records_missing_variables_and_template() -> None:
    template_id = uuid.uuid4()
    record = RespondentEmailSendRecord(
        respondent_id=uuid.uuid4(),
        email_template_id=template_id,
        outcome=EmailSendOutcome.FAILED,
        missing_variables=["first_name"],
    )
    assert record.email_template_id == template_id
    assert record.outcome == EmailSendOutcome.FAILED
    assert record.missing_variables == ["first_name"]


def test_create_detached_copy_preserves_identity() -> None:
    record = RespondentEmailSendRecord(respondent_id=uuid.uuid4(), missing_variables=["x"])
    copy = record.create_detached_copy()
    assert copy is not record
    assert copy == record
    assert copy.id == record.id
    assert copy.missing_variables == ["x"]
    assert copy.missing_variables is not record.missing_variables
