"""ABOUTME: EmailTemplate domain model for database-stored, Jinja-rendered emails
ABOUTME: Authors write a subject + HTML body; the text/plain body is derived from the HTML"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from jinja2 import TemplateSyntaxError, Undefined
from jinja2.sandbox import SandboxedEnvironment

from opendlp.domain.html_to_text import html_to_text

# Two sandboxed environments share the same lenient ``Undefined`` policy:
# a missing context variable renders as an empty string rather than raising.
# Email authors routinely reference optional respondent attributes that may be
# blank for a given person, and a single missing value must never cause a send
# to fail. Author mistakes are instead surfaced by previewing against
# ``sample_context()`` and by the save-time syntax check in
# ``validation_problems()``.
#
# The HTML environment autoescapes (values are interpolated into HTML); the
# subject environment does not, because the subject is a plain-text header and
# escaping ``&`` -> ``&amp;`` there would be wrong.
_HTML_ENV = SandboxedEnvironment(autoescape=True, undefined=Undefined)
_SUBJECT_ENV = SandboxedEnvironment(autoescape=False, undefined=Undefined)  # noqa: S701


@dataclass(frozen=True)
class AssemblyContext:
    """Assembly-derived values exposed to a template as ``{{ assembly.* }}``.

    ``first_assembly_date`` is an ISO-8601 string (or ``""``) so authors can
    print it directly without a ``None`` leaking into the output.
    ``info_url`` is a documented placeholder: Assembly has no info URL field
    yet, so it renders empty until one is added.
    """

    title: str = ""
    question: str = ""
    info_url: str = ""
    first_assembly_date: str = ""
    number_to_select: int = 0


@dataclass(frozen=True)
class RespondentContext:
    """Respondent-derived values exposed to a template as ``{{ respondent.* }}``.

    ``attributes`` is the respondent's submitted form data keyed by field key,
    so an author can reference any assembly-specific field via
    ``{{ respondent.attributes.fieldkey }}``; a missing key renders empty.
    """

    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    email: str = ""
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RenderedEmail:
    """The fully rendered output ready to hand to an ``EmailAdapter``."""

    subject: str
    html_body: str
    text_body: str


class EmailTemplate:
    """A reusable, database-stored email template scoped to an assembly.

    The author supplies a ``subject`` and an HTML ``body_html``; both are Jinja
    templates rendered against a documented context (see ``AssemblyContext`` and
    ``RespondentContext``). The plain-text alternative is derived from the
    rendered HTML rather than authored separately.
    """

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
        self.name = name.strip()
        self.subject = subject
        self.body_html = body_html
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def update(
        self,
        *,
        name: str | None = None,
        subject: str | None = None,
        body_html: str | None = None,
    ) -> None:
        """Update the supplied fields. Passing ``None`` leaves a field unchanged."""
        if name is not None:
            self.name = name.strip()
        if subject is not None:
            self.subject = subject
        if body_html is not None:
            self.body_html = body_html
        self.updated_at = datetime.now(UTC)

    def validation_problems(self) -> list[str]:
        """Human-readable reasons this template is not ready to be sent.

        Checks that the name, subject and body are present and that the subject
        and body are syntactically valid Jinja. Undefined variables are not
        flagged here: the respondent attribute set is assembly-specific and
        dynamic, so unknown names are tolerated at render time.
        """
        problems: list[str] = []
        if not self.name.strip():
            problems.append("The template needs a name")
        if not self.subject.strip():
            problems.append("The email subject is empty")
        if not self.body_html.strip():
            problems.append("The email body is empty")
        problems.extend(self._syntax_problem(_SUBJECT_ENV, self.subject, "subject"))
        problems.extend(self._syntax_problem(_HTML_ENV, self.body_html, "body"))
        return problems

    @staticmethod
    def _syntax_problem(env: SandboxedEnvironment, source: str, label: str) -> list[str]:
        if not source.strip():
            return []
        try:
            env.parse(source)
        except TemplateSyntaxError as e:
            return [f"The email {label} has a template syntax error on line {e.lineno}: {e.message}"]
        return []

    def render(self, context: Mapping[str, Any]) -> RenderedEmail:
        """Render the subject and body against ``context`` and derive the text body.

        The subject is flattened to a single line. The text/plain body is
        generated from the rendered HTML so authors maintain only one body.
        """
        subject = _SUBJECT_ENV.from_string(self.subject).render(**context)
        subject = " ".join(subject.split())
        html_body = _HTML_ENV.from_string(self.body_html).render(**context)
        text_body = html_to_text(html_body)
        return RenderedEmail(subject=subject, html_body=html_body, text_body=text_body)

    @classmethod
    def sample_context(cls) -> dict[str, Any]:
        """Placeholder context for previewing a template in the editor.

        Mirrors the real context shape with illustrative values so an author can
        see roughly how a rendered email will look before any respondent exists.
        """
        return {
            "assembly": AssemblyContext(
                title="Sheffield Climate Assembly",
                question="How should Sheffield reach net zero by 2030?",
                info_url="https://example.org/assembly",
                first_assembly_date="2026-09-01",
                number_to_select=50,
            ),
            "respondent": RespondentContext(
                first_name="Alex",
                last_name="Taylor",
                full_name="Alex Taylor",
                email="alex.taylor@example.com",
                attributes={"first_name": "Alex", "last_name": "Taylor", "postcode": "S1 2AB"},
            ),
        }

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
