"""ABOUTME: Unit tests for the EmailTemplate domain aggregate
ABOUTME: Covers rendering delegation, validation problems and detached copies"""

import uuid

from opendlp.domain.email_context import AssemblyContext, RespondentContext, build_context
from opendlp.domain.email_template import EmailTemplate, RenderedEmail


def _template(**kwargs: object) -> EmailTemplate:
    defaults: dict = {
        "assembly_id": uuid.uuid4(),
        "name": "Auto-reply",
        "subject": "Thanks {{ respondent.first_name_or_friend }}",
        "body_html": "<p>Hi {{ respondent.first_name_or_friend }}</p>",
    }
    defaults.update(kwargs)
    return EmailTemplate(**defaults)


def test_render_returns_rendered_email() -> None:
    template = _template()
    context = build_context(
        AssemblyContext(title="A"),
        RespondentContext(email="a@b.com", attributes={"firstname": "Sam"}),
    )
    rendered = template.render(context)
    assert isinstance(rendered, RenderedEmail)
    assert rendered.subject == "Thanks Sam"
    assert "Hi Sam" in rendered.html_body


def test_render_uses_friend_fallback() -> None:
    template = _template()
    context = build_context(
        AssemblyContext(title="A"),
        RespondentContext(email="a@b.com", attributes={}),
    )
    rendered = template.render(context)
    assert rendered.subject == "Thanks Friend"


def test_validation_problems_empty_for_valid_template() -> None:
    assert _template().validation_problems() == []


def test_validation_problems_flags_blank_fields() -> None:
    problems = EmailTemplate(assembly_id=uuid.uuid4(), name="", subject="", body_html="").validation_problems()
    assert len(problems) == 3


def test_validation_problems_flags_syntax_error() -> None:
    problems = _template(body_html="<p>{% if %}</p>").validation_problems()
    assert any("syntax" in p for p in problems)


def test_update_changes_fields_and_bumps_timestamp() -> None:
    template = _template()
    before = template.updated_at
    template.update(name="New name", subject="New subject", body_html="<p>New</p>")
    assert template.name == "New name"
    assert template.subject == "New subject"
    assert template.body_html == "<p>New</p>"
    assert template.updated_at >= before


def test_create_detached_copy_preserves_identity() -> None:
    template = _template()
    copy = template.create_detached_copy()
    assert copy is not template
    assert copy == template
    assert copy.id == template.id
    assert copy.subject == template.subject


def test_sample_context_renders_without_missing_variables() -> None:
    template = _template()
    rendered = template.render(template.sample_context())
    assert rendered.missing_variables == []
