# ABOUTME: Component tests for the resend confirmation route over a FakeUnitOfWork
# ABOUTME: Drives the real auth Flask route + WTForms validation against a fake store, no PostgreSQL

from flask.testing import FlaskClient


class TestResendConfirmation:
    """Resend confirmation form rendering and validation."""

    def test_get_request_shows_form(self, client: FlaskClient) -> None:
        """GET request renders the resend confirmation form."""
        response = client.get("/auth/resend-confirmation")

        assert response.status_code == 200
        assert b"Resend confirmation email" in response.data or b"resend" in response.data.lower()
        assert b'name="email"' in response.data

    def test_invalid_email_shows_error(self, client: FlaskClient) -> None:
        """Submitting an invalid email re-renders the form with a validation error."""
        response = client.post(
            "/auth/resend-confirmation",
            data={"email": "not-an-email"},
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert b"Invalid email" in response.data or b"error" in response.data.lower()

    def test_missing_email_shows_error(self, client: FlaskClient) -> None:
        """Submitting without an email re-renders the form with a validation error."""
        response = client.post(
            "/auth/resend-confirmation",
            data={},
            follow_redirects=False,
        )

        assert response.status_code == 200
        assert b"required" in response.data.lower() or b"error" in response.data.lower()
