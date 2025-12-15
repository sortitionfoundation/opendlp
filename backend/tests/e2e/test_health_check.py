"""ABOUTME: End-to-end health check endpoint tests
ABOUTME: Tests health check endpoint with different system states"""

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
        assert "@" in data["service_account_email"]
