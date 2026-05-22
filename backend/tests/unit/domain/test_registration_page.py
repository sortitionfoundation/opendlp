"""ABOUTME: Unit tests for the RegistrationPage domain model
ABOUTME: Covers the page aggregate, its HTML source, rendering and readiness"""

import uuid
from datetime import UTC, datetime

import pytest
from jinja2 import UndefinedError
from jinja2.exceptions import SecurityError

from opendlp.domain.registration_page import (
    DEFAULT_THANK_YOU_HTML,
    REQUIRED_TOKENS,
    HtmlSource,
    RegistrationPage,
    RegistrationPageAction,
    RegistrationPageActivity,
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageSource,
    RegistrationPageStatus,
    RenderContext,
    generate_starter_form_html,
)
from opendlp.domain.respondent_field_schema import (
    GROUP_LABELS,
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
    humanise_field_key,
)
from opendlp.domain.validators import SlugError

ASSEMBLY_ID = uuid.uuid4()


def _field(
    field_key: str,
    group: RespondentFieldGroup,
    sort_order: int,
    *,
    label: str = "",
    field_type: FieldType = FieldType.TEXT,
    options: list[ChoiceOption] | None = None,
    is_fixed: bool = False,
) -> RespondentFieldDefinition:
    return RespondentFieldDefinition(
        assembly_id=ASSEMBLY_ID,
        field_key=field_key,
        label=label or humanise_field_key(field_key),
        group=group,
        sort_order=sort_order,
        is_fixed=is_fixed,
        field_type=field_type,
        options=options,
    )


READY_HTML = "<form>{{ csrf_form_element }} posts to {{ form_action }}</form>"


class _StubSource:
    def __init__(self, problems: list[str] | None = None):
        self._problems = problems or []

    def render(self, ctx: RenderContext) -> str:
        return ""

    def readiness_problems(self) -> list[str]:
        return list(self._problems)


def _published_page(url_slug: str = "a-page") -> RegistrationPage:
    page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug=url_slug)
    page.publish(_StubSource(), author_id=uuid.uuid4())
    return page


class TestRegistrationPageSource:
    def test_registration_page_source_has_html_member(self):
        assert RegistrationPageSource.HTML.value == "html"


class TestRegistrationPageStatus:
    def test_members_are_test_published_closed(self):
        assert RegistrationPageStatus.TEST.value == "TEST"
        assert RegistrationPageStatus.PUBLISHED.value == "PUBLISHED"
        assert RegistrationPageStatus.CLOSED.value == "CLOSED"
        assert set(RegistrationPageStatus) == {
            RegistrationPageStatus.TEST,
            RegistrationPageStatus.PUBLISHED,
            RegistrationPageStatus.CLOSED,
        }


class TestRegistrationPageAction:
    def test_members(self):
        names = {a.value for a in RegistrationPageAction}
        assert names == {"CREATE", "EDIT", "PUBLISH", "UNPUBLISH", "CLOSE", "REOPEN"}


class TestRegistrationPageActivity:
    def test_init_with_explicit_fields(self):
        author_id = uuid.uuid4()
        when = datetime.now(UTC)
        entry = RegistrationPageActivity(
            text="hello", author_id=author_id, created_at=when, action=RegistrationPageAction.PUBLISH
        )
        assert entry.text == "hello"
        assert entry.author_id == author_id
        assert entry.created_at == when
        assert entry.action is RegistrationPageAction.PUBLISH

    def test_action_defaults_to_edit(self):
        entry = RegistrationPageActivity(text="x", author_id=uuid.uuid4(), created_at=datetime.now(UTC))
        assert entry.action is RegistrationPageAction.EDIT

    def test_to_dict_round_trip(self):
        original = RegistrationPageActivity(
            text="hi",
            author_id=uuid.uuid4(),
            created_at=datetime.now(UTC),
            action=RegistrationPageAction.CLOSE,
        )
        data = original.to_dict()
        assert isinstance(data["author_id"], str)
        assert isinstance(data["created_at"], str)
        assert data["action"] == "CLOSE"

        restored = RegistrationPageActivity.from_dict(data)
        assert restored == original

    def test_from_dict_with_unknown_action_falls_back_to_edit(self):
        data = {
            "text": "x",
            "author_id": str(uuid.uuid4()),
            "created_at": datetime.now(UTC).isoformat(),
            "action": "BANANA",
        }
        entry = RegistrationPageActivity.from_dict(data)
        assert entry.action is RegistrationPageAction.EDIT


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

    def test_render_context_validation_fields_default_empty(self):
        ctx = RenderContext(csrf_form_element="<input>", form_action="/submit")
        assert ctx.values == {}
        assert ctx.errors == {}
        assert ctx.form_level_errors == []

    def test_render_context_carries_validation_state(self):
        ctx = RenderContext(
            csrf_form_element="<input>",
            form_action="/submit",
            values={"email": "alice@example.com"},
            errors={"email": ["bad address"]},
            form_level_errors=["please fix the field above"],
        )
        assert ctx.values == {"email": "alice@example.com"}
        assert ctx.errors == {"email": ["bad address"]}
        assert ctx.form_level_errors == ["please fix the field above"]

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

    def test_render_raises_undefined_error_on_unknown_variable(self):
        # Under StrictUndefined the renderer surfaces template typos as
        # UndefinedError instead of silently rendering nothing.
        html = RegistrationPageHtml(
            registration_page_id=uuid.uuid4(),
            form_html="{{ something_else }} {{ form_action }}",
        )
        with pytest.raises(UndefinedError):
            html.render(RenderContext(csrf_form_element="x", form_action="/u"))

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


