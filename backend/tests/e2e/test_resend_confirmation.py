"""ABOUTME: End-to-end PostgreSQL happy-path smoke for the resend confirmation route
ABOUTME: Behavioural coverage (form render, validation) lives in tests/component/"""

from flask.testing import FlaskClient

from tests.e2e.helpers import get_csrf_token


class TestResendConfirmation:
    """Test resend confirmation endpoint functionality."""

    def test_resend_confirmation_form_submission_succeeds(self, client: FlaskClient, postgres_session_factory) -> None:
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
