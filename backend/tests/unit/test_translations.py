"""ABOUTME: Unit tests for translation system
ABOUTME: Tests that translation functions work both in Flask context and standalone"""

from flask import Flask
from flask_babel import LazyString

from opendlp.entrypoints.flask_app import create_app
from opendlp.service_layer.exceptions import InvalidCredentials, UserAlreadyExists
from opendlp.translations import gettext, lazy_gettext, ngettext


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

    def test_ngettext_outside_flask_context_picks_the_form_by_number(self) -> None:
        assert ngettext("%(num)s row", "%(num)s rows", 1) == "1 row"
        assert ngettext("%(num)s row", "%(num)s rows", 2) == "2 rows"
        assert ngettext("%(num)s row", "%(num)s rows", 0) == "0 rows"

    def test_ngettext_takes_further_parameters(self) -> None:
        assert ngettext("%(count)s row in %(name)s", "%(count)s rows in %(name)s", 1200, count="1,200", name="x") == (
            "1,200 rows in x"
        )

    def test_ngettext_in_flask_context(self) -> None:
        """Inside the application Flask-Babel does the work; the wrapper must hand everything through."""
        app = create_app("testing")

        with app.test_request_context():
            assert ngettext("%(num)s row", "%(num)s rows", 1) == "1 row"
            assert ngettext("%(count)s row", "%(count)s rows", 3, count="3") == "3 rows"

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
