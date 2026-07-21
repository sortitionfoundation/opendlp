"""ABOUTME: Unit tests for Flask application factory and routing
ABOUTME: Tests Flask app creation, configuration, blueprints, and error handlers"""

import os
import uuid
from datetime import timedelta

import pytest
import structlog
from flask import Flask
from flask.testing import FlaskClient

from opendlp.entrypoints.flask_app import create_app


class TestRequestContextLogging:
    """Characterisation tests for per-request structlog contextvars binding.

    This contract (request_id / view / peer bound on every request, no PII) is
    relied on by the log redaction work for request correlation - lock it so a
    future change can't silently drop it.
    """

    def test_before_request_binds_request_id_contextvars(self) -> None:
        app = create_app("testing")
        with app.test_request_context("/dashboard", environ_overrides={"REMOTE_ADDR": "1.2.3.4"}):
            app.preprocess_request()
            ctx = structlog.contextvars.get_contextvars()
            assert ctx.get("request_id")
            assert ctx.get("view") == "/dashboard"
            assert ctx.get("peer") == "1.2.3.4"
        structlog.contextvars.clear_contextvars()

    def test_request_context_does_not_bind_pii(self) -> None:
        app = create_app("testing")
        with app.test_request_context("/dashboard", environ_overrides={"REMOTE_ADDR": "1.2.3.4"}):
            app.preprocess_request()
            ctx = structlog.contextvars.get_contextvars()
            assert "email" not in ctx
        structlog.contextvars.clear_contextvars()


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
        """Test that secure security headers are applied."""
        app = create_app("testing")

        with app.test_client() as client:
            response = client.get("/")
            # Check that some security headers are present
            # Note: Exact headers depend on Talisman configuration
            assert response.status_code == 200
            assert "'self'" in response.headers["Content-Security-Policy"]
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_csp_allows_youtube_nocookie_frames_only(self) -> None:
        """The CSP must allow YouTube privacy-enhanced embeds but not plain youtube.com."""
        app = create_app("testing")

        with app.test_client() as client:
            response = client.get("/")
            csp = response.headers["Content-Security-Policy"]
            assert "frame-src 'self' https://www.youtube-nocookie.com" in csp
            assert "https://www.youtube.com" not in csp


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

    def test_index_sets_no_cookie_for_anonymous_visitor(self, client: FlaskClient) -> None:
        """The front page must set no cookie for an anonymous visitor.

        This is the load-bearing premise of docs/personal-data.md: an anonymous
        visitor acquires a cookie only by choosing a language, signing in, or
        opening a form. Adding a flash(), a CSRF token, or any session write to
        the index view would break that, and must be a deliberate decision.
        """
        response = client.get("/")

        assert response.status_code == 200
        assert "Set-Cookie" not in response.headers

    def test_index_footer_links_to_cookies_page(self, client: FlaskClient) -> None:
        """Test the footer carries a cookies page link, as GOV.UK guidance requires."""
        response = client.get("/")
        assert b"https://docs.sortitionlab.org/data-and-legal/cookies/" in response.data

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
        assert b"Create an Account" in response.data

    def test_register_with_invite_code_in_url(self, client: FlaskClient) -> None:
        """Test register route with invite code in URL."""
        response = client.get("/auth/register/TEST123")
        assert response.status_code == 200
        assert b"Create an Account" in response.data

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
        user_id = uuid.uuid4()
        response = client.get(f"/admin/users/{user_id}")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_edit_user_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin edit user route requires authentication."""
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
        invite_id = uuid.uuid4()
        response = client.get(f"/admin/invites/{invite_id}")
        # Should redirect to login
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_admin_revoke_invite_route_requires_login(self, client: FlaskClient) -> None:
        """Test admin revoke invite route requires authentication."""
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

    def test_csrf_error_handler_returns_friendly_page(self) -> None:
        """An expired/missing CSRF token renders the friendly 400 page, not a bare error."""
        app = create_app("testing")
        # CSRF is disabled in the testing config, so enable it to exercise the handler.
        app.config["WTF_CSRF_ENABLED"] = True
        client = app.test_client()
        # POST to a CSRF-protected form without a token to trigger a CSRFError.
        response = client.post("/auth/login", data={"email": "a@b.com", "password": "x"})
        assert response.status_code == 400
        assert b"Form Expired" in response.data


class TestConfiguration:
    """Test application configuration handling."""

    def test_development_config(self) -> None:
        """Test development configuration."""
        # Save current env and set to development for this test
        original_env = os.environ.get("FLASK_ENV")
        original_debug = os.environ.get("DEBUG")
        try:
            os.environ["FLASK_ENV"] = "development"
            if original_debug is not None:  # pragma: no cover
                del os.environ["DEBUG"]
            app = create_app("development")
            assert app.config.get("DEBUG") is False  # Unless explicitly set
            assert app.config["FLASK_ENV"] == "development"
        finally:
            # Restore original environment
            if original_env is not None:  # pragma: no cover
                os.environ["FLASK_ENV"] = original_env
            elif "FLASK_ENV" in os.environ:  # pragma: no cover
                del os.environ["FLASK_ENV"]
            if original_debug is not None:  # pragma: no cover
                os.environ["DEBUG"] = original_debug

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

    def test_csrf_token_has_no_separate_time_limit(self) -> None:
        """CSRF token validity is tied to the session, not a short separate clock."""
        app = create_app("development")
        assert app.config["WTF_CSRF_TIME_LIMIT"] is None

    def test_session_lifetime_is_seven_days(self) -> None:
        """Sessions (and thus CSRF tokens) remain valid for seven days."""
        app = create_app("development")
        assert app.config["PERMANENT_SESSION_LIFETIME"] == timedelta(days=7)

    def test_secret_key_configured(self) -> None:
        """Test that secret key is configured."""
        app = create_app("testing")
        assert app.config.get("SECRET_KEY") is not None
