"""ABOUTME: Unit tests for OpenDLP configuration module
ABOUTME: Tests environment variable loading and configuration class behavior"""

import uuid
from typing import ClassVar

import pytest

from opendlp.config import (
    FlaskConfig,
    FlaskProductionConfig,
    FlaskTestConfig,
    InvalidConfig,
    get_config,
    get_max_csv_upload_bytes,
    get_max_csv_upload_mb,
    get_max_image_upload_bytes,
    get_max_image_upload_mb,
    get_max_images_per_registration_page,
    get_monitor_assembly_id,
    get_monitor_health_max_age_minutes,
    get_monitor_user_id,
    get_registration_form_html_max_bytes,
    get_registration_image_max_edge_px,
    get_registration_thank_you_html_max_bytes,
    get_task_timeout_hours,
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
        clear_env_vars(
            "DB_HOST",
            "DB_PORT",
            "DB_PASSWORD",
            "DB_NAME",
            "SECRET_KEY",
            "OAUTH_GOOGLE_CLIENT_ID",
            "OAUTH_GOOGLE_CLIENT_SECRET",
        )
        temp_env_vars(FLASK_ENV="development")

        config = FlaskConfig()

        assert (
            config.SQLALCHEMY_DATABASE_URI
            == "postgresql://opendlp:abc123@localhost:54321/opendlp"  # pragma: allowlist secret
        )
        assert config.SECRET_KEY == "dev-secret-key-change-in-production"  # pragma: allowlist secret
        assert config.FLASK_ENV == "development"
        assert config.INVITE_EXPIRY_HOURS == 168
        assert config.OAUTH_GOOGLE_CLIENT_ID == ""
        assert config.OAUTH_GOOGLE_CLIENT_SECRET == ""

    def test_config_with_env_vars(self, temp_env_vars):
        """Test that Config loads from environment variables."""
        temp_env_vars(
            DB_HOST="db.server.net",
            DB_PASSWORD="db-secret",  # pragma: allowlist secret
            DB_PORT="5432",
            SECRET_KEY="test-secret",  # pragma: allowlist secret
            FLASK_ENV="production",
            INVITE_EXPIRY_HOURS="72",
            OAUTH_GOOGLE_CLIENT_ID="test-client-id",
            OAUTH_GOOGLE_CLIENT_SECRET="test-client-secret",  # pragma: allowlist secret
        )

        config = FlaskConfig()

        assert (
            config.SQLALCHEMY_DATABASE_URI
            == "postgresql://opendlp:db-secret@db.server.net:5432/opendlp"  # pragma: allowlist secret
        )
        assert config.SECRET_KEY == "test-secret"  # pragma: allowlist secret
        assert config.FLASK_ENV == "production"
        assert config.INVITE_EXPIRY_HOURS == 72
        assert config.OAUTH_GOOGLE_CLIENT_ID == "test-client-id"
        assert config.OAUTH_GOOGLE_CLIENT_SECRET == "test-client-secret"  # pragma: allowlist secret


class TestFlaskTestConfig:
    """Test the FlaskTestConfig class."""

    def test_test_config_overrides(self, clear_env_vars):
        """Test that FlaskTestConfig overrides appropriate values."""
        clear_env_vars("DB_HOST", "DB_PORT", "DB_PASSWORD", "DB_NAME", "SECRET_KEY")
        config = FlaskTestConfig()

        assert (
            config.SQLALCHEMY_DATABASE_URI
            == "postgresql://opendlp:abc123@localhost:54322/opendlp"  # pragma: allowlist secret
        )
        assert config.SECRET_KEY == "test-secret-key-aockgn298zx081238"  # pragma: allowlist secret
        assert config.FLASK_ENV == "testing"
        # Should inherit other defaults
        assert config.INVITE_EXPIRY_HOURS == 168


class TestFlaskProductionConfig:
    """Test the FlaskProductionConfig class."""

    def test_production_config_with_secret_key(self, temp_env_vars):
        """Test that ProductionConfig works with proper SECRET_KEY."""
        temp_env_vars(SECRET_KEY="production-secret-key", EMAIL_ADAPTER="console")  # pragma: allowlist secret

        config = FlaskProductionConfig()

        assert config.SECRET_KEY == "production-secret-key"  # pragma: allowlist secret

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
        assert not isinstance(config, FlaskTestConfig)
        assert not isinstance(config, FlaskProductionConfig)

    @pytest.mark.parametrize(
        "name,klass",
        [
            ("testing", FlaskTestConfig),
            ("testing_postgres", FlaskTestConfig),
        ],
    )
    def test_get_config_testing(self, name, klass, temp_env_vars):
        """Test get_config returns TestConfig for testing."""
        temp_env_vars(FLASK_ENV=name)

        config = get_config()

        assert isinstance(config, klass)

    def test_get_config_production(self, temp_env_vars):
        """Test get_config returns ProductionConfig for production."""
        temp_env_vars(
            FLASK_ENV="production",
            SECRET_KEY="production-secret",  # pragma: allowlist secret
            EMAIL_ADAPTER="console",
        )

        config = get_config()

        assert isinstance(config, FlaskProductionConfig)

    def test_get_config_default(self, clear_env_vars):
        """Test get_config returns Config by default."""
        # Remove FLASK_ENV if present
        clear_env_vars("FLASK_ENV")

        config = get_config()
        assert isinstance(config, FlaskConfig)
        assert not isinstance(config, FlaskTestConfig)
        assert not isinstance(config, FlaskProductionConfig)


class TestGetTaskTimeoutHours:
    """Test the get_task_timeout_hours function."""

    def test_returns_default_when_not_set(self, clear_env_vars):
        """Test that function returns 24 (default) when TASK_TIMEOUT_HOURS is not set."""
        clear_env_vars("TASK_TIMEOUT_HOURS")
        assert get_task_timeout_hours() == 24

    def test_returns_default_when_empty_string(self, temp_env_vars):
        """Test that function returns 24 (default) when TASK_TIMEOUT_HOURS is empty."""
        temp_env_vars(TASK_TIMEOUT_HOURS="")
        assert get_task_timeout_hours() == 24

    def test_returns_valid_positive_integer(self, temp_env_vars):
        """Test that function returns the value when set to a valid positive integer."""
        temp_env_vars(TASK_TIMEOUT_HOURS="6")
        assert get_task_timeout_hours() == 6

    def test_returns_default_for_invalid_value(self, temp_env_vars):
        """Test that function returns default and logs warning for invalid value."""
        temp_env_vars(TASK_TIMEOUT_HOURS="not-a-number")
        assert get_task_timeout_hours() == 24

    def test_returns_default_for_zero(self, temp_env_vars):
        """Test that function returns default for zero value."""
        temp_env_vars(TASK_TIMEOUT_HOURS="0")
        assert get_task_timeout_hours() == 24

    def test_returns_default_for_negative(self, temp_env_vars):
        """Test that function returns default for negative value."""
        temp_env_vars(TASK_TIMEOUT_HOURS="-5")
        assert get_task_timeout_hours() == 24


class TestMonitorConfig:
    """Test the monitoring-related configuration helpers."""

    def test_assembly_id_returns_none_when_unset(self, clear_env_vars):
        clear_env_vars("MONITOR_ASSEMBLY_ID")
        assert get_monitor_assembly_id() is None

    def test_assembly_id_returns_none_for_invalid_uuid(self, temp_env_vars, caplog):
        temp_env_vars(MONITOR_ASSEMBLY_ID="not-a-uuid")
        with caplog.at_level("WARNING"):
            assert get_monitor_assembly_id() is None
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "MONITOR_ASSEMBLY_ID" in warnings[0].message

    def test_assembly_id_returns_uuid_for_valid_value(self, temp_env_vars):
        valid = uuid.uuid4()
        temp_env_vars(MONITOR_ASSEMBLY_ID=str(valid))
        assert get_monitor_assembly_id() == valid

    def test_user_id_returns_none_when_unset(self, clear_env_vars):
        clear_env_vars("MONITOR_USER_ID")
        assert get_monitor_user_id() is None

    def test_user_id_returns_none_for_invalid_uuid(self, temp_env_vars, caplog):
        temp_env_vars(MONITOR_USER_ID="not-a-uuid")
        with caplog.at_level("WARNING"):
            assert get_monitor_user_id() is None
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "MONITOR_USER_ID" in warnings[0].message

    def test_user_id_returns_uuid_for_valid_value(self, temp_env_vars):
        valid = uuid.uuid4()
        temp_env_vars(MONITOR_USER_ID=str(valid))
        assert get_monitor_user_id() == valid

    def test_max_age_returns_default_when_unset(self, clear_env_vars):
        clear_env_vars("MONITOR_HEALTH_MAX_AGE_MINUTES")
        assert get_monitor_health_max_age_minutes() == 120

    def test_max_age_returns_default_for_non_integer(self, temp_env_vars, caplog):
        temp_env_vars(MONITOR_HEALTH_MAX_AGE_MINUTES="not-an-int")
        with caplog.at_level("WARNING"):
            assert get_monitor_health_max_age_minutes() == 120
        warnings = [r for r in caplog.records if r.levelname == "WARNING"]
        assert len(warnings) == 1
        assert "MONITOR_HEALTH_MAX_AGE_MINUTES" in warnings[0].message

    def test_max_age_returns_value_when_valid(self, temp_env_vars):
        temp_env_vars(MONITOR_HEALTH_MAX_AGE_MINUTES="45")
        assert get_monitor_health_max_age_minutes() == 45


class TestGetMaxCsvUploadMb:
    """Test the get_max_csv_upload_mb function."""

    def test_returns_default_when_not_set(self, clear_env_vars):
        clear_env_vars("MAX_CSV_UPLOAD_MB")
        assert get_max_csv_upload_mb() == 50

    def test_returns_default_when_empty_string(self, temp_env_vars):
        temp_env_vars(MAX_CSV_UPLOAD_MB="")
        assert get_max_csv_upload_mb() == 50

    def test_returns_set_value(self, temp_env_vars):
        temp_env_vars(MAX_CSV_UPLOAD_MB="100")
        assert get_max_csv_upload_mb() == 100

    def test_invalid_string_falls_back_to_default(self, temp_env_vars):
        temp_env_vars(MAX_CSV_UPLOAD_MB="not-a-number")
        assert get_max_csv_upload_mb() == 50

    def test_clamps_below_minimum(self, temp_env_vars):
        temp_env_vars(MAX_CSV_UPLOAD_MB="0")
        assert get_max_csv_upload_mb() == 1

    def test_clamps_above_ceiling(self, temp_env_vars):
        temp_env_vars(MAX_CSV_UPLOAD_MB="9999")
        assert get_max_csv_upload_mb() == 500

    def test_bytes_helper_multiplies_by_1024_squared(self, temp_env_vars):
        temp_env_vars(MAX_CSV_UPLOAD_MB="3")
        assert get_max_csv_upload_bytes() == 3 * 1024 * 1024


class TestGetRegistrationFormHtmlMaxBytes:
    """Test the get_registration_form_html_max_bytes function."""

    def test_returns_default_when_not_set(self, clear_env_vars):
        clear_env_vars("REGISTRATION_FORM_HTML_MAX_BYTES")
        assert get_registration_form_html_max_bytes() == 204800

    def test_returns_default_when_empty_string(self, temp_env_vars):
        temp_env_vars(REGISTRATION_FORM_HTML_MAX_BYTES="")
        assert get_registration_form_html_max_bytes() == 204800

    def test_returns_set_value(self, temp_env_vars):
        temp_env_vars(REGISTRATION_FORM_HTML_MAX_BYTES="300000")
        assert get_registration_form_html_max_bytes() == 300000

    def test_invalid_string_falls_back_to_default(self, temp_env_vars):
        temp_env_vars(REGISTRATION_FORM_HTML_MAX_BYTES="not-a-number")
        assert get_registration_form_html_max_bytes() == 204800

    def test_clamps_below_minimum(self, temp_env_vars):
        temp_env_vars(REGISTRATION_FORM_HTML_MAX_BYTES="10")
        assert get_registration_form_html_max_bytes() == 1024

    def test_clamps_above_ceiling(self, temp_env_vars):
        temp_env_vars(REGISTRATION_FORM_HTML_MAX_BYTES="99999999")
        assert get_registration_form_html_max_bytes() == 10 * 1024 * 1024


class TestGetRegistrationThankYouHtmlMaxBytes:
    """Test the get_registration_thank_you_html_max_bytes function."""

    def test_returns_default_when_not_set(self, clear_env_vars):
        clear_env_vars("REGISTRATION_THANK_YOU_HTML_MAX_BYTES")
        assert get_registration_thank_you_html_max_bytes() == 51200

    def test_returns_default_when_empty_string(self, temp_env_vars):
        temp_env_vars(REGISTRATION_THANK_YOU_HTML_MAX_BYTES="")
        assert get_registration_thank_you_html_max_bytes() == 51200

    def test_returns_set_value(self, temp_env_vars):
        temp_env_vars(REGISTRATION_THANK_YOU_HTML_MAX_BYTES="80000")
        assert get_registration_thank_you_html_max_bytes() == 80000

    def test_invalid_string_falls_back_to_default(self, temp_env_vars):
        temp_env_vars(REGISTRATION_THANK_YOU_HTML_MAX_BYTES="not-a-number")
        assert get_registration_thank_you_html_max_bytes() == 51200

    def test_clamps_below_minimum(self, temp_env_vars):
        temp_env_vars(REGISTRATION_THANK_YOU_HTML_MAX_BYTES="10")
        assert get_registration_thank_you_html_max_bytes() == 1024

    def test_clamps_above_ceiling(self, temp_env_vars):
        temp_env_vars(REGISTRATION_THANK_YOU_HTML_MAX_BYTES="99999999")
        assert get_registration_thank_you_html_max_bytes() == 10 * 1024 * 1024


class TestGetMaxImageUploadMb:
    """Test the get_max_image_upload_mb / _bytes functions."""

    def test_returns_default_when_not_set(self, clear_env_vars):
        clear_env_vars("MAX_IMAGE_UPLOAD_MB")
        assert get_max_image_upload_mb() == 10

    def test_returns_default_when_empty_string(self, temp_env_vars):
        temp_env_vars(MAX_IMAGE_UPLOAD_MB="")
        assert get_max_image_upload_mb() == 10

    def test_returns_set_value(self, temp_env_vars):
        temp_env_vars(MAX_IMAGE_UPLOAD_MB="5")
        assert get_max_image_upload_mb() == 5

    def test_invalid_string_falls_back_to_default(self, temp_env_vars):
        temp_env_vars(MAX_IMAGE_UPLOAD_MB="not-a-number")
        assert get_max_image_upload_mb() == 10

    def test_clamps_below_minimum(self, temp_env_vars):
        temp_env_vars(MAX_IMAGE_UPLOAD_MB="0")
        assert get_max_image_upload_mb() == 1

    def test_clamps_above_ceiling(self, temp_env_vars):
        temp_env_vars(MAX_IMAGE_UPLOAD_MB="999")
        assert get_max_image_upload_mb() == 25

    def test_bytes_helper_multiplies_by_1024_squared(self, temp_env_vars):
        temp_env_vars(MAX_IMAGE_UPLOAD_MB="3")
        assert get_max_image_upload_bytes() == 3 * 1024 * 1024


class TestGetRegistrationImageMaxEdgePx:
    """Test the get_registration_image_max_edge_px function."""

    def test_returns_default_when_not_set(self, clear_env_vars):
        clear_env_vars("REGISTRATION_IMAGE_MAX_EDGE_PX")
        assert get_registration_image_max_edge_px() == 2048

    def test_returns_set_value(self, temp_env_vars):
        temp_env_vars(REGISTRATION_IMAGE_MAX_EDGE_PX="1024")
        assert get_registration_image_max_edge_px() == 1024

    def test_invalid_string_falls_back_to_default(self, temp_env_vars):
        temp_env_vars(REGISTRATION_IMAGE_MAX_EDGE_PX="huge")
        assert get_registration_image_max_edge_px() == 2048

    def test_clamps_below_minimum(self, temp_env_vars):
        temp_env_vars(REGISTRATION_IMAGE_MAX_EDGE_PX="10")
        assert get_registration_image_max_edge_px() == 256

    def test_clamps_above_ceiling(self, temp_env_vars):
        temp_env_vars(REGISTRATION_IMAGE_MAX_EDGE_PX="99999")
        assert get_registration_image_max_edge_px() == 4096


class TestGetMaxImagesPerRegistrationPage:
    """Test the get_max_images_per_registration_page function."""

    def test_returns_default_when_not_set(self, clear_env_vars):
        clear_env_vars("MAX_IMAGES_PER_REGISTRATION_PAGE")
        assert get_max_images_per_registration_page() == 10

    def test_returns_set_value(self, temp_env_vars):
        temp_env_vars(MAX_IMAGES_PER_REGISTRATION_PAGE="3")
        assert get_max_images_per_registration_page() == 3

    def test_invalid_string_falls_back_to_default(self, temp_env_vars):
        temp_env_vars(MAX_IMAGES_PER_REGISTRATION_PAGE="lots")
        assert get_max_images_per_registration_page() == 10

    def test_clamps_below_minimum(self, temp_env_vars):
        temp_env_vars(MAX_IMAGES_PER_REGISTRATION_PAGE="0")
        assert get_max_images_per_registration_page() == 1

    def test_clamps_above_ceiling(self, temp_env_vars):
        temp_env_vars(MAX_IMAGES_PER_REGISTRATION_PAGE="500")
        assert get_max_images_per_registration_page() == 50
