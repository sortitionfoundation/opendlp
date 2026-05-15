"""ABOUTME: Unit tests for the RegistrationPage domain model
ABOUTME: Covers the page aggregate, its HTML source, rendering and readiness"""

import uuid
from datetime import UTC, datetime

import pytest

from opendlp.domain.registration_page import (
    DEFAULT_THANK_YOU_HTML,
    REQUIRED_TOKENS,
    HtmlSource,
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageSource,
    RenderContext,
)

READY_HTML = "<form>{{ csrf_form_element }} posts to {{ form_action }}</form>"


class _StubSource:
    def __init__(self, problems: list[str] | None = None):
        self._problems = problems or []

    def render(self, ctx: RenderContext) -> str:
        return ""

    def readiness_problems(self) -> list[str]:
        return list(self._problems)


class TestRegistrationPageSource:
    def test_registration_page_source_has_html_member(self):
        assert RegistrationPageSource.HTML.value == "html"


class TestDefaultThankYouHtml:
    def test_default_thank_you_html_has_h1_and_p(self):
        assert DEFAULT_THANK_YOU_HTML
        assert "<h1>" in DEFAULT_THANK_YOU_HTML
        assert "<p>" in DEFAULT_THANK_YOU_HTML


class TestRenderContext:
    def test_render_context_holds_csrf_and_form_action(self):
        ctx = RenderContext(csrf_form_element="<input>", form_action="/submit")
        assert ctx.csrf_form_element == "<input>"
        assert ctx.form_action == "/submit"

    def test_required_tokens_are_csrf_and_form_action(self):
        assert REQUIRED_TOKENS == ("csrf_form_element", "form_action")


class TestRegistrationPageHtml:
    def test_html_init_defaults(self):
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4())
        assert html.form_html == ""
        assert isinstance(html.id, uuid.UUID)
        assert html.created_at is not None
        assert html.updated_at is not None

    def test_html_init_keeps_given_id(self):
        html_id = uuid.uuid4()
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4(), html_id=html_id)
        assert html.id == html_id

    def test_update_html_sets_value_and_bumps_updated_at(self):
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4())
        original = html.updated_at
        html.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        html.update_html("<form></form>")
        assert html.form_html == "<form></form>"
        assert html.updated_at > datetime(2000, 1, 1, tzinfo=UTC)
        assert html.updated_at >= original

    def test_render_substitutes_both_tokens(self):
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4(), form_html=READY_HTML)
        rendered = html.render(RenderContext(csrf_form_element="<csrf>", form_action="/r/submit"))
        assert rendered == "<form><csrf> posts to /r/submit</form>"

    def test_render_leaves_unknown_braces_untouched(self):
        html = RegistrationPageHtml(
            registration_page_id=uuid.uuid4(),
            form_html="{{ something_else }} {{ form_action }}",
        )
        rendered = html.render(RenderContext(csrf_form_element="x", form_action="/u"))
        assert rendered == "{{ something_else }} /u"

    def test_render_with_no_tokens_returns_html_unchanged(self):
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4(), form_html="<p>hello</p>")
        rendered = html.render(RenderContext(csrf_form_element="x", form_action="/u"))
        assert rendered == "<p>hello</p>"

    def test_readiness_problems_empty_when_html_ready(self):
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4(), form_html=READY_HTML)
        assert html.readiness_problems() == []

    def test_readiness_problems_reports_empty_html(self):
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4(), form_html="   \n  ")
        assert html.readiness_problems() == ["The form HTML is empty"]

    def test_readiness_problems_reports_missing_token(self):
        html = RegistrationPageHtml(
            registration_page_id=uuid.uuid4(),
            form_html="<form>{{ csrf_form_element }}</form>",
        )
        problems = html.readiness_problems()
        assert len(problems) == 1
        assert "form_action" in problems[0]

    def test_html_create_detached_copy(self):
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4(), form_html=READY_HTML)
        copy = html.create_detached_copy()
        assert copy is not html
        assert copy.id == html.id
        assert copy.registration_page_id == html.registration_page_id
        assert copy.form_html == html.form_html


class TestHtmlSourceProtocol:
    def test_registration_page_html_is_an_html_source(self):
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4())
        assert isinstance(html, HtmlSource)