def _render(form_html: str, **ctx_kwargs) -> str:
    """Render form_html with a RenderContext built from defaults + kwargs."""
    base = {"csrf_form_element": "", "form_action": "/submit"}
    base.update(ctx_kwargs)
    html = RegistrationPageHtml(registration_page_id=uuid.uuid4(), form_html=form_html)
    return html.render(RenderContext(**base))


class TestRenderHelpers:
    # value() round-trips submitted text into input value attributes and
    # textarea bodies, autoescaping HTML-special characters in the process.

    def test_value_returns_submitted_value(self):
        rendered = _render("{{ value('email') }}", values={"email": "alice@example.com"})
        assert rendered == "alice@example.com"

    def test_value_returns_empty_for_unknown_key(self):
        rendered = _render("[{{ value('missing') }}]", values={"other": "v"})
        assert rendered == "[]"

    def test_value_autoescapes_html_special_chars(self):
        rendered = _render("value=\"{{ value('name') }}\"", values={"name": "<script>"})
        assert rendered == 'value="&lt;script&gt;"'

    def test_value_autoescapes_double_quote_in_attribute(self):
        rendered = _render("value=\"{{ value('name') }}\"", values={"name": 'O"Brien'})
        assert "&#34;" in rendered or "&quot;" in rendered

    def test_checked_returns_attribute_when_value_matches(self):
        rendered = _render(
            "<input value=\"yes\" {{ checked('eligible', 'yes') }}>",
            values={"eligible": "yes"},
        )
        assert rendered == '<input value="yes" checked>'

    def test_checked_returns_empty_when_value_differs(self):
        rendered = _render(
            "<input value=\"yes\" {{ checked('eligible', 'yes') }}>",
            values={"eligible": "no"},
        )
        assert rendered == '<input value="yes" >'

    def test_checked_returns_empty_when_field_absent(self):
        rendered = _render(
            "<input value=\"yes\" {{ checked('eligible', 'yes') }}>",
            values={},
        )
        assert rendered == '<input value="yes" >'

    def test_selected_returns_attribute_when_value_matches(self):
        rendered = _render(
            "<option value=\"N\" {{ selected('geo', 'N') }}>",
            values={"geo": "N"},
        )
        assert rendered == '<option value="N" selected>'

    def test_selected_returns_empty_when_value_differs(self):
        rendered = _render(
            "<option value=\"N\" {{ selected('geo', 'N') }}>",
            values={"geo": "S"},
        )
        assert rendered == '<option value="N" >'

    # field_errors() renders one <p class="error"> per error message; empty
    # when no errors. Error text is HTML-escaped to defend against XSS.

    def test_field_errors_renders_paragraph_per_message(self):
        rendered = _render(
            "{{ field_errors('email') }}",
            errors={"email": ["bad address", "domain blocked"]},
        )
        assert '<p class="error">bad address</p>' in rendered
        assert '<p class="error">domain blocked</p>' in rendered

    def test_field_errors_empty_when_no_errors(self):
        rendered = _render("[{{ field_errors('email') }}]", errors={})
        assert rendered == "[]"

    def test_field_errors_escapes_html_in_message(self):
        rendered = _render(
            "{{ field_errors('x') }}",
            errors={"x": ["<script>alert(1)</script>"]},
        )
        assert "<script>" not in rendered
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered

    def test_has_error_true_when_errors_present(self):
        rendered = _render("{{ has_error('email') }}", errors={"email": ["bad"]})
        assert rendered == "True"

    def test_has_error_false_when_field_absent(self):
        rendered = _render("{{ has_error('email') }}", errors={})
        assert rendered == "False"

    def test_first_error_returns_first_message(self):
        rendered = _render("{{ first_error('x') }}", errors={"x": ["one", "two"]})
        assert rendered == "one"

    def test_first_error_returns_empty_string_when_field_absent(self):
        rendered = _render("[{{ first_error('x') }}]", errors={})
        assert rendered == "[]"

    def test_first_error_autoescapes_html(self):
        rendered = _render("{{ first_error('x') }}", errors={"x": ["<b>oh</b>"]})
        assert rendered == "&lt;b&gt;oh&lt;/b&gt;"

    # form_errors() collects cross-field validation messages into an
    # unordered list. Empty when there are no form-level errors.

    def test_form_errors_renders_list_when_populated(self):
        rendered = _render("{{ form_errors() }}", form_level_errors=["a", "b"])
        assert '<ul class="form-errors">' in rendered
        assert "<li>a</li>" in rendered
        assert "<li>b</li>" in rendered

    def test_form_errors_empty_when_no_messages(self):
        rendered = _render("[{{ form_errors() }}]", form_level_errors=[])
        assert rendered == "[]"

    def test_form_errors_escapes_html_in_message(self):
        rendered = _render("{{ form_errors() }}", form_level_errors=["<b>x</b>"])
        assert "<b>x</b>" not in rendered
        assert "&lt;b&gt;x&lt;/b&gt;" in rendered


