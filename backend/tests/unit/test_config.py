"""ABOUTME: Unit tests for OpenDLP configuration module
ABOUTME: Tests environment variable loading and configuration class behavior"""

from typing import ClassVar

import pytest

from opendlp.config import (
    FlaskConfig,
    FlaskProductionConfig,
    FlaskTestPostgresConfig,
    FlaskTestSQLiteConfig,
    InvalidConfig,
    get_config,
    to_bool,
)


class TestToBool:
    test_values: ClassVar = [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("FALSE", False),
        ("1", True),
        ("0", False),
        ("yes", True),
        ("YES", True),
        ("no", False),
        ("NO", False),
        ("on", True),
        ("ON", True),
        ("off", False),
        ("OFF", False),
        ("", False),
        (None, False),
        ("  true  ", True),  # Test whitespace handling
    ]

    @pytest.mark.parametrize("bool_str,expected", test_values)
    def test_to_bool(self, bool_str: str, expected: bool):
        assert to_bool(bool_str) == expected

    def test_to_bool_raises_on_bad_value(self):
        with pytest.raises(ValueError):
            to_bool("invalid")


class TestFlaskConfigClass:
    """Test the base Config class."""

    def test_config_defaults(self, temp_env_vars, clear_env_vars):
        """Test that Config loads expected default values."""
        # Clear FLASK_ENV to test defaults
        clear_env_vars("DB_HOST", "DB_PORT", "DB_PASSWORD", "DB_NAME", "SECRET_KEY")
        temp_env_vars(FLASK_ENV="development")

        config = FlaskConfig()

        assert config.SQLALCHEMY_DATABASE_URI == "postgresql://opendlp:abc123@localhost:54321/opendlp"
        assert config.SECRET_KEY == "dev-secret-key-change-in-production"
        assert config.FLASK_ENV == "development"
        assert config.SELECTION_TIMEOUT == 600
        assert config.INVITE_EXPIRY_HOURS == 168
        assert config.OAUTH_GOOGLE_CLIENT_ID == ""
        assert config.OAUTH_GOOGLE_CLIENT_SECRET == ""

    def test_config_with_env_vars(self, temp_env_vars):
        """Test that Config loads from environment variables."""
        temp_env_vars(
            DB_HOST="db.server.net",
            DB_PASSWORD="db-secret",
            DB_PORT="5432",
            SECRET_KEY="test-secret",
            FLASK_ENV="production",
            SELECTION_TIMEOUT="300",
            INVITE_EXPIRY_HOURS="72",
            OAUTH_GOOGLE_CLIENT_ID="test-client-id",
            OAUTH_GOOGLE_CLIENT_SECRET="test-client-secret",
        )

        config = FlaskConfig()

        assert config.SQLALCHEMY_DATABASE_URI == "postgresql://opendlp:db-secret@db.server.net:5432/opendlp"
        assert config.SECRET_KEY == "test-secret"
        assert config.FLASK_ENV == "production"
        assert config.SELECTION_TIMEOUT == 300
        assert config.INVITE_EXPIRY_HOURS == 72
        assert config.OAUTH_GOOGLE_CLIENT_ID == "test-client-id"
        assert config.OAUTH_GOOGLE_CLIENT_SECRET == "test-client-secret"


class TestFlaskTestConfig:
    """Test the DevTestConfig class."""

    def test_test_sqlite_config_overrides(self):
        """Test that FlaskTestSQLiteConfig overrides appropriate values."""
        config = FlaskTestSQLiteConfig()

        assert config.SQLALCHEMY_DATABASE_URI == "sqlite:///:memory:"
        assert config.SECRET_KEY == "test-secret-key-aockgn298zx081238"
        assert config.FLASK_ENV == "testing"
        # Should inherit other defaults
        assert config.SELECTION_TIMEOUT == 600
        assert config.INVITE_EXPIRY_HOURS == 168

    def test_test_postgres_config_overrides(self, clear_env_vars):
        """Test that FlaskTestPostgresConfig overrides appropriate values."""
        clear_env_vars("DB_HOST", "DB_PORT", "DB_PASSWORD", "DB_NAME", "SECRET_KEY")
        config = FlaskTestPostgresConfig()

        assert config.SQLALCHEMY_DATABASE_URI == "postgresql://opendlp:abc123@localhost:54322/opendlp"
        assert config.SECRET_KEY == "test-secret-key-aockgn298zx081238"
        assert config.FLASK_ENV == "testing"
        # Should inherit other defaults
        assert config.SELECTION_TIMEOUT == 600
        assert config.INVITE_EXPIRY_HOURS == 168


class TestFlaskProductionConfig:
    """Test the FlaskProductionConfig class."""

    def test_production_config_with_secret_key(self, temp_env_vars):
        """Test that ProductionConfig works with proper SECRET_KEY."""
        temp_env_vars(SECRET_KEY="production-secret-key", EMAIL_ADAPTER="console")

        config = FlaskProductionConfig()

        assert config.SECRET_KEY == "production-secret-key"

    def test_production_config_without_secret_key(self, clear_env_vars):
        """Test that ProductionConfig raises error without proper SECRET_KEY."""
        clear_env_vars("SECRET_KEY")
        with pytest.raises(InvalidConfig, match="SECRET_KEY must be set in production"):
            FlaskProductionConfig()


class TestGetConfig:
    """Test the get_config function."""

    def test_get_config_development(self, temp_env_vars):
        """Test get_config returns Config for development."""
        temp_env_vars(FLASK_ENV="development")

        config = get_config()

        assert isinstance(config, FlaskConfig)
        assert not isinstance(config, FlaskTestSQLiteConfig)
        assert not isinstance(config, FlaskTestPostgresConfig)
        assert not isinstance(config, FlaskProductionConfig)

    @pytest.mark.parametrize(
        "name,klass",
        [
            ("testing", FlaskTestSQLiteConfig),
            ("testing_sqlite", FlaskTestSQLiteConfig),
            ("testing_postgres", FlaskTestPostgresConfig),
        ],
    )
    def test_get_config_testing(self, name, klass, temp_env_vars):
        """Test get_config returns TestConfig for testing."""
        temp_env_vars(FLASK_ENV=name)

        config = get_config()

        assert isinstance(config, klass)

    def test_get_config_production(self, temp_env_vars):
        """Test get_config returns ProductionConfig for production."""
        temp_env_vars(FLASK_ENV="production", SECRET_KEY="production-secret", EMAIL_ADAPTER="console")

        config = get_config()

        assert isinstance(config, FlaskProductionConfig)

    def test_get_config_default(self, clear_env_vars):
        """Test get_config returns Config by default."""
        # Remove FLASK_ENV if present
        clear_env_vars("FLASK_ENV")

        config = get_config()
        assert isinstance(config, FlaskConfig)
        assert not isinstance(config, FlaskTestSQLiteConfig)
        assert not isinstance(config, FlaskTestPostgresConfig)
        assert not isinstance(config, FlaskProductionConfig)
