"""ABOUTME: EmailTemplate domain aggregate for database-stored templated emails
ABOUTME: Holds subject and HTML body, renders against a context and validates itself"""

import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from opendlp.domain.email_context import sample_context
from opendlp.domain.email_template_render import (
    RenderedEmail,
    render_template_string,
    template_syntax_problems,
)

__all__ = ["EmailTemplate", "RenderedEmail"]


class EmailTemplate:
    """An assembly-scoped email template with a Jinja subject and HTML body."""

    def __init__(
        self,
        assembly_id: uuid.UUID,
        name: str = "",
        subject: str = "",
        body_html: str = "",
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
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def render(self, context: Mapping[str, Any]) -> RenderedEmail:
        return render_template_string(self.subject, self.body_html, context)

    def validation_problems(self) -> list[str]:
        problems: list[str] = []
        if not self.name.strip():
            problems.append("The email template needs a name")
        if not self.subject.strip():
            problems.append("The email template needs a subject")
        if not self.body_html.strip():
            problems.append("The email template body is empty")
        problems.extend(template_syntax_problems(self.subject, self.body_html))
        return problems

    def sample_context(self) -> dict[str, Any]:
        return sample_context()

    def update(self, name: str | None = None, subject: str | None = None, body_html: str | None = None) -> None:
        if name is not None:
            self.name = name
        if subject is not None:
            self.subject = subject
        if body_html is not None:
            self.body_html = body_html
        self.updated_at = datetime.now(UTC)

    def create_detached_copy(self) -> "EmailTemplate":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return EmailTemplate(
            assembly_id=self.assembly_id,
            name=self.name,
            subject=self.subject,
            body_html=self.body_html,
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
