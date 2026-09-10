"""ABOUTME: Unit tests for region-aware locale selection
ABOUTME: Verifies get_locale() preserves Accept-Language region tags like en-GB"""

import pytest
from flask import Flask

from opendlp.entrypoints.extensions import get_locale, html_lang
from opendlp.entrypoints.flask_app import create_app


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> Flask:
    # Pin the supported languages so tests are independent of local .env settings.
    monkeypatch.setenv("SUPPORTED_LANGUAGES", "en,fr,es,de,hu")
    return create_app("testing")


class TestGetLocaleBrowserDetection:
    """Locale fallback path: browser Accept-Language drives both base language and region."""

    def test_plain_en_stays_en(self, app: Flask) -> None:
        with app.test_request_context(headers=[("Accept-Language", "en")]):
            assert get_locale() == "en"

    def test_en_gb_has_case_corrected(self, app: Flask) -> None:
        with app.test_request_context(headers=[("Accept-Language", "en-GB")]):
            assert get_locale() == "en_GB"

    def test_en_us_has_case_corrected(self, app: Flask) -> None:
        with app.test_request_context(headers=[("Accept-Language", "en-US")]):
            assert get_locale() == "en_US"

    def test_quality_ranked_region_preferred_over_bare(self, app: Flask) -> None:
        with app.test_request_context(headers=[("Accept-Language", "en-GB,en;q=0.9")]):
            assert get_locale() == "en_GB"

    def test_region_for_non_english_base(self, app: Flask) -> None:
        with app.test_request_context(headers=[("Accept-Language", "fr-CA,fr;q=0.9")]):
            assert get_locale() == "fr_CA"

    def test_unsupported_base_falls_back_to_first(self, app: Flask) -> None:
        # ja is not supported; fall back to first supported ("en"), and since the
        # browser didn't express a region for en, it stays bare.
        with app.test_request_context(headers=[("Accept-Language", "ja-JP")]):
            assert get_locale() == "en"


class TestGetLocaleUserPreferences:
    """Explicit preferences still win, but pick up a region from the browser when available."""

    def test_url_param_gains_region_from_browser(self, app: Flask) -> None:
        with app.test_request_context(
            "/?lang=en",
            headers=[("Accept-Language", "en-GB")],
        ):
            assert get_locale() == "en_GB"

    def test_session_preference_gains_region_from_browser(self, app: Flask) -> None:
        with app.test_request_context(headers=[("Accept-Language", "en-GB")]) as ctx:
            ctx.session["language"] = "en"
            assert get_locale() == "en_GB"

    def test_preference_without_matching_browser_region_stays_bare(self, app: Flask) -> None:
        # User picked Spanish but the browser only advertises English — no es region available.
        with app.test_request_context(
            "/?lang=es",
            headers=[("Accept-Language", "en-GB")],
        ):
            assert get_locale() == "es"


class TestHtmlLang:
    """The `lang` attribute needs a BCP 47 tag, which is not what get_locale returns."""

    def test_bare_language_is_unchanged(self, app: Flask) -> None:
        with app.test_request_context(headers=[("Accept-Language", "hu")]):
            assert html_lang() == "hu"

    def test_region_separator_becomes_a_hyphen(self, app: Flask) -> None:
        # get_locale() gives the gettext form "en_GB"; HTML wants "en-GB".
        with app.test_request_context(headers=[("Accept-Language", "en-GB")]):
            assert get_locale() == "en_GB"
            assert html_lang() == "en-GB"

    def test_outside_a_request_it_falls_back_instead_of_raising(self, app: Flask) -> None:
        """The email templates render in an app context with no request. get_locale()
        reads request.args, so calling it there raises "Working outside of request
        context" — which would break every outgoing email."""
        with app.app_context():
            assert html_lang() == "en"
