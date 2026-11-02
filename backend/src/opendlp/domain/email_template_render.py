"""ABOUTME: Rendering seam for database-stored email templates
ABOUTME: Lenient sandboxed rendering that records missing variables for later review"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jinja2 import TemplateSyntaxError, Undefined
from jinja2.sandbox import SandboxedEnvironment

from opendlp.domain.html_to_text import html_to_text
from opendlp.translations import gettext as _

_PARSE_ENV = SandboxedEnvironment(autoescape=True)


@dataclass(frozen=True)
class RenderedEmail:
    """The result of rendering an email template against a context."""

    subject: str
    html_body: str
    text_body: str
    missing_variables: list[str]


def _recording_environment(autoescape: bool, missing: list[str]) -> SandboxedEnvironment:
    class _RecordingUndefined(Undefined):
        def _record(self) -> None:
            name = self._undefined_name
            if name and name not in missing:
                missing.append(name)

        def __str__(self) -> str:
            self._record()
            return ""

        def __html__(self) -> str:
            self._record()
            return ""

    return SandboxedEnvironment(autoescape=autoescape, undefined=_RecordingUndefined)


def render_template_string(subject: str, body_html: str, context: Mapping[str, Any]) -> RenderedEmail:
    missing: list[str] = []
    rendered_subject = _recording_environment(autoescape=False, missing=missing).from_string(subject).render(**context)
    rendered_html = _recording_environment(autoescape=True, missing=missing).from_string(body_html).render(**context)
    return RenderedEmail(
        subject=rendered_subject,
        html_body=rendered_html,
        text_body=html_to_text(rendered_html),
        missing_variables=sorted(set(missing)),
    )


def _syntax_error(source: str) -> TemplateSyntaxError | None:
    try:
        _PARSE_ENV.parse(source)
    except TemplateSyntaxError as exc:
        return exc
    return None


def template_syntax_problems(subject: str, body_html: str) -> list[str]:
    problems: list[str] = []
    if subject_error := _syntax_error(subject):
        problems.append(
            _(
                "The email subject has a template syntax error on line %(line)s: %(error)s",
                line=subject_error.lineno,
                error=subject_error.message or "",
            )
        )
    if body_error := _syntax_error(body_html):
        problems.append(
            _(
                "The email body has a template syntax error on line %(line)s: %(error)s",
                line=body_error.lineno,
                error=body_error.message or "",
            )
        )
    return problems
