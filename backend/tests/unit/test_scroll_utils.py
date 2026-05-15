"""ABOUTME: Unit tests for scroll_utils module
ABOUTME: Tests redirect_preserving_scroll function for scroll position preservation"""

import pytest
from flask import Flask
from flask.testing import FlaskClient

from opendlp.entrypoints.scroll_utils import redirect_preserving_scroll


class TestRedirectPreservingScroll:
    @pytest.fixture
    def app(self) -> Flask:
        """Create a minimal Flask app for testing."""
        app = Flask(__name__)
        app.config["TESTING"] = True
        return app

    @pytest.fixture
    def client(self, app: Flask) -> FlaskClient:
        return app.test_client()

    def test_redirect_without_scroll_param(self, app: Flask) -> None:
        """When no scroll param in request, redirect URL is unchanged."""
        with app.test_request_context("/some/path"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url"

    def test_redirect_with_scroll_param(self, app: Flask) -> None:
        """When scroll param exists, it's appended to redirect URL."""
        with app.test_request_context("/some/path?scroll=500"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url?scroll=500"

    def test_redirect_with_scroll_param_and_existing_query_string(self, app: Flask) -> None:
        """When scroll param exists and target URL has query string, scroll is appended with &."""
        with app.test_request_context("/some/path?scroll=750"):
            response = redirect_preserving_scroll("/target/url?source=csv")
            assert response.status_code == 302
            assert response.location == "/target/url?source=csv&scroll=750"

    def test_redirect_with_zero_scroll(self, app: Flask) -> None:
        """Scroll value of 0 is preserved (user at top of page)."""
        with app.test_request_context("/some/path?scroll=0"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url?scroll=0"

    def test_redirect_with_large_scroll_value(self, app: Flask) -> None:
        """Large scroll values are preserved correctly."""
        with app.test_request_context("/some/path?scroll=99999"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url?scroll=99999"

    def test_redirect_with_other_params_preserved(self, app: Flask) -> None:
        """Other request params don't affect scroll preservation."""
        with app.test_request_context("/some/path?other=value&scroll=300&another=param"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url?scroll=300"

    def test_redirect_with_empty_scroll_param(self, app: Flask) -> None:
        """Empty scroll param is treated as no scroll (falsy value)."""
        with app.test_request_context("/some/path?scroll="):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            # Empty string is falsy, so no scroll param added
            assert response.location == "/target/url"

    def test_redirect_preserves_target_url_hash(self, app: Flask) -> None:
        """Hash fragment in target URL is preserved."""
        with app.test_request_context("/some/path?scroll=200"):
            response = redirect_preserving_scroll("/target/url#section")
            assert response.status_code == 302
            assert response.location == "/target/url?scroll=200#section"

    def test_redirect_with_complex_target_url(self, app: Flask) -> None:
        """Complex target URL with multiple params works correctly."""
        with app.test_request_context("/some/path?scroll=100"):
            response = redirect_preserving_scroll("/target/url?source=csv&mode=edit")
            assert response.status_code == 302
            assert response.location == "/target/url?source=csv&mode=edit&scroll=100"

    def test_redirect_with_non_numeric_scroll_is_ignored(self, app: Flask) -> None:
        """Non-numeric scroll values are ignored for security."""
        with app.test_request_context("/some/path?scroll=abc"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url"

    def test_redirect_with_negative_scroll_is_ignored(self, app: Flask) -> None:
        """Negative scroll values are ignored (isdigit returns False for -)."""
        with app.test_request_context("/some/path?scroll=-100"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url"

    def test_redirect_with_injection_attempt_is_ignored(self, app: Flask) -> None:
        """Potential injection attempts in scroll param are ignored."""
        with app.test_request_context("/some/path?scroll=100&evil=true"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            # Only the numeric scroll value should be preserved
            assert response.location == "/target/url?scroll=100"
        # Try actual malicious value
        with app.test_request_context("/some/path?scroll=<script>"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url"

    def test_redirect_with_external_url_in_scroll_is_ignored(self, app: Flask) -> None:
        """Attempts to inject external URLs via scroll param are rejected."""
        # Full URL attempt
        with app.test_request_context("/some/path?scroll=https://evil.com"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url"
            assert "evil.com" not in response.location

        # Protocol-relative URL attempt
        with app.test_request_context("/some/path?scroll=//evil.com"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url"
            assert "evil.com" not in response.location

    def test_redirect_with_url_encoded_injection_is_ignored(self, app: Flask) -> None:
        """URL-encoded injection attempts in scroll param are rejected."""
        # Encoded newline + Location header injection attempt
        with app.test_request_context("/some/path?scroll=100%0d%0aLocation:http://evil.com"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert "evil.com" not in response.location

        # Encoded characters that look like numbers
        with app.test_request_context("/some/path?scroll=%31%30%30"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            # URL-encoded "100" is decoded by Flask, so this should work
            # but if it doesn't decode, it should be rejected
            # Either way, no external redirect should occur
            assert "evil" not in response.location.lower()

    def test_redirect_rejects_scroll_with_path_traversal(self, app: Flask) -> None:
        """Path traversal attempts in scroll param are rejected."""
        with app.test_request_context("/some/path?scroll=../../../etc/passwd"):
            response = redirect_preserving_scroll("/target/url")
            assert response.status_code == 302
            assert response.location == "/target/url"
            assert "etc" not in response.location
            assert "passwd" not in response.location
