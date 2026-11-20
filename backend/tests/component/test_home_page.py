# ABOUTME: Component tests for the public home page served at /
# ABOUTME: Checks it renders for every visitor, links to the account pages, and offers signed-in users their dashboard

import re
from html.parser import HTMLParser
from typing import Any

import flask_babel
import pytest
from flask import Flask, url_for
from flask.testing import FlaskClient

from opendlp.feature_flags import default_dashboard_endpoint

SLOGAN_MSGID = "Bringing %(highlight)s to Sortition"

_VOID_ELEMENTS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class DemoToggle(HTMLParser):
    """The hero demo's pause button: its attributes, the tags inside it, and the attributes of each element around it."""

    def __init__(self) -> None:
        super().__init__()
        self.open: list[tuple[str, dict[str, str | None]]] = []
        self.attrs: dict[str, str | None] = {}
        self.ancestors: list[dict[str, str | None]] = []
        self.inner: list[str] = []
        self.depth = 0  # how deep inside the button the parser is; 0 outside it

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if self.depth:
            self.inner.append(self.get_starttag_text() or "")
            if tag not in _VOID_ELEMENTS:
                self.depth += 1
        elif not self.attrs and "data-hero-demo-toggle" in attributes:
            self.attrs = attributes
            self.ancestors = [element for _, element in self.open]
            self.depth = 1
        if tag not in _VOID_ELEMENTS:
            self.open.append((tag, attributes))

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # A self-closing tag, such as an icon's <rect/>, opens nothing.
        if self.depth:
            self.inner.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if self.depth and tag not in _VOID_ELEMENTS:
            self.depth -= 1
        # An element left open, such as a <p> or <li>, is closed by its parent's end tag.
        for index in range(len(self.open) - 1, -1, -1):
            if self.open[index][0] == tag:
                del self.open[index:]
                break


def demo_toggle(html: str) -> DemoToggle:
    toggle = DemoToggle()
    toggle.feed(html)
    assert toggle.attrs, "no element carries data-hero-demo-toggle"
    return toggle


def slogan_parts(html: str) -> list[str]:
    """The heading's text in three parts: before the highlighted word, the word, after it."""
    heading = html[html.index("<h1") : html.index("</h1>")]
    heading = heading[heading.index(">") + 1 :]
    match = re.fullmatch(r"(.*?)<span[^>]*>(.*?)</span>(.*)", heading, re.DOTALL)
    assert match is not None
    return [part.strip() for part in match.groups()]


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
        assert "Simplicity" in response.text
        assert "to Sortition" in response.text
        assert "Sortition is complicated" in response.text
        assert "OpenDLP makes it simple" in response.text
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
        assert "img/opendlp-small-sized-logo.svg" in response.text
        assert "img/opendlp-favicon.svg" in response.text
        assert "img/opendlp-logo-light.svg" not in response.text

    def test_hero_plays_the_product_demo(self, client: FlaskClient) -> None:
        """The demo's five screens are in the hero, and its script loads under the page's nonce."""
        response = client.get("/")
        assert "data-hero-demo" in response.text
        for scene in ("projects", "create", "targets", "selection", "dashboard"):
            assert f'data-scene="{scene}"' in response.text
        script = re.search(r"<script[^>]*js/hero-demo\.js[^>]*>", response.text)
        assert script is not None
        assert re.search(r'nonce="[^"]+"', script.group(0))
        # every target the script looks for is a real attribute, not escaped text
        for name in ("create-project", "title", "size", "submit-create", "min-1", "max-3", "run", "modal"):
            assert f'data-demo="{name}"' in response.text
        assert "&#34;" not in response.text[response.text.index("data-hero-demo") :]
        assert "A short demonstration of OpenDLP" in response.text

    def test_hero_demo_has_a_pause_button_outside_its_hidden_frame(self, client: FlaskClient) -> None:
        """A toggle button pauses the demo (WCAG 2.2.2), reachable by assistive technology.

        Its name stays the same and aria-pressed carries the state. It sits in the demo but outside the
        aria-hidden frame, and is hidden until the script plays the demo: without JavaScript the demo
        rests on its last screen and there is nothing to pause.
        """
        response = client.get("/")
        toggle = demo_toggle(response.text)
        assert toggle.attrs["type"] == "button"
        assert toggle.attrs["aria-label"] == "Pause the demo"
        assert toggle.attrs["aria-pressed"] == "false"
        assert "hidden" in toggle.attrs
        assert any("data-hero-demo" in element for element in toggle.ancestors)
        assert not any(element.get("aria-hidden") == "true" for element in toggle.ancestors)
        # both icons are drawn; the stylesheet shows the one aria-pressed calls for
        inner = "".join(toggle.inner)
        assert "hero-demo__toggle-pause" in inner
        assert "hero-demo__toggle-play" in inner

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

    def test_problem_section_names_the_three_difficulties(self, client: FlaskClient) -> None:
        response = client.get("/")
        start = response.text.index('id="problem-heading"')
        section = response.text[start : response.text.index("</section>", start)]
        for title in ("Stitched together by hand", "Easy to get wrong", "Few places to learn"):
            assert title in section
        assert "But doing it well is hard." in section
        assert "We are changing that with OpenDLP." in section

    def test_hero_leads_with_create_account(self, client: FlaskClient) -> None:
        """Create account is the primary button and comes first; Contact us is secondary."""
        response = client.get("/")
        # The text column only: the demo beside it has buttons of its own.
        hero_start = response.text.index("<h1")
        hero = response.text[hero_start : response.text.index("data-hero-visual", hero_start)]
        assert hero.count("btn--primary") == 1
        assert hero.count("btn--secondary") == 1
        assert hero.index("/auth/register") < hero.index("mailto:")

    def test_hero_states_the_track_record(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert "300+" in response.text
        assert "30+" in response.text
        assert "lotteries already run in OpenDLP" in response.text

    def test_slogan_splits_around_the_highlighted_word(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert slogan_parts(response.text) == ["Bringing", "Simplicity", "to Sortition"]

    @pytest.mark.parametrize(
        ("translation", "expected"),
        [
            ("%(highlight)s for sortition", ["", "Simplicity", "for sortition"]),
            ("Sortition with %(highlight)s", ["Sortition with", "Simplicity", ""]),
            ("A %(highlight)s B", ["A", "Simplicity", "B"]),
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
