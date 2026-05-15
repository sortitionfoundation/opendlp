"""ABOUTME: RegistrationPage domain model for assembly registration pages
ABOUTME: Holds page config plus the HTML source that supplies the registration form"""

import html as html_lib
import secrets
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Protocol, runtime_checkable

from opendlp.domain.respondent_field_schema import (
    BOOL_TYPES,
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.validators import InvalidSlug, SlugError, UrlSlugValidator

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


def _validated_slug(slug: str, field: str) -> str:
    if slug:
        try:
            UrlSlugValidator().validate(slug)
        except InvalidSlug as e:
            raise SlugError(field=field, reason=e.reason, message=str(e)) from e
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
        self.url_slug = _validated_slug(url_slug, field="url_slug")
        self.short_url_slug = _validated_slug(short_url_slug, field="short_url_slug")
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
            self.url_slug = _validated_slug(url_slug, field="url_slug")
        if short_url_slug is not None:
            self.short_url_slug = _validated_slug(short_url_slug, field="short_url_slug")
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


def _render_input(field: RespondentFieldDefinition, input_type: str, required_attr: str) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    label = html_lib.escape(field.label)
    return [
        f'<label for="{key}">{label}</label>',
        f'<input type="{input_type}" id="{key}" name="{key}"{required_attr}>',
    ]


def _render_textarea(field: RespondentFieldDefinition, required_attr: str) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    label = html_lib.escape(field.label)
    return [
        f'<label for="{key}">{label}</label>',
        f'<textarea id="{key}" name="{key}"{required_attr}></textarea>',
    ]


def _render_yes_no_radios(field: RespondentFieldDefinition) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    legend = html_lib.escape(field.label)
    return [
        "<fieldset>",
        f"<legend>{legend}</legend>",
        f'<label><input type="radio" name="{key}" value="yes"> Yes</label>',
        f'<label><input type="radio" name="{key}" value="no"> No</label>',
        "</fieldset>",
    ]


def _render_choice_radios(field: RespondentFieldDefinition) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    legend = html_lib.escape(field.label)
    parts = ["<fieldset>", f"<legend>{legend}</legend>"]
    for opt in field.options or []:
        value = html_lib.escape(opt.value, quote=True)
        text = html_lib.escape(opt.value)
        parts.append(f'<label><input type="radio" name="{key}" value="{value}"> {text}</label>')
    parts.append("</fieldset>")
    return parts


def _render_choice_dropdown(field: RespondentFieldDefinition, is_required: bool) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    label = html_lib.escape(field.label)
    required_attr = " required" if is_required else ""
    parts = [
        f'<label for="{key}">{label}</label>',
        f'<select id="{key}" name="{key}"{required_attr}>',
    ]
    if not is_required:
        parts.append('<option value="">— Please choose —</option>')
    for opt in field.options or []:
        value = html_lib.escape(opt.value, quote=True)
        text = html_lib.escape(opt.value)
        parts.append(f'<option value="{value}">{text}</option>')
    parts.append("</select>")
    return parts


def _render_field(field: RespondentFieldDefinition, required_field_keys: Iterable[str]) -> list[str]:
    is_required = field.field_key in required_field_keys
    required_attr = " required" if is_required else ""
    field_type = field.effective_field_type

    if field_type == FieldType.TEXT:
        return _render_input(field, "text", required_attr)
    if field_type == FieldType.EMAIL:
        return _render_input(field, "email", required_attr)
    if field_type == FieldType.INTEGER:
        return _render_input(field, "number", required_attr)
    if field_type == FieldType.LONGTEXT:
        return _render_textarea(field, required_attr)
    if field_type in BOOL_TYPES:
        return _render_yes_no_radios(field)
    if field_type == FieldType.CHOICE_RADIO:
        return _render_choice_radios(field)
    if field_type == FieldType.CHOICE_DROPDOWN:
        return _render_choice_dropdown(field, is_required)
    return _render_input(field, "text", required_attr)


def _group_fields(
    fields: list[RespondentFieldDefinition],
) -> dict[RespondentFieldGroup, list[RespondentFieldDefinition]]:
    grouped: dict[RespondentFieldGroup, list[RespondentFieldDefinition]] = {g: [] for g in GROUP_DISPLAY_ORDER}
    for f in fields:
        grouped.setdefault(f.group, []).append(f)
    for bucket in grouped.values():
        bucket.sort(key=lambda f: f.sort_order)
    return grouped


def generate_starter_form_html(
    fields: list[RespondentFieldDefinition],
    required_field_keys: Iterable[str] = (),
) -> str:
    """Generate an unstyled starter HTML form from a respondent field schema.

    Output uses ``{{ csrf_form_element }}`` and ``{{ form_action }}`` so it is
    a valid input for ``RegistrationPageHtml.render``. Fields are grouped by
    ``RespondentFieldGroup`` in ``GROUP_DISPLAY_ORDER`` and ordered by
    ``sort_order`` within each group; empty groups are suppressed.
    """
    required_set = set(required_field_keys)
    grouped = _group_fields(fields)

    parts: list[str] = ['<form action="{{ form_action }}" method="post">', "{{ csrf_form_element }}"]
    for group in GROUP_DISPLAY_ORDER:
        bucket = grouped.get(group, [])
        if not bucket:
            continue
        parts.append(f"<h2>{html_lib.escape(str(GROUP_LABELS[group]))}</h2>")
        for field in bucket:
            parts.extend(_render_field(field, required_set))
    parts.append('<button type="submit">Register</button>')
    parts.append("</form>")
    return "\n".join(parts) + "\n"
