"""ABOUTME: EmailTemplate domain aggregate for database-stored templated emails
ABOUTME: Holds subject, HTML body and reply-to; renders against a context and validates itself"""

import unicodedata
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from opendlp.domain.email_template_render import (
    RenderedEmail,
    render_template_string,
    template_syntax_problems,
)
from opendlp.domain.validators import validate_email
from opendlp.translations import gettext as _

__all__ = ["EmailTemplate", "RenderedEmail", "ReplyTo", "reply_to_address"]

ReplyTo = str | tuple[str, str] | None

REPLY_TO_MAX_LENGTH = 255

_LINE_SEPARATORS = ("\u2028", "\u2029")


def reply_to_address(name: str, email: str) -> ReplyTo:
    """The Reply-To value for the email adapter: (name, email), a bare email, or None."""
    if not email:
        return None
    if name:
        return (name, email)
    return email


def _has_control_character(text: str) -> bool:
    return any(unicodedata.category(char) == "Cc" or char in _LINE_SEPARATORS for char in text)


def _reply_to_problems(name: str, email: str) -> list[str]:
    problems: list[str] = []
    if _has_control_character(name):
        problems.append(_("The name for replies cannot contain line breaks or other control characters"))
    if len(name) > REPLY_TO_MAX_LENGTH:
        problems.append(_("The name for replies must be at most %(max)s characters", max=REPLY_TO_MAX_LENGTH))
    if len(email) > REPLY_TO_MAX_LENGTH:
        problems.append(_("The email address for replies must be at most %(max)s characters", max=REPLY_TO_MAX_LENGTH))
    elif email:
        try:
            validate_email(email)
        except ValueError:
            problems.append(_("The email address for replies is not valid"))
    return problems


class EmailTemplate:
    """An assembly-scoped email template with a Jinja subject and HTML body."""

    def __init__(
        self,
        assembly_id: uuid.UUID,
        name: str = "",
        subject: str = "",
        body_html: str = "",
        reply_to_name: str = "",
        reply_to_email: str = "",
        email_template_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        now = datetime.now(UTC)
        self.id = email_template_id or uuid.uuid4()
        self.assembly_id = assembly_id
        self.name = name
        self.subject = subject
        self.body_html = body_html
        self.reply_to_name = reply_to_name.strip()
        self.reply_to_email = reply_to_email.strip()
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def render(self, context: Mapping[str, Any]) -> RenderedEmail:
        return render_template_string(self.subject, self.body_html, context)

    def reply_to(self) -> ReplyTo:
        return reply_to_address(self.reply_to_name, self.reply_to_email)

    def validation_problems(self) -> list[str]:
        problems: list[str] = []
        if not self.name.strip():
            problems.append(_("The email template needs a name"))
        if not self.subject.strip():
            problems.append(_("The email template needs a subject"))
        if not self.body_html.strip():
            problems.append(_("The email template body is empty"))
        problems.extend(template_syntax_problems(self.subject, self.body_html))
        problems.extend(_reply_to_problems(self.reply_to_name, self.reply_to_email))
        return problems

    def update(
        self,
        name: str | None = None,
        subject: str | None = None,
        body_html: str | None = None,
        reply_to_name: str | None = None,
        reply_to_email: str | None = None,
    ) -> None:
        if name is not None:
            self.name = name
        if subject is not None:
            self.subject = subject
        if body_html is not None:
            self.body_html = body_html
        if reply_to_name is not None:
            self.reply_to_name = reply_to_name.strip()
        if reply_to_email is not None:
            self.reply_to_email = reply_to_email.strip()
        self.updated_at = datetime.now(UTC)

    def create_detached_copy(self) -> "EmailTemplate":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return EmailTemplate(
            assembly_id=self.assembly_id,
            name=self.name,
            subject=self.subject,
            body_html=self.body_html,
            reply_to_name=self.reply_to_name,
            reply_to_email=self.reply_to_email,
            email_template_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, EmailTemplate):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
