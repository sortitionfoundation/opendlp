# ABOUTME: Component tests for the lang attribute on every base template
# ABOUTME: A page served in Hungarian inside <html lang="en"> is a WCAG 3.1.1 failure

import re
from pathlib import Path

import pytest
from flask import Flask, render_template

# Every base template that produces a page a person reads in the browser. Each
# renders standalone, so no route or fixture is needed to check its <html> tag.
APP_BASE_TEMPLATES = ("base.html", "base_public.html", "backoffice/base.html")

TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates"
HTML_TAG = re.compile(r"<html[^>]*>")


@pytest.fixture
def multilingual_app(app: Flask) -> Flask:
    """tests/conftest.py scrubs SUPPORTED_LANGUAGES, so the suite runs on
    config.py's en,es,fr,de default and get_locale() would refuse "hu". The
    autouse _restore_shared_app_state fixture puts the config back."""
    app.config["LANGUAGES"] = ["en", "hu"]
    return app


@pytest.mark.parametrize("template", APP_BASE_TEMPLATES)
class TestLangFollowsTheNegotiatedLocale:
    def test_hungarian_request_gets_lang_hu(self, multilingual_app: Flask, template: str) -> None:
        with multilingual_app.test_request_context(headers=[("Accept-Language", "hu")]):
            assert 'lang="hu"' in HTML_TAG.search(render_template(template)).group()

    def test_english_request_gets_lang_en(self, multilingual_app: Flask, template: str) -> None:
        with multilingual_app.test_request_context(headers=[("Accept-Language", "en")]):
            assert 'lang="en"' in HTML_TAG.search(render_template(template)).group()

    def test_region_is_a_hyphen_not_an_underscore(self, multilingual_app: Flask, template: str) -> None:
        """get_locale() returns the gettext form "en_GB"; BCP 47 wants "en-GB",
        and a browser given the underscore ignores the attribute."""
        with multilingual_app.test_request_context(headers=[("Accept-Language", "en-GB")]):
            assert 'lang="en-GB"' in HTML_TAG.search(render_template(template)).group()


class TestNoTemplateHardcodesItsLanguage:
    """The three bases were all born with lang="en" hardcoded, which held even
    once the page body was Hungarian. A base added later must not repeat it."""

    def test_only_the_email_templates_carry_a_literal_lang(self) -> None:
        hardcoded = sorted(
            str(path.relative_to(TEMPLATES_DIR))
            for path in TEMPLATES_DIR.rglob("*.html")
            if re.search(r"<html[^>]*\blang=\"[a-zA-Z-]+\"", path.read_text())
        )
        # An email's language is fixed when it is sent, not negotiated per
        # request, and it renders with no request context to negotiate from.
        # See docs/agent/898-translate-skill/page-language.md.
        assert hardcoded == [
            "emails/account_reenabled.html",
            "emails/assembly_role_assigned.html",
            "emails/email_confirmation.html",
            "emails/password_reset.html",
            "emails/user_invite.html",
        ]
