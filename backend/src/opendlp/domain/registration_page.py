"""ABOUTME: RegistrationPage domain model for assembly registration pages
ABOUTME: Holds page config plus the HTML source that supplies the registration form"""

import html as html_lib
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from jinja2 import StrictUndefined, TemplateSyntaxError, meta
from jinja2.sandbox import SandboxedEnvironment
from markupsafe import Markup

from opendlp.domain.respondent_field_schema import (
    BOOL_TYPES,
    GROUP_DISPLAY_ORDER,
    GROUP_LABELS,
    FieldOnRegistrationPage,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.validators import InvalidSlug, SlugError, UrlSlugValidator

_SANDBOX_ENV = SandboxedEnvironment(autoescape=True, undefined=StrictUndefined)

REQUIRED_TOKENS = ("csrf_form_element", "form_action")

DEFAULT_THANK_YOU_HTML = """\
<div class="govuk-grid-row">
    <div class="govuk-grid-column-two-thirds" style="float: none; margin: 0 auto;">
        <div class="govuk-panel govuk-panel--confirmation">
            <h1 class="govuk-panel__title">Thank you for registering</h1>
            <div class="govuk-panel__body">Your registration has been received</div>
        </div>
        <p class="govuk-body">We'll be in touch.</p>
    </div>
</div>
"""


class RegistrationPageSource(Enum):
    HTML = "html"


class RegistrationPageStatus(Enum):
    """Lifecycle state of a RegistrationPage.

    TEST loads publicly at the page slug; submissions are recorded as test
    submissions. PUBLISHED is live; submissions go into the selection pool.
    CLOSED redirects visitors to the registration-closed page.
    """

    TEST = "TEST"
    PUBLISHED = "PUBLISHED"
    CLOSED = "CLOSED"


class RegistrationPageAction(Enum):
    """Type of action a RegistrationPageActivity records."""

    CREATE = "CREATE"
    EDIT = "EDIT"
    PUBLISH = "PUBLISH"
    UNPUBLISH = "UNPUBLISH"
    CLOSE = "CLOSE"
    REOPEN = "REOPEN"


class RegistrationPageNotReady(Exception):
    """Raised when a registration page is not ready to be published."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class RegistrationPageActivity:
    """A timestamped entry in a RegistrationPage's audit log."""

    text: str
    author_id: uuid.UUID
    created_at: datetime
    action: RegistrationPageAction = RegistrationPageAction.EDIT

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "author_id": str(self.author_id),
            "created_at": self.created_at.isoformat(),
            "action": self.action.value,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RegistrationPageActivity":
        try:
            action = RegistrationPageAction(data.get("action", RegistrationPageAction.EDIT.value))
        except ValueError:
            action = RegistrationPageAction.EDIT
        return cls(
            text=data["text"],
            author_id=uuid.UUID(data["author_id"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            action=action,
        )


@dataclass(frozen=True)
class RenderContext:
    """Values substituted into the form HTML at render time.

    ``csrf_form_element`` and ``form_action`` are always populated.
    ``assembly_title`` and ``assembly_question`` are optional copy that
    authors can drop into their HTML via ``{{ assembly_title }}`` and
    ``{{ assembly_question }}``; they default to empty so callers that
    don't have an Assembly handy can omit them. The remaining fields
    carry validation state from a failed POST: ``values`` pre-fills
    field inputs, ``errors`` maps field keys to per-field error
    messages, and ``form_level_errors`` holds cross-field messages
    shown via the ``form_errors()`` helper.
    """

    csrf_form_element: str
    form_action: str
    assembly_title: str = ""
    assembly_question: str = ""
    values: dict[str, str] = field(default_factory=dict)
    errors: dict[str, list[str]] = field(default_factory=dict)
    form_level_errors: list[str] = field(default_factory=list)


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
        status: RegistrationPageStatus = RegistrationPageStatus.TEST,
        source_type: RegistrationPageSource = RegistrationPageSource.HTML,
        thank_you_html: str = "",
        activity: list[RegistrationPageActivity] | None = None,
        registration_page_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        auto_reply_email_template_id: uuid.UUID | None = None,
    ):
        now = datetime.now(UTC)
        self.id = registration_page_id or uuid.uuid4()
        self.assembly_id = assembly_id
        self.url_slug = _validated_slug(url_slug, field="url_slug")
        self.short_url_slug = _validated_slug(short_url_slug, field="short_url_slug")
        self.status = status
        self.source_type = source_type
        self.thank_you_html = thank_you_html
        self.auto_reply_email_template_id = auto_reply_email_template_id
        self.activity: list[RegistrationPageActivity] = list(activity) if activity else []
        self.created_at = created_at or now
        self.updated_at = updated_at or now

    def has_ever_been_published(self) -> bool:
        return any(a.action == RegistrationPageAction.PUBLISH for a in self.activity)

    @property
    def slugs_frozen(self) -> bool:
        """Slugs are editable only while in TEST. PUBLISHED locks live URLs;
        CLOSED stays locked because invites and QR codes from the published
        period are still in the world and the closed-page redirect needs
        the original slug to keep working."""
        return self.status != RegistrationPageStatus.TEST

    def update_slugs(self, url_slug: str | None = None, short_url_slug: str | None = None) -> None:
        """Update the URL slugs. Raises while the page is published or closed."""
        if self.slugs_frozen:
            raise ValueError("Cannot change slugs while the registration page is published or closed")
        if url_slug is not None:
            self.url_slug = _validated_slug(url_slug, field="url_slug")
        if short_url_slug is not None:
            self.short_url_slug = _validated_slug(short_url_slug, field="short_url_slug")
        self.updated_at = datetime.now(UTC)

    def update_thank_you_html(self, thank_you_html: str) -> None:
        self.thank_you_html = thank_you_html
        self.updated_at = datetime.now(UTC)

    def set_auto_reply_template(self, template_id: uuid.UUID | None) -> None:
        self.auto_reply_email_template_id = template_id
        self.updated_at = datetime.now(UTC)

    def readiness_problems(self, source: HtmlSource) -> list[str]:
        """Human-readable reasons the (page, source) combo is not publishable."""
        problems: list[str] = []
        if not self.url_slug:
            problems.append("The registration page needs a URL slug before it can be published")
        problems.extend(source.readiness_problems())
        return problems

    def _append_activity(self, action: RegistrationPageAction, author_id: uuid.UUID, text: str) -> None:
        now = datetime.now(UTC)
        entry = RegistrationPageActivity(text=text, author_id=author_id, created_at=now, action=action)
        self.activity = [*self.activity, entry]
        self.updated_at = now

    def record_create(self, author_id: uuid.UUID) -> None:
        self._append_activity(RegistrationPageAction.CREATE, author_id, "Registration page created")

    def record_edit(self, author_id: uuid.UUID, text: str) -> None:
        self._append_activity(RegistrationPageAction.EDIT, author_id, text)

    def publish(self, source: HtmlSource, author_id: uuid.UUID, text: str = "") -> None:
        if self.status != RegistrationPageStatus.TEST:
            raise ValueError(f"Cannot publish a registration page in status {self.status.value}")
        problems = self.readiness_problems(source)
        if problems:
            raise RegistrationPageNotReady(problems)
        self.status = RegistrationPageStatus.PUBLISHED
        self._append_activity(RegistrationPageAction.PUBLISH, author_id, text)

    def unpublish(self, author_id: uuid.UUID, text: str = "") -> None:
        if self.status != RegistrationPageStatus.PUBLISHED:
            raise ValueError(f"Cannot unpublish a registration page in status {self.status.value}")
        self.status = RegistrationPageStatus.TEST
        self._append_activity(RegistrationPageAction.UNPUBLISH, author_id, text)

    def close(self, author_id: uuid.UUID, text: str = "") -> None:
        if self.status != RegistrationPageStatus.PUBLISHED:
            raise ValueError(f"Cannot close a registration page in status {self.status.value}")
        self.status = RegistrationPageStatus.CLOSED
        self._append_activity(RegistrationPageAction.CLOSE, author_id, text)

    def reopen(self, source: HtmlSource, author_id: uuid.UUID, text: str = "") -> None:
        if self.status != RegistrationPageStatus.CLOSED:
            raise ValueError(f"Cannot reopen a registration page in status {self.status.value}")
        problems = self.readiness_problems(source)
        if problems:
            raise RegistrationPageNotReady(problems)
        self.status = RegistrationPageStatus.PUBLISHED
        self._append_activity(RegistrationPageAction.REOPEN, author_id, text)

    def is_publicly_loadable(self) -> bool:
        """True if the form should render at the public slug.

        Requires a non-empty ``url_slug`` (a slugless page has no canonical URL
        to render at) and a status of TEST or PUBLISHED. CLOSED redirects
        visitors to the registration-closed page, so it never renders the form.
        """
        if not self.url_slug:
            return False
        return self.status in (RegistrationPageStatus.TEST, RegistrationPageStatus.PUBLISHED)

    def create_detached_copy(self) -> "RegistrationPage":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return RegistrationPage(
            assembly_id=self.assembly_id,
            url_slug=self.url_slug,
            short_url_slug=self.short_url_slug,
            status=self.status,
            source_type=self.source_type,
            thank_you_html=self.thank_you_html,
            activity=list(self.activity),
            registration_page_id=self.id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            auto_reply_email_template_id=self.auto_reply_email_template_id,
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
        template = _SANDBOX_ENV.from_string(self.form_html)
        # csrf_form_element is the hidden <input> built by Flask-WTF (or its
        # CSRF middleware), never user-supplied; wrapping it in Markup so
        # autoescape doesn't escape the angle brackets is safe.
        return template.render(
            csrf_form_element=Markup(ctx.csrf_form_element),  # noqa: S704
            form_action=ctx.form_action,
            assembly_title=ctx.assembly_title,
            assembly_question=ctx.assembly_question,
            value=lambda k: ctx.values.get(k, ""),
            checked=lambda k, v: "checked" if ctx.values.get(k) == v else "",
            selected=lambda k, v: "selected" if ctx.values.get(k) == v else "",
            field_errors=lambda k: _field_errors_html(ctx.errors.get(k, [])),
            has_error=lambda k: bool(ctx.errors.get(k)),
            first_error=lambda k: (ctx.errors.get(k) or [""])[0],
            form_errors=lambda: _form_errors_html(ctx.form_level_errors),
        )

    def readiness_problems(self) -> list[str]:
        if not self.form_html.strip():
            return ["The form HTML is empty"]
        try:
            parsed = _SANDBOX_ENV.parse(self.form_html)
        except TemplateSyntaxError as e:
            return [f"The form HTML has a template syntax error on line {e.lineno}: {e.message}"]
        referenced = meta.find_undeclared_variables(parsed)
        problems: list[str] = []
        for token in REQUIRED_TOKENS:
            if token not in referenced:
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


def _field_errors_html(errors: list[str]) -> Markup:
    if not errors:
        return Markup("")
    parts = [Markup('<p class="error">{}</p>').format(msg) for msg in errors]
    return Markup("\n").join(parts)


def _form_errors_html(errors: list[str]) -> Markup:
    if not errors:
        return Markup("")
    items = Markup("").join(Markup("<li>{}</li>").format(msg) for msg in errors)
    return Markup('<ul class="form-errors">{}</ul>').format(items)


def _jinja_str(value: str) -> str:
    # Escape a Python string for embedding inside a single-quoted Jinja string
    # literal. The pair backslash-then-quote in the rendered template lets the
    # Jinja parser see a single literal quote inside the string.
    return value.replace("\\", r"\\").replace("'", r"\'")


def _jinja_call(fn: str, *args: str) -> str:
    quoted = ", ".join(f"'{_jinja_str(a)}'" for a in args)
    return f"{{{{ {fn}({quoted}) }}}}"


def _render_input(field: RespondentFieldDefinition, input_type: str, required_attr: str) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    label = html_lib.escape(field.label)
    value_expr = _jinja_call("value", field.field_key)
    return [
        f'<label for="{key}">{label}</label>',
        f'<input type="{input_type}" id="{key}" name="{key}" value="{value_expr}"{required_attr}>',
        _jinja_call("field_errors", field.field_key),
    ]


def _render_textarea(field: RespondentFieldDefinition, required_attr: str) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    label = html_lib.escape(field.label)
    value_expr = _jinja_call("value", field.field_key)
    return [
        f'<label for="{key}">{label}</label>',
        f'<textarea id="{key}" name="{key}"{required_attr}>{value_expr}</textarea>',
        _jinja_call("field_errors", field.field_key),
    ]


def _render_checkbox(field: RespondentFieldDefinition, required_attr: str) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    label = html_lib.escape(field.label)
    checked_expr = _jinja_call("checked", field.field_key, "yes")
    return [
        f'<label><input type="checkbox" id="{key}" name="{key}" value="yes" {checked_expr}{required_attr}> {label}</label>',
        _jinja_call("field_errors", field.field_key),
    ]


def _render_choice_radios(field: RespondentFieldDefinition) -> list[str]:
    key = html_lib.escape(field.field_key, quote=True)
    legend = html_lib.escape(field.label)
    parts = ["<fieldset>", f"<legend>{legend}</legend>"]
    for opt in field.options or []:
        value_attr = html_lib.escape(opt.value, quote=True)
        text = html_lib.escape(opt.value)
        checked_expr = _jinja_call("checked", field.field_key, opt.value)
        parts.append(f'<label><input type="radio" name="{key}" value="{value_attr}" {checked_expr}> {text}</label>')
    parts.append(_jinja_call("field_errors", field.field_key))
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
        value_attr = html_lib.escape(opt.value, quote=True)
        text = html_lib.escape(opt.value)
        selected_expr = _jinja_call("selected", field.field_key, opt.value)
        parts.append(f'<option value="{value_attr}" {selected_expr}>{text}</option>')
    parts.append("</select>")
    parts.append(_jinja_call("field_errors", field.field_key))
    return parts


def _render_field(field: RespondentFieldDefinition) -> list[str]:
    is_required = field.on_registration_page == FieldOnRegistrationPage.YES_REQUIRED
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
        return _render_checkbox(field, required_attr)
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


def generate_starter_form_html(fields: list[RespondentFieldDefinition]) -> str:
    """Generate an unstyled starter HTML form from a respondent field schema.

    Output uses ``{{ csrf_form_element }}`` and ``{{ form_action }}`` so it is
    a valid input for ``RegistrationPageHtml.render``. The skeleton also
    includes optional ``{{ assembly_title }}`` and ``{{ assembly_question }}``
    placeholders above the form so authors get a sensible heading and
    intro paragraph by default; both substitute to the empty string when
    not supplied. Fields are grouped by ``RespondentFieldGroup`` in
    ``GROUP_DISPLAY_ORDER`` and ordered by ``sort_order`` within each
    group; empty groups are suppressed. Fields whose ``on_registration_page``
    is ``NO`` are omitted, and a field is marked ``required`` when it is
    ``YES_REQUIRED``.
    """
    grouped = _group_fields(fields)

    parts: list[str] = [
        "<h1>{{ assembly_title }}</h1>",
        "<p>{{ assembly_question }}</p>",
        '<form action="{{ form_action }}" method="post">',
        "{{ csrf_form_element }}",
        "{{ form_errors() }}",
    ]
    for group in GROUP_DISPLAY_ORDER:
        bucket = [f for f in grouped.get(group, []) if f.on_registration_page != FieldOnRegistrationPage.NO]
        if not bucket:
            continue
        parts.append(f"<h2>{html_lib.escape(str(GROUP_LABELS[group]))}</h2>")
        for field_def in bucket:
            parts.extend(_render_field(field_def))
    parts.append('<button type="submit">Register</button>')
    parts.append("</form>")
    return "\n".join(parts) + "\n"
