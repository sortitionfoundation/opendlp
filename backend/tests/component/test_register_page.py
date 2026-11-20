"""ABOUTME: Component tests for the words around the sign-up page's fields
ABOUTME: Invite code help, password rules, the survey's sources question and the beta disclaimer's text"""

import re
from itertools import pairwise

import pytest
from flask import Flask
from flask.testing import FlaskClient

from opendlp.feature_flags import reload_flags
from tests.fakes import FakeStore, FakeUnitOfWork


@pytest.fixture
def open_signup(monkeypatch):
    """Turn on FF_OPEN_SIGNUP for one test, restoring the flags afterwards."""
    monkeypatch.setenv("FF_OPEN_SIGNUP", "true")
    reload_flags()
    yield
    monkeypatch.delenv("FF_OPEN_SIGNUP", raising=False)
    reload_flags()


def _page(client: FlaskClient, url: str = "/auth/register") -> str:
    response = client.get(url)
    assert response.status_code == 200
    return response.get_data(as_text=True)


def _tag(html: str, pattern: str) -> str:
    match = re.search(pattern, html)
    assert match is not None, f"nothing on the page matches {pattern}"
    return match.group(0)


class TestInviteCodeHelperText:
    """With invites required, the note about invite codes is the field's helper text."""

    def test_the_note_above_the_form_is_gone(self, client: FlaskClient):
        html = _page(client)

        assert "You need an invite code to create an account" not in html

    def test_the_helper_text_sits_under_the_invite_code_field(self, client: FlaskClient):
        html = _page(client)

        helper = _tag(html, r'<p id="invite_code-help"[^>]*>[^<]*If you don\'t have one, please contact <a ')
        assert html.find('name="invite_code"') < html.find(helper) < html.find('name="email"')

    def test_the_helper_text_links_to_the_support_address(self, app: Flask, client: FlaskClient):
        link = _tag(_page(client), r"<a [^>]*>OpenDLP support</a>")

        assert f'href="mailto:{app.config["SUPPORT_EMAIL"]}"' in link

    def test_the_invite_code_field_is_described_by_its_helper_text(self, client: FlaskClient):
        field = _tag(_page(client), r'<input[^>]*name="invite_code"[^>]*>')

        assert 'aria-describedby="invite_code-help"' in field
        assert "required" in field

    def test_the_old_hint_above_the_field_is_gone(self, client: FlaskClient):
        assert "Enter your invite code to register" not in _page(client)

    def test_open_signup_keeps_the_optional_hint_without_the_support_link(self, client: FlaskClient, open_signup):
        """An optional code needs no one to ask for it, so the field keeps its own hint."""
        html = _page(client, "/auth/register/SOMECODE1")

        assert 'value="SOMECODE1"' in html
        assert "Optional — if you were given an invite code, enter it here." in html
        assert 'id="invite_code-help"' not in html
        assert "OpenDLP support</a>" not in html


class TestPasswordRequirements:
    """The password field lists its rules in the design's short form."""

    def test_the_rules_follow_your_password_must(self, client: FlaskClient):
        rules = _tag(_page(client), r'<div id="password-requirements"[\s\S]*?</ul>')

        assert "Your password must:" in rules
        lines = (
            "10–256 characters",
            "Not be numbers only",
            "Not be a commonly used password",
            "Not be too similar to your personal information",
        )
        positions = [rules.find(f"<span>{line}</span>") for line in lines]
        assert -1 not in positions
        assert positions == sorted(positions)

    def test_the_password_field_is_described_by_its_rules(self, client: FlaskClient):
        field = _tag(_page(client), r'<input[^>]*name="password"[^>]*>')

        assert 'aria-describedby="password-requirements"' in field

    def test_the_long_validator_help_texts_are_gone(self, client: FlaskClient):
        html = _page(client)

        assert "Your password must contain" not in html
        assert "Your password cannot be" not in html


