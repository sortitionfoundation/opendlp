"""ABOUTME: Unit tests for translation system
ABOUTME: Tests that translation functions work both in Flask context and standalone"""

from flask import Flask

from opendlp.service_layer.exceptions import InvalidCredentials, UserAlreadyExists
from opendlp.translations import _, _l


class TestTranslations:
    """Test translation functionality."""

    def test_gettext_outside_flask_context(self) -> None:
        """Test that _ function works outside Flask context."""
        result = _("Login")
        assert result == "Login"  # Should return original since no translations loaded

    def test_lazy_gettext_outside_flask_context(self) -> None:
        """Test that _l function works outside Flask context."""
        result = _l("Registration successful! Welcome to OpenDLP.")
        assert result == "Registration successful! Welcome to OpenDLP."

    def test_gettext_with_parameters(self) -> None:
        """Test that _ function works with parameters."""
        result = _("User with username %(username)s already exists", username="testuser")
        assert result == "User with username testuser already exists"

    def test_lazy_gettext_with_parameters(self) -> None:
        """Test that _l function works with parameters."""
        result = _l("User with email %(email)s already exists", email="test@example.com")
        assert result == "User with email test@example.com already exists"

    def test_gettext_in_flask_context(self) -> None:
        """Test that _ function works inside Flask context."""
        app = Flask(__name__)

        with app.app_context():
            result = _("Login")
            assert result == "Login"  # Will use Flask-Babel if available

    def test_lazy_gettext_in_flask_context(self) -> None:
        """Test that _l function works inside Flask context."""
        app = Flask(__name__)

        with app.app_context():
            result = _l("Dashboard")
            assert result == "Dashboard"

    def test_translations_in_exceptions(self) -> None:
        """Test that translations work in domain exceptions."""

        # Test UserAlreadyExists with username
        exc = UserAlreadyExists(username="testuser")
        assert "testuser" in str(exc)

        # Test UserAlreadyExists with email
        exc = UserAlreadyExists(email="test@example.com")
        assert "test@example.com" in str(exc)

        # Test InvalidCredentials
        exc = InvalidCredentials()
        assert "Invalid username or password" in str(exc)
