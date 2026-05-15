"""ABOUTME: RegistrationPage domain model for assembly registration pages
ABOUTME: Holds page config plus the HTML source that supplies the registration form"""

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from opendlp.domain.validators import UrlSlugValidator

REQUIRED_TOKENS = ("csrf_form_element", "form_action")

DEFAULT_THANK_YOU_HTML = (
    "<h1>Thank you for registering</h1>\n<p>Your registration has been received. We'll be in touch.</p>\n"
)


class RegistrationPageSource(Enum):
    HTML = "html"


class RegistrationPageNotReady(Exception):
    """Raised when a registration page is not ready to be published."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class RenderContext:
    """Values substituted into the form HTML at render time."""

    csrf_form_element: str
    form_action: str


@runtime_checkable
class HtmlSource(Protocol):
    """Common interface for the source types that supply a page's form HTML."""

    def render(self, ctx: RenderContext) -> str:
        """Render the HTML from this Source, using the provided context"""
        ...

    def readiness_problems(self) -> list[str]:
        """
        Check if the source is ready to be used.
        If yes, return empty list.
        If not, return list of strings giving the problems that have to be resolved.
        """
        ...


def _validated_slug(slug: str) -> str:
    if slug:
        UrlSlugValidator().validate(slug)
    return slug


class RegistrationPage:
    """Registration page configuration for an assembly."""

    def __init__(
        self,
        assembly_id: uuid.UUID,
        url_slug: str = "",
        short_url_slug: str = "",
        is_published: bool = False,
        preview_token: str = "",
        source_type: RegistrationPageSource = RegistrationPageSource.HTML,
        thank_you_html: str = "",
        registration_page_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        now = datetime.now(UTC)
        self.id = registration_page_id or uuid.uuid4()
        self.assembly_id = assembly_id
        self.url_slug = _validated_slug(url_slug)
        self.short_url_slug = _validated_slug(short_url_slug)
        self.is_published = is_published
        self.preview_token = preview_token or secrets.token_urlsafe(32)
        self.source_type = source_type
        self.thank_you_html = thank_you_html
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def update_slugs(self, url_slug: str | None = None, short_url_slug: str | None = None) -> None:
        """Update the URL slugs. Raises if the page is published (slugs are frozen)."""
        if self.is_published:
            raise ValueError("Cannot change slugs while the registration page is published")
        if url_slug is not None:
            self.url_slug = _validated_slug(url_slug)
        if short_url_slug is not None:
            self.short_url_slug = _validated_slug(short_url_slug)
        self.updated_at = datetime.now(UTC)

    def update_thank_you_html(self, thank_you_html: str) -> None:
        self.thank_you_html = thank_you_html
        self.updated_at = datetime.now(UTC)

    def readiness_problems(self, source: HtmlSource) -> list[str]:
        """Human-readable reasons the (page, source) combo is not publishable."""
        problems: list[str] = []
        if not self.url_slug:
            problems.append("The registration page needs a URL slug before it can be published")
        problems.extend(source.readiness_problems())
        return problems

    def publish(self, source: HtmlSource) -> None:
        problems = self.readiness_problems(source)
        if problems:
            raise RegistrationPageNotReady(problems)
        self.is_published = True
        self.updated_at = datetime.now(UTC)

    def unpublish(self) -> None:
        self.is_published = False
        self.updated_at = datetime.now(UTC)

    def regenerate_preview_token(self) -> None:
        self.preview_token = secrets.token_urlsafe(32)
        self.updated_at = datetime.now(UTC)

    def is_visible_with(self, token: str = "") -> bool:
        """True if the page is published, or the token matches the preview token."""
        if self.is_published:
            return True
        return bool(token) and token == self.preview_token

    def create_detached_copy(self) -> "RegistrationPage":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return RegistrationPage(
            assembly_id=self.assembly_id,
            url_slug=self.url_slug,
            short_url_slug=self.short_url_slug,
            is_published=self.is_published,
            preview_token=self.preview_token,
            source_type=self.source_type,
            thank_you_html=self.thank_you_html,
            registration_page_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RegistrationPage):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


class RegistrationPageHtml:
    """The HTML source-of-truth when RegistrationPage.source_type == HTML."""

    def __init__(
        self,
        registration_page_id: uuid.UUID,
        form_html: str = "",
        html_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        now = datetime.now(UTC)
        self.id = html_id or uuid.uuid4()
        self.registration_page_id = registration_page_id
        self.form_html = form_html
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def update_html(self, form_html: str) -> None:
        self.form_html = form_html
        self.updated_at = datetime.now(UTC)

    def render(self, ctx: RenderContext) -> str:
        rendered = self.form_html.replace("{{ csrf_form_element }}", ctx.csrf_form_element)
        return rendered.replace("{{ form_action }}", ctx.form_action)

    def readiness_problems(self) -> list[str]:
        if not self.form_html.strip():
            return ["The form HTML is empty"]
        problems: list[str] = []
        for token in REQUIRED_TOKENS:
            if f"{{{{ {token} }}}}" not in self.form_html:
                problems.append(f"The form HTML is missing the {{{{ {token} }}}} placeholder")
        return problems

    def create_detached_copy(self) -> "RegistrationPageHtml":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return RegistrationPageHtml(
            registration_page_id=self.registration_page_id,
            form_html=self.form_html,
            html_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RegistrationPageHtml):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)