class TestRegistrationPageInit:
    def test_init_sets_id_when_not_given(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        assert isinstance(page.id, uuid.UUID)

    def test_init_keeps_given_id(self):
        page_id = uuid.uuid4()
        page = RegistrationPage(assembly_id=uuid.uuid4(), registration_page_id=page_id)
        assert page.id == page_id

    def test_init_defaults(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        assert page.is_published is False
        assert page.source_type is RegistrationPageSource.HTML
        assert page.url_slug == ""
        assert page.short_url_slug == ""
        assert page.thank_you_html == ""

    def test_init_autogenerates_preview_token(self):
        page_a = RegistrationPage(assembly_id=uuid.uuid4())
        page_b = RegistrationPage(assembly_id=uuid.uuid4())
        assert page_a.preview_token
        assert page_a.preview_token != page_b.preview_token

    def test_init_keeps_given_preview_token(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), preview_token="fixed-token")
        assert page.preview_token == "fixed-token"

    def test_init_sets_created_and_updated_at(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        assert page.created_at is not None
        assert page.updated_at is not None

    def test_init_validates_url_slug(self):
        with pytest.raises(ValueError):
            RegistrationPage(assembly_id=uuid.uuid4(), url_slug="Bad Slug")

    def test_init_validates_short_url_slug(self):
        with pytest.raises(ValueError):
            RegistrationPage(assembly_id=uuid.uuid4(), short_url_slug="Bad Slug")

    def test_init_allows_empty_slugs(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="", short_url_slug="")
        assert page.url_slug == ""
        assert page.short_url_slug == ""


class TestUpdateSlugs:
    def test_update_slugs_changes_url_slug(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.update_slugs(url_slug="my-page")
        assert page.url_slug == "my-page"

    def test_update_slugs_changes_short_url_slug(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.update_slugs(short_url_slug="mp")
        assert page.short_url_slug == "mp"

    def test_update_slugs_changes_both(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.update_slugs(url_slug="my-page", short_url_slug="mp")
        assert page.url_slug == "my-page"
        assert page.short_url_slug == "mp"

    def test_update_slugs_none_leaves_value_alone(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="keep-me")
        page.update_slugs(short_url_slug="mp")
        assert page.url_slug == "keep-me"

    def test_update_slugs_empty_string_clears(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="clear-me")
        page.update_slugs(url_slug="")
        assert page.url_slug == ""

    def test_update_slugs_validates(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        with pytest.raises(ValueError):
            page.update_slugs(url_slug="Bad Slug")

    def test_update_slugs_raises_when_published(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page", is_published=True)
        with pytest.raises(ValueError, match="published"):
            page.update_slugs(url_slug="new-page")

    def test_update_slugs_bumps_updated_at(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        page.update_slugs(url_slug="my-page")
        assert page.updated_at > datetime(2000, 1, 1, tzinfo=UTC)


class TestUpdateThankYouHtml:
    def test_update_thank_you_html_sets_value(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.update_thank_you_html("<p>thanks</p>")
        assert page.thank_you_html == "<p>thanks</p>"

    def test_update_thank_you_html_bumps_updated_at(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        page.update_thank_you_html("<p>thanks</p>")
        assert page.updated_at > datetime(2000, 1, 1, tzinfo=UTC)


class TestPublishAndReadiness:
    def test_readiness_problems_empty_when_ready(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        assert page.readiness_problems(_StubSource()) == []

    def test_readiness_problems_reports_missing_url_slug(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        problems = page.readiness_problems(_StubSource())
        assert any("URL slug" in p for p in problems)

    def test_readiness_problems_includes_source_problems(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        problems = page.readiness_problems(_StubSource(["bad html"]))
        assert "bad html" in problems

    def test_publish_sets_is_published(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        page.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        page.publish(_StubSource())
        assert page.is_published is True
        assert page.updated_at > datetime(2000, 1, 1, tzinfo=UTC)

    def test_publish_raises_when_not_ready(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        with pytest.raises(RegistrationPageNotReady) as exc_info:
            page.publish(_StubSource(["bad html"]))
        assert "bad html" in exc_info.value.problems
        assert page.is_published is False

    def test_unpublish_clears_is_published(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page", is_published=True)
        token_before = page.preview_token
        page.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        page.unpublish()
        assert page.is_published is False
        assert page.updated_at > datetime(2000, 1, 1, tzinfo=UTC)
        assert page.preview_token == token_before

    def test_publish_with_real_html_source(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        html = RegistrationPageHtml(registration_page_id=page.id, form_html=READY_HTML)
        page.publish(html)
        assert page.is_published is True


class TestVisibilityAndPreviewToken:
    def test_is_visible_with_published_is_always_visible(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page", is_published=True)
        assert page.is_visible_with("") is True
        assert page.is_visible_with("anything") is True

    def test_is_visible_with_unpublished_needs_matching_token(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), preview_token="secret")
        assert page.is_visible_with("secret") is True
        assert page.is_visible_with("wrong") is False
        assert page.is_visible_with("") is False

    def test_regenerate_preview_token_changes_token(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        token_before = page.preview_token
        page.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        page.regenerate_preview_token()
        assert page.preview_token != token_before
        assert page.updated_at > datetime(2000, 1, 1, tzinfo=UTC)


class TestCreateDetachedCopyAndIdentity:
    def test_create_detached_copy_is_equal_independent_object(self):
        page = RegistrationPage(
            assembly_id=uuid.uuid4(),
            url_slug="a-page",
            short_url_slug="ap",
            thank_you_html="<p>thanks</p>",
        )
        copy = page.create_detached_copy()
        assert copy is not page
        assert copy == page
        assert copy.assembly_id == page.assembly_id
        assert copy.url_slug == page.url_slug
        assert copy.short_url_slug == page.short_url_slug
        assert copy.preview_token == page.preview_token
        assert copy.source_type == page.source_type
        assert copy.thank_you_html == page.thank_you_html
        assert copy.created_at == page.created_at
        assert copy.updated_at == page.updated_at

    def test_eq_by_id(self):
        page_id = uuid.uuid4()
        page_a = RegistrationPage(assembly_id=uuid.uuid4(), registration_page_id=page_id)
        page_b = RegistrationPage(assembly_id=uuid.uuid4(), registration_page_id=page_id)
        assert page_a == page_b

    def test_hash_by_id(self):
        page_id = uuid.uuid4()
        page_a = RegistrationPage(assembly_id=uuid.uuid4(), registration_page_id=page_id)
        page_b = RegistrationPage(assembly_id=uuid.uuid4(), registration_page_id=page_id)
        assert hash(page_a) == hash(page_b)
