# ABOUTME: Component tests for the public home page served at /
# ABOUTME: Checks it renders for every visitor, links to the account pages, and offers signed-in users their dashboard

import re
from typing import Any

import flask_babel
import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from opendlp.feature_flags import default_dashboard_endpoint

SLOGAN_MSGID = "Bringing %(highlight)s to sortition"


def slogan_parts(html: str) -> list[str]:
    """The text of the heading's three spans: before the word, the word, after it."""
    heading = html[html.index("<h1") : html.index("</h1>")]
    return [part.strip() for part in re.findall(r"<span[^>]*>(.*?)</span>", heading, re.DOTALL)]


class SloganTranslations:
    """Wraps the real translations, swapping in one translation of the slogan."""

    def __init__(self, real: Any, slogan: str) -> None:
        self.real = real
        self.slogan = slogan

    def ugettext(self, message: str) -> str:
        return self.slogan if message == SLOGAN_MSGID else str(self.real.ugettext(message))

    def __getattr__(self, name: str) -> Any:
        return getattr(self.real, name)


class TestHomePage:
    def test_renders_for_anonymous_visitor(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "Bringing" in response.text
        assert "simplicity" in response.text
        assert "to sortition" in response.text
        assert "How does OpenDLP work?" in response.text
        assert "Key benefits" in response.text
        assert "Who is OpenDLP for?" in response.text

    def test_does_not_redirect_signed_in_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/")
        assert response.status_code == 200
        assert "Bringing" in response.text

    def test_links_to_sign_in_and_registration(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert 'href="/auth/login"' in response.text
        assert 'href="/auth/register"' in response.text

    def test_uses_the_opendlp_logo_files(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert "img/opendlp-logo-light.svg" in response.text
        assert "img/opendlp-small-sized-logo.svg" in response.text
        assert "img/opendlp-favicon.svg" in response.text

    def test_footer_links_to_known_destinations(self, client: FlaskClient, app: Flask) -> None:
        response = client.get("/")
        assert 'href="#how-it-works"' in response.text
        assert 'id="how-it-works"' in response.text
        assert f'href="mailto:{app.config["SUPPORT_EMAIL"]}"' in response.text
        assert "https://github.com/sortitionfoundation/opendlp" in response.text
        assert f'href="{app.config["HELP_SITE_HOME"]}"' in response.text
        assert f'href="{app.config["KNOWLEDGE_HUB_URL"]}"' in response.text
        assert 'href="#"' not in response.text

    def test_footer_drops_links_without_a_page(self, client: FlaskClient) -> None:
        response = client.get("/")
        for label in ("Documentation", "Release notes", "Report a vulnerability", "Privacy policy", "Terms of use"):
            assert label not in response.text

    def test_footer_names_the_legal_entity_and_licence(self, client: FlaskClient) -> None:
        response = client.get("/")
        footer = response.text[response.text.index("<footer") :]
        assert "Sortition Europe" in footer
        assert "Open source under the Apache License 2.0" in footer
        assert "LEGAL ENTITY" not in footer
        assert "REGISTRATION NUMBER" not in footer

    def test_intro_splits_the_complexity_sentence(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert "<p>Democratic lotteries can be technically complex to implement.</p>" in response.text
        assert "<p>There are few public resources available to support them.</p>" in response.text

    def test_hero_actions_are_primary_buttons(self, client: FlaskClient) -> None:
        response = client.get("/")
        hero_start = response.text.index("<h1")
        hero = response.text[hero_start : response.text.index("</section>", hero_start)]
        assert hero.count("btn--primary") == 2
        assert "btn--secondary" not in hero

    def test_slogan_splits_around_the_highlighted_word(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert slogan_parts(response.text) == ["Bringing", "simplicity", "to sortition"]

    @pytest.mark.parametrize(
        ("translation", "expected"),
        [
            ("%(highlight)s for sortition", ["", "simplicity", "for sortition"]),
            ("Sortition with %(highlight)s", ["Sortition with", "simplicity", ""]),
            ("A %(highlight)s B", ["A", "simplicity", "B"]),
        ],
    )
    def test_slogan_split_follows_where_a_translation_puts_the_word(
        self, client: FlaskClient, monkeypatch: pytest.MonkeyPatch, translation: str, expected: list[str]
    ) -> None:
        real_get_translations = flask_babel.get_translations
        monkeypatch.setattr(
            flask_babel, "get_translations", lambda: SloganTranslations(real_get_translations(), translation)
        )
        response = client.get("/")
        assert slogan_parts(response.text) == expected

    def test_header_has_home_link_sign_in_and_help(self, client: FlaskClient, app: Flask) -> None:
        response = client.get("/")
        header_start = response.text.index("<section")
        header = response.text[header_start : response.text.index("</section>", header_start)]
        assert 'href="/"' in header
        assert 'href="/auth/login"' in header
        assert f'href="{app.config["HELP_SITE_HOME"]}' in header

    def test_header_offers_dashboard_to_signed_in_user(self, logged_in_user: FlaskClient, app: Flask) -> None:
        """The button goes to the user's default dashboard, in place of Sign in."""
        response = logged_in_user.get("/")
        header_start = response.text.index("<section")
        header = response.text[header_start : response.text.index("</section>", header_start)]
        with app.test_request_context():
            dashboard_url = url_for(default_dashboard_endpoint())
        assert f'href="{dashboard_url}"' in header
        assert "Dashboard" in header
        assert 'href="/auth/login"' not in header
