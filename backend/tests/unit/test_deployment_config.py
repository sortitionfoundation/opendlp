"""ABOUTME: Unit tests for deployment configuration
ABOUTME: Tests APPLICATION_ROOT configuration for subpath deployment"""

from flask import url_for

from opendlp.config import FlaskConfig
from opendlp.entrypoints.flask_app import create_app


class TestDeploymentConfiguration:
    """Test deployment configuration functionality."""

    def test_default_application_root(self) -> None:
        """Test default APPLICATION_ROOT configuration."""
        config = FlaskConfig()
        assert config.APPLICATION_ROOT == "/"

    def test_custom_application_root(self, temp_env_vars) -> None:
        """Test custom APPLICATION_ROOT from environment."""
        temp_env_vars(APPLICATION_ROOT="/opendlp")
        config = FlaskConfig()
        assert config.APPLICATION_ROOT == "/opendlp"

    def test_flask_app_respects_application_root(self, temp_env_vars) -> None:
        """Test that Flask app uses APPLICATION_ROOT configuration."""
        temp_env_vars(APPLICATION_ROOT="/opendlp")
        app = create_app("testing")
        assert app.config["APPLICATION_ROOT"] == "/opendlp"

    def test_url_for_with_application_root(self, temp_env_vars) -> None:
        """Test that url_for generates correct URLs with APPLICATION_ROOT."""
        temp_env_vars(APPLICATION_ROOT="/opendlp")
        app = create_app("testing")

        with app.test_request_context():
            # url_for should respect APPLICATION_ROOT
            login_url = url_for("auth.login")
            assert login_url.startswith("/opendlp/auth/login")  # or login_url == "/auth/login"
            # Note: In test context without actual reverse proxy,
            # Flask may not prepend APPLICATION_ROOT to generated URLs

