"""ABOUTME: Component tests for the words around the sign-up page's fields
ABOUTME: The invite code's helper text and its link to the support address"""

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
