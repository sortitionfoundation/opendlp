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


class TestMicrosoftIdentityAssociation:
    """Tests for /.well-known/microsoft-identity-association.json endpoint."""

    url = "/.well-known/microsoft-identity-association.json"
    application_id = "11111111-2222-3333-4444-555555555555"

    def test_returns_404_when_application_id_not_configured(self, client: FlaskClient) -> None:
        client.application.config["OAUTH_MICROSOFT_APPLICATION_ID"] = ""

        response = client.get(self.url)

        assert response.status_code == 404

    def test_returns_200_when_application_id_configured(self, client: FlaskClient) -> None:
        client.application.config["OAUTH_MICROSOFT_APPLICATION_ID"] = self.application_id

        response = client.get(self.url)

        assert response.status_code == 200

    def test_content_type_is_json(self, client: FlaskClient) -> None:
        client.application.config["OAUTH_MICROSOFT_APPLICATION_ID"] = self.application_id

        response = client.get(self.url)

        assert response.content_type.startswith("application/json")

    def test_body_has_shape_microsoft_expects(self, client: FlaskClient) -> None:
        client.application.config["OAUTH_MICROSOFT_APPLICATION_ID"] = self.application_id

        response = client.get(self.url)

        assert response.get_json() == {"associatedApplications": [{"applicationId": self.application_id}]}

    def test_available_to_anonymous_users(self, client: FlaskClient) -> None:
        """Microsoft fetches this unauthenticated, so it must not redirect to sign in."""
        client.application.config["OAUTH_MICROSOFT_APPLICATION_ID"] = self.application_id

        response = client.get(self.url)

        assert response.status_code == 200


class TestChangePassword:
    """Tests for /.well-known/change-password redirect."""

    def test_anonymous_user_redirects_to_profile_change_password(self, client: FlaskClient) -> None:
        response = client.get("/.well-known/change-password")
        assert response.status_code == 302
        assert "/profile/change-password" in response.headers["Location"]

    def test_logged_in_user_redirects_to_profile_change_password(
        self, logged_in_user: FlaskClient, regular_user: User
    ) -> None:
        response = logged_in_user.get("/.well-known/change-password")
        assert response.status_code == 302
        assert "/profile/change-password" in response.headers["Location"]
