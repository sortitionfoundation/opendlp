"""ABOUTME: Component tests for the words around the sign-up page's fields
ABOUTME: Invite code help, password rules, the survey's sources question and the beta disclaimer's tickbox"""

import re

import pytest
from flask import Flask
from flask.testing import FlaskClient

from opendlp.feature_flags import reload_flags


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
    "By registering an account I understand that currently OpenDLP is only open for beta testing, therefore using "
    "it in actual democratic lottery processes and/or with actual personal datasets is forbidden. I agree to "
    "contact Sortition Foundation directly before using OpenDLP for actual projects described earlier. I also "
    "consent to Sortition Foundation contacting me to learn more about my usage patterns and user needs."
)


class TestBetaDisclaimer:
    """The beta disclaimer sits under the data agreement, with a required tickbox of its own."""

    def test_the_disclaimer_reads_as_written(self, client: FlaskClient):
        paragraph = _tag(_page(client), r'<p id="beta-disclaimer-text"[^>]*>[^<]*</p>')

        assert BETA_DISCLAIMER in " ".join(paragraph.split())

    def test_the_disclaimer_and_its_tickbox_follow_the_data_agreement(self, client: FlaskClient):
        html = _page(client)

        data_agreement = html.find('name="accept_data_agreement"')
        disclaimer = html.find('id="beta-disclaimer-text"')
        tickbox = html.find('name="accept_beta_disclaimer"')
        assert -1 not in (data_agreement, disclaimer, tickbox)
        assert data_agreement < disclaimer < tickbox < html.find('value="email"', tickbox)

    def test_the_tickbox_has_a_short_label_marked_required(self, client: FlaskClient):
        tickbox = _tag(_page(client), r'<input[^>]*name="accept_beta_disclaimer"[\s\S]*?</label>')

        assert 'type="checkbox"' in tickbox
        label = _tag(tickbox, r'<span class="checkbox-label">[\s\S]*')
        assert "Accept beta disclaimer" in label
        assert "*</span>" in label

    def test_the_tickbox_is_described_by_the_disclaimer(self, client: FlaskClient):
        field = _tag(_page(client), r'<input[^>]*name="accept_beta_disclaimer"[^>]*>')

        assert 'aria-describedby="beta-disclaimer-text"' in field

    def test_an_unticked_disclaimer_is_refused_under_its_tickbox(self, client: FlaskClient, open_signup):
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
        html = response.get_data(as_text=True)

        assert response.status_code == 200
        error = _tag(html, r'<p id="accept_beta_disclaimer-error"[^>]*>[^<]*</p>')
        assert "You must accept the beta disclaimer to register" in error
        field = _tag(html, r'<input[^>]*name="accept_beta_disclaimer"[^>]*>')
        assert 'aria-invalid="true"' in field
        # One attribute naming both, or the second would be ignored
        assert 'aria-describedby="accept_beta_disclaimer-error beta-disclaimer-text"' in field
        # The data agreement the user did tick stays ticked
        assert re.search(r"\bchecked\b", _tag(html, r'<input[^>]*name="accept_data_agreement"[^>]*>'))
