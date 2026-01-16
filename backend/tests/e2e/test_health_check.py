"""ABOUTME: End-to-end health check endpoint tests
ABOUTME: Tests health check endpoint with different system states"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from flask.testing import FlaskClient


class TestHealthCheckEndpoint:
    """Test health check endpoint functionality."""

    def test_health_check_returns_200_when_all_healthy(self, client: FlaskClient):
        """Test health check returns HTTP 200 when database and celery are healthy."""
        # Mock both checks to return healthy status
        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")

        assert response.status_code == 200
        assert response.content_type == "application/json"

        data = response.get_json()
        assert data is not None
        assert data["database_ok"] is True
        assert data["celery_worker_running"] is True
        assert "user_count" in data
        assert isinstance(data["user_count"], int) or data["user_count"] == "UNKNOWN"
        assert "service_account_email" in data
        assert "version" in data

    def test_health_check_returns_500_when_celery_not_running(self, client: FlaskClient):
        """Test health check returns HTTP 500 when celery worker is not running."""
        # Mock database as healthy but celery as not running
        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 5)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=False),
        ):
            response = client.get("/health")

        assert response.status_code == 500
        assert response.content_type == "application/json"

        data = response.get_json()
        assert data is not None
        assert data["database_ok"] is True
        assert data["celery_worker_running"] is False
        assert "user_count" in data
        assert "service_account_email" in data
        assert "version" in data

    def test_health_check_returns_500_when_database_fails(self, client: FlaskClient):
        """Test health check returns HTTP 500 when database check fails."""
        # Mock database check to return failure
        with patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(False, "UNKNOWN")):
            response = client.get("/health")

        assert response.status_code == 500
        assert response.content_type == "application/json"

        data = response.get_json()
        assert data is not None
        assert data["database_ok"] is False
        assert data["user_count"] == "UNKNOWN"
        assert "celery_worker_running" in data
        assert "service_account_email" in data
        assert "version" in data

    def test_health_check_always_returns_valid_json(self, client: FlaskClient):
        """Test health check always returns valid JSON even when checks fail."""
        # Mock both checks to fail
        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(False, "UNKNOWN")),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=False),
        ):
            response = client.get("/health")

        assert response.status_code == 500
        assert response.content_type == "application/json"

        # Should still be valid JSON with all expected fields
        data = response.get_json()
        assert data is not None
        assert "database_ok" in data
        assert "user_count" in data
        assert "celery_worker_running" in data
        assert "service_account_email" in data
        assert "version" in data

    def test_health_check_includes_version_and_service_account(self, client: FlaskClient):
        """Test health check includes version string and service account email."""
        with patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True):
            response = client.get("/health")

        data = response.get_json()
        assert data is not None

        # Version should be present (either actual version or "UNKNOWN")
        assert "version" in data
        assert isinstance(data["version"], str)
        assert len(data["version"]) > 0

        # Service account email should be present
        assert "service_account_email" in data
        assert isinstance(data["service_account_email"], str)
        assert len(data["service_account_email"]) > 0


class TestHealthCheckMicrosoftOAuthExpiry:
    """Test health check OAuth expiry monitoring functionality."""

    def test_health_check_includes_microsoft_oauth_expiry_fields(self, client: FlaskClient):
        """Test health check includes Microsoft OAuth expiry fields."""
        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")

        data = response.get_json()
        assert data is not None

        # Microsoft OAuth expiry fields should be present
        assert "oauth_microsoft_days_to_expiry" in data
        assert "oauth_microsoft_expiry_status" in data

    def test_health_check_no_microsoft_oauth_when_not_configured(self, client: FlaskClient):
        """Test health check returns NO_MICROSOFT_OAUTH when Microsoft OAuth not configured."""
        # Ensure Microsoft OAuth client ID is not set
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = ""

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")

        assert response.status_code == 200  # NO_MICROSOFT_OAUTH never affects health
        data = response.get_json()
        assert data["oauth_microsoft_days_to_expiry"] is None
        assert data["oauth_microsoft_expiry_status"] == "NO_MICROSOFT_OAUTH"

    def test_health_check_microsoft_expiry_unknown_when_not_set(self, client: FlaskClient):
        """Test health check returns UNKNOWN when OAuth configured but expiry date not set."""
        # Microsoft OAuth is configured but expiry date is not set
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = "test-client-id"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY"] = ""

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")

        assert response.status_code == 200  # UNKNOWN doesn't affect health without fail_on_warning
        data = response.get_json()
        assert data["oauth_microsoft_days_to_expiry"] is None
        assert data["oauth_microsoft_expiry_status"] == "UNKNOWN"

    def test_health_check_microsoft_expiry_ok_when_far_future(self, client: FlaskClient):
        """Test health check returns OK when expiry is >30 days away."""
        # Configure Microsoft OAuth
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = "test-client-id"
        # Set expiry 60 days in the future
        future_date = (datetime.now(UTC) + timedelta(days=60)).date()
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY"] = future_date.strftime("%Y-%m-%d")

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["oauth_microsoft_days_to_expiry"] == 60
        assert data["oauth_microsoft_expiry_status"] == "OK"

    def test_health_check_microsoft_expiry_warning_when_near(self, client: FlaskClient):
        """Test health check returns WARNING when expiry is <=30 days away."""
        # Set expiry 15 days in the future
        future_date = (datetime.now(UTC) + timedelta(days=15)).date()
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY"] = future_date.strftime("%Y-%m-%d")

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")

        assert response.status_code == 200  # WARNING doesn't fail without fail_on_warning
        data = response.get_json()
        assert data["oauth_microsoft_days_to_expiry"] == 15
        assert data["oauth_microsoft_expiry_status"] == "WARNING"

    def test_health_check_microsoft_expiry_expired_returns_500(self, client: FlaskClient):
        """Test health check returns 500 when secret has expired."""
        # Set expiry 10 days in the past
        past_date = (datetime.now(UTC) - timedelta(days=10)).date()
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY"] = past_date.strftime("%Y-%m-%d")

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")

        assert response.status_code == 500  # EXPIRED always fails
        data = response.get_json()
        assert data["oauth_microsoft_days_to_expiry"] == -10
        assert data["oauth_microsoft_expiry_status"] == "EXPIRED"

    def test_health_check_fail_on_warning_true_fails_on_warning(self, client: FlaskClient):
        """Test fail_on_warning=true returns 500 on WARNING status."""
        # Set expiry 20 days in the future (WARNING)
        future_date = (datetime.now(UTC) + timedelta(days=20)).date()
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY"] = future_date.strftime("%Y-%m-%d")

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health?fail_on_warning=true")

        assert response.status_code == 500  # WARNING with fail_on_warning=true
        data = response.get_json()
        assert data["oauth_microsoft_expiry_status"] == "WARNING"

    def test_health_check_fail_on_warning_true_fails_on_unknown(self, client: FlaskClient):
        """Test fail_on_warning=true returns 500 on UNKNOWN status."""
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY"] = ""

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health?fail_on_warning=true")

        assert response.status_code == 500  # UNKNOWN with fail_on_warning=true
        data = response.get_json()
        assert data["oauth_microsoft_expiry_status"] == "UNKNOWN"

    def test_health_check_fail_on_warning_false_succeeds_on_warning(self, client: FlaskClient):
        """Test fail_on_warning=false returns 200 on WARNING status."""
        # Set expiry 20 days in the future (WARNING)
        future_date = (datetime.now(UTC) + timedelta(days=20)).date()
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY"] = future_date.strftime("%Y-%m-%d")

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health?fail_on_warning=false")

        assert response.status_code == 200  # WARNING without fail_on_warning
        data = response.get_json()
        assert data["oauth_microsoft_expiry_status"] == "WARNING"

    def test_health_check_invalid_date_format_returns_unknown(self, client: FlaskClient):
        """Test invalid date format returns UNKNOWN status."""
        client.application.config["OAUTH_MICROSOFT_CLIENT_ID"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET"] = "1234"
        client.application.config["OAUTH_MICROSOFT_CLIENT_SECRET_EXPIRY"] = "not-a-date"  # pragma: allowlist secret

        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 3)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")

        assert response.status_code == 200  # UNKNOWN doesn't fail without fail_on_warning
        data = response.get_json()
        assert data["oauth_microsoft_days_to_expiry"] is None
        assert data["oauth_microsoft_expiry_status"] == "UNKNOWN"
