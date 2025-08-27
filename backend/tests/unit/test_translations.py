"""ABOUTME: Unit tests for translation system
ABOUTME: Tests that translation functions work both in Flask context and standalone"""

from flask import Flask
from flask_babel import LazyString

from opendlp.service_layer.exceptions import InvalidCredentials, UserAlreadyExists
from opendlp.translations import gettext, lazy_gettext


class TestTranslations:
    """Test translation functionality."""

    def test_gettext_outside_flask_context(self) -> None:
        """Test that gettext function works outside Flask context."""
        result = gettext("Login")
        assert result == "Login"  # Should return original since no translations loaded

    def test_lazy_gettext_outside_flask_context(self) -> None:
        """Test that lazy_gettext function works outside Flask context."""
        result = lazy_gettext("Registration successful! Welcome to OpenDLP.")
        assert isinstance(result, LazyString)
        assert result == "Registration successful! Welcome to OpenDLP."

    def test_gettext_with_parameters(self) -> None:
        """Test that gettext function works with parameters."""
        result = gettext("User with username %(username)s already exists", username="testuser")
        assert result == "User with username testuser already exists"

    def test_lazy_gettext_with_parameters(self) -> None:
        """Test that lazy_gettext function works with parameters."""
        result = lazy_gettext("User with email %(email)s already exists", email="test@example.com")
        assert isinstance(result, LazyString)
        assert result == "User with email test@example.com already exists"

    def test_gettext_in_flask_context(self) -> None:
        """Test that gettext function works inside Flask context."""
        app = Flask(__name__)

        with app.app_context():
            result = gettext("Login")
            assert result == "Login"  # Will use Flask-Babel if available

    def test_lazy_gettext_in_flask_context(self) -> None:
        """Test that lazy_gettext function works inside Flask context."""
        app = Flask(__name__)

        with app.app_context():
            result = lazy_gettext("Dashboard")
            assert result == "Dashboard"

    def test_translations_in_exceptions(self) -> None:
        """Test that translations work in domain exceptions."""

        # Test UserAlreadyExists with email
        exc = UserAlreadyExists(email="test@example.com")
        assert "test@example.com" in str(exc)

        # Test InvalidCredentials
        exc = InvalidCredentials()
        assert "Invalid email or password" in str(exc)
