"""ABOUTME: Unit tests for the EmailTemplate domain aggregate
ABOUTME: Covers rendering delegation, reply-to, validation problems and detached copies"""

import uuid

import pytest

from opendlp.domain import email_template as email_template_module
from opendlp.domain import email_template_render as email_template_render_module
from opendlp.domain.email_context import (
    AssemblyContext,
    RespondentContext,
    build_context,
    sample_respondent_context,
)
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
    assembly_context = AssemblyContext(
        title="Sample Assembly",
        question="Should the city pedestrianise the centre?",
        first_assembly_date="2026-01-01",
        number_to_select=100,
    )
    rendered = template.render(build_context(assembly_context, sample_respondent_context([])))
    assert rendered.missing_variables == []


def test_reply_to_defaults_to_empty() -> None:
    template = _template()
    assert template.reply_to_name == ""
    assert template.reply_to_email == ""
    assert template.reply_to() is None


def test_reply_to_is_name_and_email_tuple_when_name_set() -> None:
    template = _template(reply_to_name="The Team", reply_to_email="team@example.com")
    assert template.reply_to() == ("The Team", "team@example.com")


def test_reply_to_is_bare_email_when_no_name() -> None:
    template = _template(reply_to_email="team@example.com")
    assert template.reply_to() == "team@example.com"


def test_reply_to_is_none_when_only_a_name_is_set() -> None:
    """A name with no address has nowhere to send replies, so it is not used."""
    template = _template(reply_to_name="The Team")
    assert template.reply_to() is None


def test_reply_to_fields_are_stripped() -> None:
    template = _template(reply_to_name="  The Team ", reply_to_email=" team@example.com  ")
    assert template.reply_to_name == "The Team"
    assert template.reply_to_email == "team@example.com"


def test_update_sets_reply_to_and_keeps_it_when_not_passed() -> None:
    template = _template()
    template.update(reply_to_name="The Team", reply_to_email=" team@example.com ")
    assert template.reply_to_name == "The Team"
    assert template.reply_to_email == "team@example.com"
    template.update(subject="Another subject")
    assert template.reply_to_name == "The Team"
    assert template.reply_to_email == "team@example.com"


def test_update_can_clear_reply_to() -> None:
    template = _template(reply_to_name="The Team", reply_to_email="team@example.com")
    template.update(reply_to_name="", reply_to_email="")
    assert template.reply_to() is None


def test_create_detached_copy_preserves_reply_to() -> None:
    template = _template(reply_to_name="The Team", reply_to_email="team@example.com")
    copy = template.create_detached_copy()
    assert copy.reply_to_name == "The Team"
    assert copy.reply_to_email == "team@example.com"


def test_validation_accepts_valid_reply_to() -> None:
    assert _template(reply_to_name="The Team", reply_to_email="team@example.com").validation_problems() == []


def test_validation_flags_invalid_reply_to_email() -> None:
    problems = _template(reply_to_email="not-an-email").validation_problems()
    assert problems == ["The email address for replies is not valid"]


@pytest.mark.parametrize("bad_name", ["The\nTeam", "The\r\nTeam", "The\tTeam", "The\x00Team", "The Team"])
def test_validation_flags_control_characters_in_reply_to_name(bad_name: str) -> None:
    """A line break in the name would make every send fail when the header is built."""
    problems = _template(reply_to_name=bad_name, reply_to_email="team@example.com").validation_problems()
    assert problems == ["The name for replies cannot contain line breaks or other control characters"]


def test_validation_allows_zero_width_joiner_in_reply_to_name() -> None:
    name = "Team \U0001f469‍\U0001f4bb"
    assert _template(reply_to_name=name, reply_to_email="team@example.com").validation_problems() == []


def test_validation_flags_overlong_reply_to_fields() -> None:
    problems = _template(
        reply_to_name="n" * 256, reply_to_email="a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 60 + ".com"
    ).validation_problems()
    assert "The name for replies must be at most 255 characters" in problems
    assert "The email address for replies must be at most 255 characters" in problems


def test_validation_problems_are_translated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every problem is shown to a manager, so each one goes through gettext."""
    monkeypatch.setattr(email_template_module, "_", lambda msgid, **kwargs: "TR:" + (msgid % kwargs))
    monkeypatch.setattr(email_template_render_module, "_", lambda msgid, **kwargs: "TR:" + (msgid % kwargs))
    problems = EmailTemplate(
        assembly_id=uuid.uuid4(),
        name="",
        subject="{% if %}",
        body_html="",
        reply_to_name="a\nb",
        reply_to_email="nope",
    ).validation_problems()
    assert len(problems) == 5
    assert all(p.startswith("TR:") for p in problems), problems


def test_unfilled_placeholders_finds_bracketed_text_in_order_once() -> None:
    template = _template(
        subject="Welcome to [Assembly name]",
        body_html="<p>[Date]: we will call. [Date]: the first session.</p><p>[Your name]</p>",
    )
    assert template.unfilled_placeholders() == ["[Assembly name]", "[Date]", "[Your name]"]


def test_unfilled_placeholders_finds_letters_in_any_language() -> None:
    assert _template(body_html="<p>Üdvözlettel, [Neved]</p>").unfilled_placeholders() == ["[Neved]"]


def test_unfilled_placeholders_ignores_numbers_and_attributes() -> None:
    template = _template(body_html='<p>See note [1].</p><p><a href="https://example.org/[x]">Link</a></p>')
    assert template.unfilled_placeholders() == []


def test_the_default_auto_reply_has_placeholders_to_fill() -> None:
    body = (
        "<li>[Date, time and place of each session]</li>"
        "<p>around a [10 to 20] in 100 chance</p><p>Kind regards,<br>[Your name]</p>"
    )
    assert _template(body_html=body).unfilled_placeholders() == [
        "[Date, time and place of each session]",
        "[10 to 20]",
        "[Your name]",
    ]


@pytest.mark.parametrize(
    ("subject", "body", "uses"),
    [
        ("Hi", "<p>{{ assembly.first_assembly_date_text }}</p>", True),
        ("Starts {{assembly.first_assembly_date}}", "<p>x</p>", True),
        ("Hi", "<p>{{ project.first_event_date_text }}</p>", True),
        ("Starts {{project.first_event_date}}", "<p>x</p>", True),
        ("Hi", "<p>{{ assembly.title }}</p>", False),
        ("Hi", "<p>{{ project.title }}</p>", False),
    ],
)
def test_uses_first_assembly_date(subject: str, body: str, uses: bool) -> None:
    assert _template(subject=subject, body_html=body).uses_first_assembly_date() is uses
