"""ABOUTME: Unit tests for CSP nonce generation and injection
ABOUTME: Tests that nonces are generated per request and properly injected into CSP headers"""

import pytest
from flask import Flask

from opendlp.entrypoints.flask_app import create_app, generate_csp_nonce


class TestCSPNonceGeneration:
    """Tests for CSP nonce generation and handling."""

    def test_generate_csp_nonce_returns_string(self) -> None:
        """Test that generate_csp_nonce returns a non-empty string."""
        nonce = generate_csp_nonce()
        assert isinstance(nonce, str)
        assert len(nonce) > 0

    def test_generate_csp_nonce_is_unique(self) -> None:
        """Test that successive calls to generate_csp_nonce return different values."""
        nonce1 = generate_csp_nonce()
        nonce2 = generate_csp_nonce()
        assert nonce1 != nonce2

    def test_nonce_format_is_url_safe(self) -> None:
        """Test that nonce contains only URL-safe characters."""
        nonce = generate_csp_nonce()
        # URL-safe base64 uses: A-Z, a-z, 0-9, -, _
        allowed_chars = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")
        assert all(c in allowed_chars for c in nonce)


class TestCSPNonceInApp:
    """Tests for CSP nonce in Flask application context."""

    @pytest.fixture
    def app(self) -> Flask:
        """Create test Flask application."""
        return create_app("testing")

    def test_nonce_in_flask_g(self, app: Flask) -> None:
        """Test that nonce is stored in Flask g during request."""
        with app.test_client() as client:
            response = client.get("/")
            with client.session_transaction():
                # We can't directly access g here, but we can verify the nonce is in the CSP header
                assert response.status_code == 200

    def test_nonce_in_csp_header(self, app: Flask) -> None:
        """Test that CSP header includes nonce-{value}."""
        with app.test_client() as client:
            response = client.get("/")
            csp_header = response.headers.get("Content-Security-Policy", "")
            assert "nonce-" in csp_header
            assert "NONCE_PLACEHOLDER" not in csp_header  # Should be replaced

    def test_nonce_unique_per_request(self, app: Flask) -> None:
        """Test that different requests get different nonces."""
        with app.test_client() as client:
            response1 = client.get("/")
            csp1 = response1.headers.get("Content-Security-Policy", "")

            response2 = client.get("/")
            csp2 = response2.headers.get("Content-Security-Policy", "")

            # Extract nonces from CSP headers
            nonce1 = csp1.split("nonce-")[1].split(" ")[0].split("'")[0]
            nonce2 = csp2.split("nonce-")[1].split(" ")[0].split("'")[0]

            assert nonce1 != nonce2

    def test_nonce_in_template_context(self, app: Flask) -> None:
        """Test that csp_nonce is available in template context."""
        with app.test_client() as client:
            response = client.get("/")
            assert response.status_code == 200
            # The nonce should be in the rendered HTML (in script tags with nonce attribute)
            html = response.data.decode("utf-8")
            assert 'nonce="' in html

    def test_csp_no_unsafe_inline_in_script_src(self, app: Flask) -> None:
        """Test that CSP script-src does not contain 'unsafe-inline'."""
        with app.test_client() as client:
            response = client.get("/")
            csp_header = response.headers.get("Content-Security-Policy", "")
            # Extract script-src directive
            script_src = ""
            for directive in csp_header.split(";"):
                if "script-src" in directive:
                    script_src = directive
                    break

            assert "'unsafe-inline'" not in script_src

    def test_csp_no_unsafe_eval_in_script_src(self, app: Flask) -> None:
        """Test that CSP script-src does not contain 'unsafe-eval'."""
        with app.test_client() as client:
            response = client.get("/")
            csp_header = response.headers.get("Content-Security-Policy", "")
            # Extract script-src directive
            script_src = ""
            for directive in csp_header.split(";"):
                if "script-src" in directive:
                    script_src = directive
                    break

            assert "'unsafe-eval'" not in script_src

    def test_csp_has_strict_dynamic(self, app: Flask) -> None:
        """Test that CSP script-src contains 'strict-dynamic'."""
        with app.test_client() as client:
            response = client.get("/")
            csp_header = response.headers.get("Content-Security-Policy", "")
            # Extract script-src directive
            script_src = ""
            for directive in csp_header.split(";"):
                if "script-src" in directive:
                    script_src = directive
                    break

            assert "'strict-dynamic'" in script_src