class TestRenderContextSubstitution:
    # The original render-time tokens still work, but now via Jinja
    # rather than flat str.replace. csrf_form_element must render as raw
    # HTML (it carries the <input>); form_action is plain text.

    def test_csrf_form_element_inserted_as_raw_html(self):
        rendered = _render(
            "{{ csrf_form_element }}",
            csrf_form_element='<input name="csrf_token" value="abc">',
        )
        assert rendered == '<input name="csrf_token" value="abc">'

    def test_form_action_substituted(self):
        rendered = _render('<form action="{{ form_action }}">', form_action="/r/submit")
        assert rendered == '<form action="/r/submit">'


class TestRenderSandbox:
    def test_dunder_attribute_access_blocked(self):
        html = RegistrationPageHtml(
            registration_page_id=uuid.uuid4(),
            form_html="{{ ''.__class__ }}",
        )
        with pytest.raises(SecurityError):
            html.render(RenderContext(csrf_form_element="", form_action="/u"))


class TestRenderGeneratedStarterEndToEnd:
    # Exercise the helper API against a starter form built from a small
    # realistic schema, with values and errors set.

    def test_pre_filled_values_and_errors_round_trip(self):
        fields = [
            _field("email", RespondentFieldGroup.NAME_AND_CONTACT, 0, field_type=FieldType.EMAIL),
            _field(
                "gender",
                RespondentFieldGroup.ABOUT_YOU,
                0,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Female"), ChoiceOption(value="Male")],
            ),
            _field(
                "geo",
                RespondentFieldGroup.ADDRESS,
                0,
                field_type=FieldType.CHOICE_DROPDOWN,
                options=[ChoiceOption(value="North"), ChoiceOption(value="South")],
            ),
        ]
        starter = generate_starter_form_html(fields)
        rendered = RegistrationPageHtml(
            registration_page_id=uuid.uuid4(),
            form_html=starter,
        ).render(
            RenderContext(
                csrf_form_element="<input name='csrf' value='tok'>",
                form_action="/r/submit",
                values={"email": "alice@example.com", "gender": "Female", "geo": "South"},
                errors={"email": ["already registered"]},
                form_level_errors=["please review the form"],
            )
        )

        # CSRF + form action substituted, no Jinja markers leaking through.
        assert "<input name='csrf' value='tok'>" in rendered
        assert '<form action="/r/submit"' in rendered
        assert "{{" not in rendered

        # Pre-filled email value.
        assert 'value="alice@example.com"' in rendered

        # Pre-filled radio + dropdown selections; unmatched options stay empty.
        assert 'value="Female" checked' in rendered
        assert 'value="Male" checked' not in rendered
        assert 'value="South" selected' in rendered
        assert 'value="North" selected' not in rendered

        # Field error rendered next to the email field.
        assert '<p class="error">already registered</p>' in rendered

        # Form-level error rendered near the top.
        assert '<ul class="form-errors">' in rendered
        assert "<li>please review the form</li>" in rendered


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
        assert page.status is RegistrationPageStatus.TEST
        assert page.activity == []
        assert page.source_type is RegistrationPageSource.HTML
        assert page.url_slug == ""
        assert page.short_url_slug == ""
        assert page.thank_you_html == ""

    def test_init_sets_created_and_updated_at(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        assert page.created_at is not None
        assert page.updated_at is not None

    def test_init_validates_url_slug(self):
        with pytest.raises(SlugError) as exc:
            RegistrationPage(assembly_id=uuid.uuid4(), url_slug="admin")
        assert exc.value.field == "url_slug"
        assert exc.value.reason == "reserved"

    def test_init_validates_short_url_slug(self):
        with pytest.raises(SlugError) as exc:
            RegistrationPage(assembly_id=uuid.uuid4(), short_url_slug="Bad Slug")
        assert exc.value.field == "short_url_slug"
        assert exc.value.reason == "malformed"

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

    def test_update_slugs_raises_after_first_publish(self):
        page = _published_page("a-page")
        with pytest.raises(ValueError, match="published"):
            page.update_slugs(url_slug="new-page")

    def test_update_slugs_allowed_when_never_published_even_if_status_draft(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.update_slugs(url_slug="a-page")
        assert page.url_slug == "a-page"

    def test_update_slugs_still_raises_in_closed_state(self):
        page = _published_page("a-page")
        page.close(author_id=uuid.uuid4())
        assert page.status is RegistrationPageStatus.CLOSED
        with pytest.raises(ValueError, match="published"):
            page.update_slugs(url_slug="changed")

    def test_update_slugs_still_raises_after_unpublish(self):
        page = _published_page("a-page")
        page.unpublish(author_id=uuid.uuid4())
        assert page.status is RegistrationPageStatus.TEST
        with pytest.raises(ValueError, match="published"):
            page.update_slugs(url_slug="changed")

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

    def test_publish_sets_status_published(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        page.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        page.publish(_StubSource(), author_id=uuid.uuid4())
        assert page.status is RegistrationPageStatus.PUBLISHED
        assert page.updated_at > datetime(2000, 1, 1, tzinfo=UTC)

    def test_publish_appends_publish_activity(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        author_id = uuid.uuid4()
        page.publish(_StubSource(), author_id=author_id, text="going live")
        assert len(page.activity) == 1
        entry = page.activity[0]
        assert entry.action is RegistrationPageAction.PUBLISH
        assert entry.author_id == author_id
        assert entry.text == "going live"

    def test_publish_text_default_is_empty_string(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        page.publish(_StubSource(), author_id=uuid.uuid4())
        assert page.activity[0].text == ""

    def test_publish_raises_when_not_ready(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        with pytest.raises(RegistrationPageNotReady) as exc_info:
            page.publish(_StubSource(["bad html"]), author_id=uuid.uuid4())
        assert "bad html" in exc_info.value.problems
        assert page.status is RegistrationPageStatus.TEST
        assert page.activity == []

    def test_publish_from_published_raises(self):
        page = _published_page()
        with pytest.raises(ValueError, match="PUBLISHED"):
            page.publish(_StubSource(), author_id=uuid.uuid4())

    def test_publish_from_closed_raises(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        with pytest.raises(ValueError, match="CLOSED"):
            page.publish(_StubSource(), author_id=uuid.uuid4())

    def test_unpublish_sets_status_test(self):
        page = _published_page()
        page.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        page.unpublish(author_id=uuid.uuid4())
        assert page.status is RegistrationPageStatus.TEST
        assert page.updated_at > datetime(2000, 1, 1, tzinfo=UTC)

    def test_unpublish_appends_unpublish_activity(self):
        page = _published_page()
        author_id = uuid.uuid4()
        page.unpublish(author_id=author_id, text="typo")
        last = page.activity[-1]
        assert last.action is RegistrationPageAction.UNPUBLISH
        assert last.author_id == author_id
        assert last.text == "typo"

    def test_unpublish_from_test_raises(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        with pytest.raises(ValueError, match="TEST"):
            page.unpublish(author_id=uuid.uuid4())

    def test_unpublish_from_closed_raises(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        with pytest.raises(ValueError, match="CLOSED"):
            page.unpublish(author_id=uuid.uuid4())

    def test_publish_with_real_html_source(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        html = RegistrationPageHtml(registration_page_id=page.id, form_html=READY_HTML)
        page.publish(html, author_id=uuid.uuid4())
        assert page.status is RegistrationPageStatus.PUBLISHED


class TestCloseAndReopen:
    def test_close_from_published_sets_status_closed(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        assert page.status is RegistrationPageStatus.CLOSED

    def test_close_appends_close_activity(self):
        page = _published_page()
        author_id = uuid.uuid4()
        page.close(author_id=author_id, text="sortition done")
        last = page.activity[-1]
        assert last.action is RegistrationPageAction.CLOSE
        assert last.author_id == author_id
        assert last.text == "sortition done"

    def test_close_from_test_raises(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        with pytest.raises(ValueError, match="TEST"):
            page.close(author_id=uuid.uuid4())

    def test_close_from_closed_raises(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        with pytest.raises(ValueError, match="CLOSED"):
            page.close(author_id=uuid.uuid4())

    def test_reopen_from_closed_sets_status_published(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        page.reopen(_StubSource(), author_id=uuid.uuid4())
        assert page.status is RegistrationPageStatus.PUBLISHED

    def test_reopen_appends_reopen_activity(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        author_id = uuid.uuid4()
        page.reopen(_StubSource(), author_id=author_id, text="resuming")
        last = page.activity[-1]
        assert last.action is RegistrationPageAction.REOPEN
        assert last.author_id == author_id
        assert last.text == "resuming"

    def test_reopen_runs_readiness_check(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        with pytest.raises(RegistrationPageNotReady):
            page.reopen(_StubSource(["bad html"]), author_id=uuid.uuid4())
        assert page.status is RegistrationPageStatus.CLOSED

    def test_reopen_from_test_raises(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        with pytest.raises(ValueError, match="TEST"):
            page.reopen(_StubSource(), author_id=uuid.uuid4())

    def test_reopen_from_published_raises(self):
        page = _published_page()
        with pytest.raises(ValueError, match="PUBLISHED"):
            page.reopen(_StubSource(), author_id=uuid.uuid4())


class TestHasEverBeenPublished:
    def test_false_when_no_activity(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        assert page.has_ever_been_published() is False

    def test_false_with_only_edit_activity(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.record_edit(uuid.uuid4(), "something")
        assert page.has_ever_been_published() is False

    def test_true_after_publish(self):
        page = _published_page()
        assert page.has_ever_been_published() is True

    def test_true_after_publish_then_unpublish(self):
        page = _published_page()
        page.unpublish(author_id=uuid.uuid4())
        assert page.has_ever_been_published() is True

    def test_true_after_publish_then_close(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        assert page.has_ever_been_published() is True


class TestSlugsFrozen:
    def test_unfrozen_initially(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        assert page.slugs_frozen is False

    def test_frozen_after_publish(self):
        page = _published_page()
        assert page.slugs_frozen is True


class TestRecordEdit:
    def test_appends_one_entry(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        author_id = uuid.uuid4()
        page.record_edit(author_id, "Updated form HTML")
        assert len(page.activity) == 1
        entry = page.activity[0]
        assert entry.action is RegistrationPageAction.EDIT
        assert entry.author_id == author_id
        assert entry.text == "Updated form HTML"

    def test_uses_list_reassignment(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        old = page.activity
        page.record_edit(uuid.uuid4(), "foo")
        assert page.activity is not old

    def test_bumps_updated_at(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        page.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
        page.record_edit(uuid.uuid4(), "foo")
        assert page.updated_at > datetime(2000, 1, 1, tzinfo=UTC)


class TestRecordCreate:
    def test_appends_create_entry(self):
        page = RegistrationPage(assembly_id=uuid.uuid4())
        author_id = uuid.uuid4()
        page.record_create(author_id)
        entry = page.activity[0]
        assert entry.action is RegistrationPageAction.CREATE
        assert entry.author_id == author_id
        assert entry.text


class TestPublicLoadability:
    def test_published_is_publicly_loadable(self):
        page = _published_page()
        assert page.is_publicly_loadable() is True

    def test_test_status_is_publicly_loadable(self):
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="a-page")
        assert page.status is RegistrationPageStatus.TEST
        assert page.is_publicly_loadable() is True

    def test_closed_is_not_publicly_loadable(self):
        page = _published_page()
        page.close(author_id=uuid.uuid4())
        assert page.is_publicly_loadable() is False

    def test_empty_url_slug_is_not_publicly_loadable(self):
        # A freshly created page is TEST with no slug; it has no URL to render at.
        page = RegistrationPage(assembly_id=uuid.uuid4(), url_slug="")
        assert page.status is RegistrationPageStatus.TEST
        assert page.is_publicly_loadable() is False


class TestCreateDetachedCopyAndIdentity:
    def test_create_detached_copy_is_equal_independent_object(self):
        page = RegistrationPage(
            assembly_id=uuid.uuid4(),
            url_slug="a-page",
            short_url_slug="ap",
            thank_you_html="<p>thanks</p>",
        )
        page.record_create(uuid.uuid4())
        copy = page.create_detached_copy()
        assert copy is not page
        assert copy == page
        assert copy.assembly_id == page.assembly_id
        assert copy.url_slug == page.url_slug
        assert copy.short_url_slug == page.short_url_slug
        assert copy.source_type == page.source_type
        assert copy.thank_you_html == page.thank_you_html
        assert copy.status == page.status
        assert copy.activity == page.activity
        assert copy.activity is not page.activity
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


class TestGenerateStarterFormHtml:
    def test_empty_schema_minimal_form(self):
        html = generate_starter_form_html([])

        assert '<form action="{{ form_action }}" method="post">' in html
        assert "{{ csrf_form_element }}" in html
        assert "{{ form_errors() }}" in html
        assert '<button type="submit">Register</button>' in html
        assert html.rstrip().endswith("</form>")

    def test_form_errors_appears_between_csrf_and_button(self):
        html = generate_starter_form_html([])

        csrf_pos = html.find("{{ csrf_form_element }}")
        form_errors_pos = html.find("{{ form_errors() }}")
        button_pos = html.find('<button type="submit">')
        assert -1 < csrf_pos < form_errors_pos < button_pos

    def test_text_field_renders_input_with_value_helper(self):
        fields = [_field("first_name", RespondentFieldGroup.NAME_AND_CONTACT, 0)]
        html = generate_starter_form_html(fields)

        assert '<label for="first_name">First name</label>' in html
        assert ('<input type="text" id="first_name" name="first_name" value="{{ value(\'first_name\') }}">') in html
        assert "{{ field_errors('first_name') }}" in html

    def test_email_field_renders_email_input_with_value_helper(self):
        fields = [_field("email", RespondentFieldGroup.NAME_AND_CONTACT, 0, field_type=FieldType.EMAIL)]
        html = generate_starter_form_html(fields)

        assert ('<input type="email" id="email" name="email" value="{{ value(\'email\') }}">') in html
        assert "{{ field_errors('email') }}" in html

    def test_longtext_field_renders_textarea_with_value_helper(self):
        fields = [_field("about", RespondentFieldGroup.ABOUT_YOU, 0, field_type=FieldType.LONGTEXT)]
        html = generate_starter_form_html(fields)

        assert ('<textarea id="about" name="about">{{ value(\'about\') }}</textarea>') in html
        assert "{{ field_errors('about') }}" in html

    def test_integer_field_renders_number_input_with_value_helper(self):
        fields = [_field("age", RespondentFieldGroup.ABOUT_YOU, 0, field_type=FieldType.INTEGER)]
        html = generate_starter_form_html(fields)

        assert ('<input type="number" id="age" name="age" value="{{ value(\'age\') }}">') in html
        assert "{{ field_errors('age') }}" in html

    def test_bool_field_renders_two_radios_with_checked_helpers(self):
        fields = [_field("eligible", RespondentFieldGroup.ELIGIBILITY, 0, field_type=FieldType.BOOL)]
        html = generate_starter_form_html(fields)

        assert "<fieldset>" in html
        assert "<legend>Eligible</legend>" in html
        assert ('<input type="radio" name="eligible" value="yes" {{ checked(\'eligible\', \'yes\') }}>') in html
        assert ('<input type="radio" name="eligible" value="no" {{ checked(\'eligible\', \'no\') }}>') in html
        assert "{{ field_errors('eligible') }}" in html

    def test_bool_or_none_field_renders_two_radios_no_third_option(self):
        fields = [_field("can_attend", RespondentFieldGroup.ELIGIBILITY, 0, is_fixed=True)]
        html = generate_starter_form_html(fields)

        radio_count = html.count('type="radio" name="can_attend"')
        assert radio_count == 2
        assert ('<input type="radio" name="can_attend" value="yes" {{ checked(\'can_attend\', \'yes\') }}>') in html
        assert ('<input type="radio" name="can_attend" value="no" {{ checked(\'can_attend\', \'no\') }}>') in html
        assert "Not set" not in html

    def test_choice_radio_renders_per_option_radios_with_checked_helpers(self):
        fields = [
            _field(
                "gender",
                RespondentFieldGroup.ABOUT_YOU,
                0,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Female"), ChoiceOption(value="Male")],
            ),
        ]
        html = generate_starter_form_html(fields)

        assert "<legend>Gender</legend>" in html
        assert ('<input type="radio" name="gender" value="Female" {{ checked(\'gender\', \'Female\') }}>') in html
        assert "Female</label>" in html
        assert ('<input type="radio" name="gender" value="Male" {{ checked(\'gender\', \'Male\') }}>') in html
        assert "Male</label>" in html
        assert html.find('value="Female"') < html.find('value="Male"')
        assert "{{ field_errors('gender') }}" in html

    def test_choice_dropdown_not_required_includes_placeholder_and_selected_helpers(self):
        fields = [
            _field(
                "geo",
                RespondentFieldGroup.ADDRESS,
                0,
                field_type=FieldType.CHOICE_DROPDOWN,
                options=[ChoiceOption(value="North"), ChoiceOption(value="South")],
            ),
        ]
        html = generate_starter_form_html(fields)

        assert '<select id="geo" name="geo">' in html
        assert '<option value="">' in html
        assert ("<option value=\"North\" {{ selected('geo', 'North') }}>North</option>") in html
        assert ("<option value=\"South\" {{ selected('geo', 'South') }}>South</option>") in html
        assert "{{ field_errors('geo') }}" in html

    def test_html_escapes_label_and_option_value(self):
        # Labels are HTML-escaped in <legend>, option values are HTML-escaped in
        # value="..." attributes. Inside Jinja string literals the raw value is
        # used (Jinja literals do not interpret HTML entities) so the helper can
        # compare against the literal value the browser submits.
        fields = [
            _field(
                "company",
                RespondentFieldGroup.OTHER,
                0,
                label="AT&T",
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="<Yes>")],
            ),
        ]
        html = generate_starter_form_html(fields)

        assert "AT&amp;T" in html
        assert "AT&T<" not in html
        assert "&lt;Yes&gt;" in html
        assert " {{ checked('company', '<Yes>') }}" in html

    def test_single_quote_in_option_value_is_escaped_in_jinja_literal(self):
        # An apostrophe inside the Jinja string literal must be escaped so the
        # template still parses; the raw character stays inside the HTML
        # attribute (where html.escape keeps it as the &#x27; entity).
        fields = [
            _field(
                "name_prefix",
                RespondentFieldGroup.NAME_AND_CONTACT,
                0,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="O'Brien")],
            ),
        ]
        html = generate_starter_form_html(fields)

        assert "checked('name_prefix', 'O\\'Brien')" in html

    def test_groups_emitted_in_display_order(self):
        fields = [
            _field("first_name", RespondentFieldGroup.NAME_AND_CONTACT, 0),
            _field("eligible", RespondentFieldGroup.ELIGIBILITY, 0, field_type=FieldType.BOOL),
        ]
        html = generate_starter_form_html(fields)

        eligibility_label = str(GROUP_LABELS[RespondentFieldGroup.ELIGIBILITY])
        contact_label = str(GROUP_LABELS[RespondentFieldGroup.NAME_AND_CONTACT])
        assert html.find(f"<h2>{eligibility_label}</h2>") < html.find(f"<h2>{contact_label}</h2>")

    def test_sort_order_within_group(self):
        fields = [
            _field("second", RespondentFieldGroup.NAME_AND_CONTACT, 20),
            _field("first", RespondentFieldGroup.NAME_AND_CONTACT, 10),
        ]
        html = generate_starter_form_html(fields)

        assert html.find('name="first"') < html.find('name="second"')

    def test_empty_groups_suppressed(self):
        fields = [_field("note", RespondentFieldGroup.OTHER, 0)]
        html = generate_starter_form_html(fields)

        assert str(GROUP_LABELS[RespondentFieldGroup.ELIGIBILITY]) not in html
        assert str(GROUP_LABELS[RespondentFieldGroup.OTHER]) in html

    def test_group_label_uses_group_labels_mapping(self):
        fields = [_field("first_name", RespondentFieldGroup.NAME_AND_CONTACT, 0)]
        html = generate_starter_form_html(fields)

        assert f"<h2>{GROUP_LABELS[RespondentFieldGroup.NAME_AND_CONTACT]}</h2>" in html

    def test_effective_field_type_honoured_for_fixed_fields(self):
        fields = [_field("eligible", RespondentFieldGroup.ELIGIBILITY, 0, is_fixed=True)]
        html = generate_starter_form_html(fields)

        assert ('<input type="radio" name="eligible" value="yes" {{ checked(\'eligible\', \'yes\') }}>') in html
        assert "<legend>Eligible</legend>" in html

    def test_required_attribute_on_required_text_field(self):
        fields = [_field("email", RespondentFieldGroup.NAME_AND_CONTACT, 0, field_type=FieldType.EMAIL)]
        html = generate_starter_form_html(fields, required_field_keys={"email"})

        assert ('<input type="email" id="email" name="email" value="{{ value(\'email\') }}" required>') in html

    def test_required_dropdown_omits_placeholder_and_marks_required(self):
        fields = [
            _field(
                "geo",
                RespondentFieldGroup.ADDRESS,
                0,
                field_type=FieldType.CHOICE_DROPDOWN,
                options=[ChoiceOption(value="North")],
            ),
        ]
        html = generate_starter_form_html(fields, required_field_keys={"geo"})

        assert '<select id="geo" name="geo" required>' in html
        assert '<option value="">' not in html

    def test_render_round_trip_substitutes_tokens(self):
        fields = [_field("first_name", RespondentFieldGroup.NAME_AND_CONTACT, 0)]
        starter = generate_starter_form_html(fields)
        rendered = RegistrationPageHtml(
            registration_page_id=uuid.uuid4(),
            form_html=starter,
        ).render(RenderContext(csrf_form_element="<csrf>", form_action="/r/submit"))

        assert "<csrf>" in rendered
        assert '<form action="/r/submit"' in rendered
        assert "{{ form_action }}" not in rendered
        assert "{{ csrf_form_element }}" not in rendered

    def test_generated_html_passes_readiness_check(self):
        fields = [_field("first_name", RespondentFieldGroup.NAME_AND_CONTACT, 0)]
        starter = generate_starter_form_html(fields)
        html = RegistrationPageHtml(registration_page_id=uuid.uuid4(), form_html=starter)

        assert html.readiness_problems() == []

    def test_realistic_schema_shape(self):
        fields = [
            _field("eligible", RespondentFieldGroup.ELIGIBILITY, 0, is_fixed=True),
            _field("can_attend", RespondentFieldGroup.ELIGIBILITY, 10, is_fixed=True),
            _field("email", RespondentFieldGroup.NAME_AND_CONTACT, 0, field_type=FieldType.EMAIL, is_fixed=True),
            _field("first_name", RespondentFieldGroup.NAME_AND_CONTACT, 10),
            _field("last_name", RespondentFieldGroup.NAME_AND_CONTACT, 20),
            _field(
                "gender",
                RespondentFieldGroup.ABOUT_YOU,
                0,
                field_type=FieldType.CHOICE_RADIO,
                options=[ChoiceOption(value="Female"), ChoiceOption(value="Male")],
            ),
            _field(
                "geo_bucket",
                RespondentFieldGroup.ABOUT_YOU,
                10,
                field_type=FieldType.CHOICE_DROPDOWN,
                options=[ChoiceOption(value="North"), ChoiceOption(value="South")],
            ),
        ]
        html = generate_starter_form_html(fields)

        for key in ("eligible", "can_attend", "email", "first_name", "last_name", "gender", "geo_bucket"):
            assert f'name="{key}"' in html
            assert f"{{{{ field_errors('{key}') }}}}" in html
        for value in ("Female", "Male", "North", "South"):
            assert f'value="{value}"' in html
        eligibility_pos = html.find(str(GROUP_LABELS[RespondentFieldGroup.ELIGIBILITY]))
        contact_pos = html.find(str(GROUP_LABELS[RespondentFieldGroup.NAME_AND_CONTACT]))
        about_pos = html.find(str(GROUP_LABELS[RespondentFieldGroup.ABOUT_YOU]))
        assert eligibility_pos < contact_pos < about_pos
