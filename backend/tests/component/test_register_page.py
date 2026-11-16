"""ABOUTME: Component tests for the words around the sign-up page's fields
ABOUTME: The invite code's helper text and its support link, and the password requirements and their live ticks"""

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


def _rules(html: str) -> dict[str, tuple[dict[str, str], str]]:
    """Each line of the password rules by its key: the <li>'s attributes, and what is inside it."""
    block = _tag(html, r'<div id="password-requirements"[\s\S]*?</ul>')
    lines = {}
    for attrs, body in re.findall(r"<li([^>]*)>([\s\S]*?)</li>", block):
        attributes = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        lines[attributes.get("data-password-rule", "")] = (attributes, body)
    return lines


def _icon(app: Flask, macro: str, **kwargs: str) -> str:
    """The markup an icon macro draws, as the page draws it."""
    args = ", ".join(f'{name}="{value}"' for name, value in kwargs.items())
    source = f'{{% from "backoffice/components/icons.html" import {macro} %}}{{{{ {macro}({args}) }}}}'
    with app.app_context():
        return app.jinja_env.from_string(source).render()


def _holder(body: str, markup: str) -> str:
    """The start tag of the <span> that holds `markup`."""
    match = re.search(r"(<span[^>]*>)\s*" + re.escape(markup), body)
    assert match is not None, f"no <span> holds {markup[:60]}"
    return match.group(1)


class TestLivePasswordRules:
    """Every rule starts neutral; the page's script ticks it while the password meets it."""

    def test_every_line_carries_its_key_and_where_it_is_checked(self, client: FlaskClient):
        rules = _rules(_page(client))

        assert list(rules) == ["length", "not-numbers-only", "not-common", "not-similar"]
        assert {key: attrs["data-live-check"] for key, (attrs, _body) in rules.items()} == {
            "length": "browser",
            "not-numbers-only": "browser",
            "not-common": "server",
            "not-similar": "server",
        }

    def test_the_length_line_carries_the_validators_numbers(self, client: FlaskClient):
        attrs, _body = _rules(_page(client))["length"]

        assert (attrs["data-min-length"], attrs["data-max-length"]) == ("10", "256")

    def test_only_the_length_line_carries_numbers(self, client: FlaskClient):
        for key, (attrs, _body) in _rules(_page(client)).items():
            if key != "length":
                assert "data-min-length" not in attrs
                assert "data-max-length" not in attrs

    def test_every_line_starts_with_the_hollow_circle(self, app: Flask, client: FlaskClient):
        circle = _icon(app, "icon_circle_small", classes="w-3.5 h-3.5")

        for _attrs, body in _rules(_page(client)).values():
            holder = _holder(body, circle)
            assert 'x-show="!met($el)"' in holder
            assert "x-cloak" not in holder

    def test_no_line_shows_a_tick_until_the_script_runs(self, app: Flask, client: FlaskClient):
        """x-cloak keeps the tick hidden without JavaScript, so a page without it shows circles only."""
        tick = _icon(app, "icon_check", classes="w-3.5 h-3.5", style="color: var(--color-success-text);")

        for _attrs, body in _rules(_page(client)).values():
            holder = _holder(body, tick)
            assert 'x-show="met($el)"' in holder
            assert "x-cloak" in holder

    def test_each_line_has_its_state_for_screen_readers_once_the_script_runs(self, client: FlaskClient):
        for _attrs, body in _rules(_page(client)).values():
            assert re.search(r'<span class="sr-only" x-show="met\(\$el\)" x-cloak> \(met\)</span>', body)
            assert re.search(r'<span class="sr-only" x-show="!met\(\$el\)" x-cloak> \(not met yet\)</span>', body)

    def test_the_component_holds_the_fields_the_server_compares_the_password_with(self, client: FlaskClient):
        html = _page(client)

        start = _tag(html, r'<div[^>]*x-data="passwordRules"[^>]*>')
        assert '@input="changed($event)"' in start
        assert 'data-check-url="/auth/password-check"' in start
        assert re.search(r'data-csrf-token="[^"]+"', start)
        inside = html[html.find(start) : html.find('id="password-requirements"')]
        for name in ("email", "password"):
            assert f'name="{name}"' in inside
        names = html[html.find(start) :]
        for name in ("first_name", "last_name"):
            assert f'name="{name}"' in names[: names.find("Data Agreement")]
