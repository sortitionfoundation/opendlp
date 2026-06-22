"""ABOUTME: RespondentEmailSendRecord domain object for auditing emails to respondents
ABOUTME: Records subject, addresses, outcome and missing template variables per send"""

import uuid
from datetime import UTC, datetime
from enum import Enum


class EmailSendOutcome(Enum):
    """Outcome of an attempted email send (the initial handoff to the adapter)."""

    SENT = "SENT"
    FAILED = "FAILED"


class RespondentEmailSendRecord:
    """A record of one templated email sent (or attempted) to a respondent."""

    def __init__(
        self,
        respondent_id: uuid.UUID,
        email_template_id: uuid.UUID | None = None,
        to_email: str = "",
        from_email: str = "",
        subject: str = "",
        outcome: EmailSendOutcome = EmailSendOutcome.SENT,
        missing_variables: list[str] | None = None,
        record_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = record_id or uuid.uuid4()
        self.respondent_id = respondent_id
        self.email_template_id = email_template_id
        self.to_email = to_email
        self.from_email = from_email
        self.subject = subject
        self.outcome = outcome
        self.missing_variables = list(missing_variables) if missing_variables else []
        self.created_at = created_at or datetime.now(UTC)

    def create_detached_copy(self) -> "RespondentEmailSendRecord":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return RespondentEmailSendRecord(
            respondent_id=self.respondent_id,
            email_template_id=self.email_template_id,
            to_email=self.to_email,
            from_email=self.from_email,
            subject=self.subject,
            outcome=self.outcome,
            missing_variables=list(self.missing_variables),
            record_id=self.id,
            created_at=self.created_at,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RespondentEmailSendRecord):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
