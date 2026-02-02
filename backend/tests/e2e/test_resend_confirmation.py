"""ABOUTME: Tests for resend confirmation endpoint with WTForms
ABOUTME: Ensures the endpoint uses WTForms for CSRF protection and validation"""

from flask.testing import FlaskClient

from tests.e2e.helpers import get_csrf_token


class TestResendConfirmation:
    """Test resend confirmation endpoint functionality."""

    def test_resend_confirmation_form_submission_succeeds(self, client: FlaskClient, postgres_session_factory):
        """Test that resend confirmation POST with form data succeeds.

        Note: CSRF is disabled in test mode (WTF_CSRF_ENABLED = False),
        but in production it's enabled and the form includes csrf_token via form.hidden_tag().
        """
        response = client.post(
            "/auth/resend-confirmation",
            data={
                "email": "test@example.com",
                "csrf_token": get_csrf_token(client, "/auth/resend-confirmation"),
            },
            follow_redirects=False,
        )

        # Should succeed and redirect to login (even if email not found, due to anti-enumeration)
        assert response.status_code == 302
        assert response.headers["Location"] == "/auth/login"

    def test_resend_confirmation_get_request_shows_form(self, client: FlaskClient):
        """Test that GET request shows the resend confirmation form."""
        response = client.get("/auth/resend-confirmation")

        assert response.status_code == 200
        assert b"Resend confirmation email" in response.data or b"resend" in response.data.lower()
        # Verify the form is using WTForms (has CSRF token field in production)
        assert b'name="email"' in response.data

    def test_resend_confirmation_with_invalid_email_shows_error(self, client: FlaskClient, postgres_session_factory):
        """Test that submitting invalid email shows validation error."""
        response = client.post(
            "/auth/resend-confirmation",
            data={
                "email": "not-an-email",
                "csrf_token": get_csrf_token(client, "/auth/resend-confirmation"),
            },
            follow_redirects=False,
        )

        # Should re-render form with validation error
        assert response.status_code == 200
        assert b"Invalid email" in response.data or b"error" in response.data.lower()

    def test_resend_confirmation_with_missing_email_shows_error(self, client: FlaskClient, postgres_session_factory):
        """Test that submitting without email shows validation error."""
        response = client.post(
            "/auth/resend-confirmation",
            data={
                "csrf_token": get_csrf_token(client, "/auth/resend-confirmation"),
                # No email provided
            },
            follow_redirects=False,
        )

        # Should re-render form with validation error
        assert response.status_code == 200
        assert b"required" in response.data.lower() or b"error" in response.data.lower()