class TestWhereDidYouHearAboutUs:
    """The optional survey asks where people heard about OpenDLP, from a fixed list."""

    def test_the_question_offers_its_answers_in_order(self, client: FlaskClient, open_signup):
        select = _tag(_page(client), r'<select name="survey_heard_about_us"[\s\S]*?</select>')

        labels = [label.strip() for label in re.findall(r"<option[^>]*>([^<]*)</option>", select)]
        assert labels == ["Please select", "Social media", "An event", "Forum", "Newsletter", "From a friend", "Other"]
        values = re.findall(r'<option value="([^"]*)"', select)
        assert values == ["", "social_media", "event", "forum", "newsletter", "friend", "other"]

    def test_the_question_is_the_select_label(self, client: FlaskClient, open_signup):
        label = _tag(_page(client), r'<label for="survey_heard_about_us"[^>]*>[^<]*')

        assert "Where did you hear about us?" in label

    def test_the_question_is_not_asked_without_open_signup(self, client: FlaskClient):
        assert "survey_heard_about_us" not in _page(client)


BETA_DISCLAIMER = (
    "Registration for OpenDLP is currently only open for beta testing. Please contact us if you intend to use it in "
    "actual democratic lottery processes and/or with actual personal datasets."
)


def _disclaimer(html: str) -> str:
    """The "Beta disclaimer" heading and the paragraph under it."""
    return _tag(html, r"<h2[^>]*>Beta disclaimer</h2>\s*<p[^>]*>[\s\S]*?</p>")


def _text(html: str) -> str:
    """The words of some markup, tags dropped and whitespace collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


class TestBetaDisclaimer:
    """The beta disclaimer is text under the data agreement, with nothing to tick."""

    def test_the_disclaimer_reads_as_written(self, client: FlaskClient):
        paragraph = _tag(_disclaimer(_page(client)), r"<p[^>]*>[\s\S]*?</p>")

        assert _text(paragraph) == BETA_DISCLAIMER

    def test_contact_us_links_to_the_support_address(self, app: Flask, client: FlaskClient):
        link = _tag(_disclaimer(_page(client)), r"<a [^>]*>contact us</a>")

        assert f'href="mailto:{app.config["SUPPORT_EMAIL"]}"' in link
        assert "color: var(--color-links);" in link

    def test_the_support_link_is_there_with_open_signup_too(self, app: Flask, client: FlaskClient, open_signup):
        """Open sign-up hides the invite code's helper text, the other link to support, but not this one."""
        link = _tag(_disclaimer(_page(client)), r"<a [^>]*>contact us</a>")

        assert f'href="mailto:{app.config["SUPPORT_EMAIL"]}"' in link

    def test_its_title_is_a_heading_in_the_page_outline(self, client: FlaskClient, open_signup):
        html = _page(client)
        headings = [(int(level), _text(title)) for level, title in re.findall(r"<h([1-6])[^>]*>([\s\S]*?)</h\1>", html)]

        assert (2, "Beta disclaimer") in headings
        levels = [level for level, _ in headings]
        assert levels[0] == 1
        # No level is skipped on the way down
        assert all(later <= earlier + 1 for earlier, later in pairwise(levels))

    def test_it_sits_under_the_data_agreement_and_above_the_submit_buttons(self, client: FlaskClient):
        html = _page(client)

        data_agreement = html.find('name="accept_data_agreement"')
        disclaimer = html.find(_disclaimer(html))
        assert -1 not in (data_agreement, disclaimer)
        assert data_agreement < disclaimer < html.find('value="email"', disclaimer)

    def test_there_is_nothing_to_tick(self, client: FlaskClient):
        """The data agreement's tickbox is the only one on the page."""
        tickboxes = re.findall(r'<input[^>]*type="checkbox"[^>]*>', _page(client))

        assert [_tag(tickbox, r'name="[^"]*"') for tickbox in tickboxes] == ['name="accept_data_agreement"']

    def test_a_sign_up_by_email_needs_only_the_data_agreement(
        self, client: FlaskClient, fake_store: FakeStore, open_signup
    ):
        response = client.post(
            "/auth/register",
            data={
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@example.com",
                "password": "securepassword123",  # pragma: allowlist secret
                "password_confirm": "securepassword123",  # pragma: allowlist secret
                "accept_data_agreement": "y",
            },
        )

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            user = uow.users.get_by_email("newuser@example.com")
            assert user is not None
            assert user.user_data_agreement_agreed_at is not None
