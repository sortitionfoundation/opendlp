"""ABOUTME: Integration tests for Flask application factory and routing
ABOUTME: Tests Flask app creation, configuration, blueprints, and error handlers"""

import pytest
from flask import Flask
from flask.testing import FlaskClient

from opendlp.entrypoints.flask_app import create_app


class TestFlaskApp:
    """Test Flask application factory and basic functionality."""

    def test_create_app_returns_flask_instance(self) -> None:
        """Test that create_app returns a Flask instance."""
        app = create_app("testing")
        assert isinstance(app, Flask)

    def test_create_app_loads_test_config(self) -> None:
        """Test that create_app loads the correct configuration."""
        app = create_app("testing")
        assert app.config["TESTING"] is True
        assert app.config["WTF_CSRF_ENABLED"] is False

    def test_create_app_registers_blueprints(self) -> None:
        """Test that blueprints are registered."""
        app = create_app("testing")
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        assert "main" in blueprint_names
        assert "auth" in blueprint_names
        assert "admin" in blueprint_names

    def test_main_routes_exist(self) -> None:
        """Test that main routes are accessible."""
        app = create_app("testing")
        with app.test_client() as client:
            # Test index route
            response = client.get("/")
            assert response.status_code == 200

    def test_auth_routes_exist(self) -> None:
        """Test that auth routes are accessible."""
        app = create_app("testing")
        with app.test_client() as client:
            # Test login route (GET)
            response = client.get("/auth/login")
            assert response.status_code == 200

            # Test register route (GET)
            response = client.get("/auth/register")
            assert response.status_code == 200

    def test_error_handlers_registered(self) -> None:
        """Test that error handlers are properly registered."""
        app = create_app("testing")

        with app.test_client() as client:
            # Test 404 handler
            response = client.get("/nonexistent-route")
            assert response.status_code == 404
            assert b"Page Not Found" in response.data or b"404" in response.data

    def test_security_headers_applied(self) -> None:
        """Test that Talisman security headers are applied."""
        app = create_app("testing")

        with app.test_client() as client:
            response = client.get("/")
            # Check that some security headers are present
            # Note: Exact headers depend on Talisman configuration
            assert response.status_code == 200
            assert "'self'" in response.headers["Content-Security-Policy"]
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


class TestMainBlueprint:
    """Test main blueprint routes."""

    @pytest.fixture
    def client(self) -> FlaskClient:
        """Create test client."""
        app = create_app("testing")
        return app.test_client()

    def test_index_route(self, client: FlaskClient) -> None:
        """Test index route returns landing page."""
        response = client.get("/")
        assert response.status_code == 200
        assert b"OpenDLP" in response.data

    def test_dashboard_requires_login(self, client: FlaskClient) -> None:
        """Test dashboard route requires authentication."""
        response = client.get("/dashboard")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestAuthBlueprint:
    """Test auth blueprint routes."""

    @pytest.fixture
    def client(self) -> FlaskClient:
        """Create test client."""
        app = create_app("testing")
        return app.test_client()

    def test_login_get(self, client: FlaskClient) -> None:
        """Test login GET request shows login form."""
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert b"Sign in" in response.data

    def test_register_get(self, client: FlaskClient) -> None:
        """Test register GET request shows registration form."""
        response = client.get("/auth/register")
        assert response.status_code == 200
        assert b"Register" in response.data

    def test_register_with_invite_code_in_url(self, client: FlaskClient) -> None:
        """Test register route with invite code in URL."""
        response = client.get("/auth/register/TEST123")
        assert response.status_code == 200
        assert b"Register" in response.data

    def test_login_post_missing_credentials(self, client: FlaskClient) -> None:
        """Test login POST with missing credentials."""
        response = client.post("/auth/login", data={})
        assert response.status_code == 200  # Returns form with error
        # Would check for flash message in full integration

    def test_register_post_missing_fields(self, client: FlaskClient) -> None:
        """Test register POST with missing fields."""
        response = client.post(
            "/auth/register",
            data={
                "first_name": "Test",
                # Missing other required fields (email, password, etc.)
            },
        )
        assert response.status_code == 200  # Returns form with error


class TestAdminBlueprint:
    """Test admin blueprint routes."""

    @pytest.fixture
    def client(self) -> FlaskClient:
        """Create test client."""
        app = create_app("testing")
        return app.test_client()

    def test_admin_users_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin users list route requires authentication."""
        response = client.get("/admin/users")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_view_user_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin view user route requires authentication."""
        import uuid

        user_id = uuid.uuid4()
        response = client.get(f"/admin/users/{user_id}")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_edit_user_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin edit user route requires authentication."""
        import uuid

        user_id = uuid.uuid4()
        response = client.get(f"/admin/users/{user_id}/edit")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_invites_list_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin invites list route requires authentication."""
        response = client.get("/admin/invites")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_create_invite_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin create invite route requires authentication."""
        response = client.get("/admin/invites/create")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_view_invite_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin view invite route requires authentication."""
        import uuid

        invite_id = uuid.uuid4()
        response = client.get(f"/admin/invites/{invite_id}")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_revoke_invite_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin revoke invite route requires authentication."""
        import uuid

        invite_id = uuid.uuid4()
        response = client.post(f"/admin/invites/{invite_id}/revoke")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_cleanup_invites_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin cleanup invites route requires authentication."""
        response = client.post("/admin/invites/cleanup")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestErrorHandlers:
    """Test error handlers."""

    @pytest.fixture
    def client(self) -> FlaskClient:
        """Create test client."""
        app = create_app("testing")
        return app.test_client()

    def test_404_handler(self, client: FlaskClient) -> None:
        """Test 404 error handler."""
        response = client.get("/does-not-exist")
        assert response.status_code == 404
        assert b"404" in response.data or b"Not Found" in response.data

    def test_404_handler_returns_proper_template(self, client: FlaskClient) -> None:
        """Test 404 handler uses proper template."""
        response = client.get("/invalid-route")
        assert response.status_code == 404
        # Should contain elements from our 404 template
        assert b"Page Not Found" in response.data or b"404" in response.data


class TestConfiguration:
    """Test application configuration handling."""

    def test_development_config(self) -> None:
        """Test development configuration."""
        import os

        # Save current env and set to development for this test
        original_env = os.environ.get("FLASK_ENV")
        try:
            os.environ["FLASK_ENV"] = "development"
            app = create_app("development")
            assert app.config.get("DEBUG") is False  # Unless explicitly set
            assert app.config["FLASK_ENV"] == "development"
        finally:
            # Restore original environment
            if original_env is not None:  # pragma: no cover
                os.environ["FLASK_ENV"] = original_env
            elif "FLASK_ENV" in os.environ:  # pragma: no cover
                del os.environ["FLASK_ENV"]

    def test_testing_config(self) -> None:
        """Test testing configuration."""
        app = create_app("testing")
        assert app.config["TESTING"] is True
        assert app.config["WTF_CSRF_ENABLED"] is False

    def test_config_loading_fallback(self) -> None:
        """Test configuration loading with fallback."""
        # Should not raise an error with unknown config
        app = create_app("unknown")
        assert isinstance(app, Flask)

    def test_secret_key_configured(self) -> None:
        """Test that secret key is configured."""
        app = create_app("testing")
        assert app.config.get("SECRET_KEY") is not None
