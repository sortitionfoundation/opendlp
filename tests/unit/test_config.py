"""ABOUTME: Unit tests for OpenDLP configuration module
ABOUTME: Tests environment variable loading and configuration class behavior"""

from typing import ClassVar

import pytest

from opendlp.config import FlaskProductionConfig, to_bool


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
    def test_to_bool(self, bool_str: str, expected: bool) -> None:
        assert to_bool(bool_str) == expected


class TestProductionConfig:
    """Test the ProductionConfig class."""

    def test_production_config_with_secret_key(self, temp_env_vars):
        """Test that ProductionConfig works with proper SECRET_KEY."""
        temp_env_vars(SECRET_KEY="production-secret-key")

        config = FlaskProductionConfig()

        assert config.SECRET_KEY == "production-secret-key"

    def test_production_config_without_secret_key(self):
        """Test that ProductionConfig raises error without proper SECRET_KEY."""
        with pytest.raises(ValueError, match="SECRET_KEY must be set in production"):
            FlaskProductionConfig()
