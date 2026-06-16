"""ABOUTME: Unit tests for the templated-email rendering seam
ABOUTME: Covers lenient rendering, missing-variable recording and escaping"""

from opendlp.domain.email_template_render import (
    RenderedEmail,
    render_template_string,
    template_syntax_problems,
)


def _context(**respondent_attrs: str) -> dict:
    return {"respondent": {"attributes": dict(respondent_attrs)}}


def test_renders_subject_and_body() -> None:
    result = render_template_string(
        subject="Hello {{ name }}",
        body_html="<p>Hi {{ name }}</p>",
        context={"name": "Sam"},
    )
    assert isinstance(result, RenderedEmail)
    assert result.subject == "Hello Sam"
    assert "Hi Sam" in result.html_body
    assert "Hi Sam" in result.text_body
    assert result.missing_variables == []


def test_missing_variable_renders_empty_and_is_recorded() -> None:
    result = render_template_string(
        subject="Hi {{ missing_subject_var }}",
        body_html="<p>Body {{ missing_body_var }}</p>",
        context={},
    )
    assert result.subject == "Hi "
    assert "Body" in result.html_body
    assert "missing_subject_var" in result.missing_variables
    assert "missing_body_var" in result.missing_variables


def test_body_autoescapes_untrusted_values() -> None:
    result = render_template_string(
        subject="x",
        body_html="<p>{{ name }}</p>",
        context={"name": "<script>bad()</script>"},
    )
    assert "<script>bad()</script>" not in result.html_body
    assert "&lt;script&gt;" in result.html_body


def test_subject_is_not_html_escaped() -> None:
    result = render_template_string(
        subject="A & B <C>",
        body_html="<p>x</p>",
        context={},
    )
    assert result.subject == "A & B <C>"


def test_template_syntax_problems_flags_bad_syntax() -> None:
    problems = template_syntax_problems(subject="{{ ok }}", body_html="<p>{% if %}</p>")
    assert problems
    assert any("body" in p for p in problems)


def test_template_syntax_problems_allows_unknown_variables() -> None:
    assert template_syntax_problems(subject="{{ anything }}", body_html="<p>{{ unknown }}</p>") == []
