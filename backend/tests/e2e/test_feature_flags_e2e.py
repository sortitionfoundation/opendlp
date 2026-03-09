"""ABOUTME: End-to-end tests for feature flags in the full Flask application.
ABOUTME: Verifies feature flags work through the complete request/response cycle."""

import os
from unittest.mock import patch

from flask.testing import FlaskClient

from opendlp.feature_flags import reload_flags


class TestFeatureFlagsE2E:
    """Test feature flags through the real application stack."""

    def test_feature_function_available_in_health_response(self, client: FlaskClient):
        """The feature() context processor is registered on the real app.

        We verify this indirectly: if the app boots and serves a page, the
        context processor was registered without error. The health endpoint
        doesn't use templates, but the app startup would have failed if
        the context processor registration raised.
        """
        with (
            patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 0)),
            patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
        ):
            response = client.get("/health")
        assert response.status_code == 200

    def test_feature_flag_in_login_page(self, client: FlaskClient, monkeypatch):
        """Login page renders successfully with feature flags available.

        The login page is public (no auth needed) so we can verify that
        the template rendering pipeline works with our context processor.
        """
        monkeypatch.setenv("FF_TEST_E2E", "true")
        reload_flags()

        response = client.get("/auth/login")
        assert response.status_code == 200

    def test_app_starts_with_no_feature_flags(self, client: FlaskClient):
        """App starts cleanly when no FF_* environment variables are set."""
        # Remove any FF_ vars that might be set
        ff_keys = [k for k in os.environ if k.startswith("FF_")]
        saved = {k: os.environ.pop(k) for k in ff_keys}
        reload_flags()
        try:
            with (
                patch("opendlp.entrypoints.blueprints.health.check_database", return_value=(True, 0)),
                patch("opendlp.entrypoints.blueprints.health.check_celery_worker", return_value=True),
            ):
                response = client.get("/health")
            assert response.status_code == 200
        finally:
            os.environ.update(saved)
            reload_flags()
