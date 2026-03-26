"""ABOUTME: E2E tests for well-known URL endpoints (robots.txt, security.txt, change-password).
ABOUTME: Verifies static file serving, caching headers, and authentication-aware redirects."""

from flask.testing import FlaskClient

from opendlp.domain.users import User


class TestRobotsTxt:
    """Tests for /robots.txt endpoint."""

    def test_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/robots.txt")
        assert response.status_code == 200

    def test_content_type_is_plain_text(self, client: FlaskClient) -> None:
        response = client.get("/robots.txt")
        assert response.content_type.startswith("text/plain")

    def test_contains_user_agent_directive(self, client: FlaskClient) -> None:
        response = client.get("/robots.txt")
        assert b"User-agent:" in response.data


class TestSecurityTxt:
    """Tests for /.well-known/security.txt endpoint."""

    def test_returns_200(self, client: FlaskClient) -> None:
        response = client.get("/.well-known/security.txt")
        assert response.status_code == 200

    def test_content_type_is_plain_text(self, client: FlaskClient) -> None:
        response = client.get("/.well-known/security.txt")
        assert response.content_type.startswith("text/plain")

    def test_contains_contact_field(self, client: FlaskClient) -> None:
        response = client.get("/.well-known/security.txt")
        assert b"Contact:" in response.data


class TestChangePassword:
    """Tests for /.well-known/change-password redirect."""

    def test_anonymous_user_redirects_to_forgot_password(self, client: FlaskClient) -> None:
        response = client.get("/.well-known/change-password")
        assert response.status_code == 302
        assert "/auth/forgot-password" in response.headers["Location"]

    def test_logged_in_user_redirects_to_profile_change_password(
        self, logged_in_user: FlaskClient, regular_user: User
    ) -> None:
        response = logged_in_user.get("/.well-known/change-password")
        assert response.status_code == 302
        assert "/profile/change-password" in response.headers["Location"]
