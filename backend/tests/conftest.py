"""ABOUTME: Pytest configuration and fixtures for OpenDLP tests
ABOUTME: Provides test fixtures and configuration for unit, integration, and e2e tests"""

import os

import pytest

from opendlp.config import FlaskTestConfig, get_config


@pytest.fixture(scope="session")
def test_config():
    """Provide test configuration for the entire test session."""
    # Ensure we're using test configuration
    os.environ["FLASK_ENV"] = "testing"
    return FlaskTestConfig()


@pytest.fixture(scope="function")
def config():
    """Provide configuration for individual test functions."""
    return get_config()


@pytest.fixture(autouse=True)
def set_test_env():
    """Automatically set test environment for all tests."""
    original_env = os.environ.get("FLASK_ENV")
    os.environ["FLASK_ENV"] = "testing"
    yield
    if original_env is not None:
        os.environ["FLASK_ENV"] = original_env
    else:
        os.environ.pop("FLASK_ENV", None)


@pytest.fixture
def temp_env_vars():
    """Fixture to temporarily set environment variables for testing."""
    original_vars = {}

    def _set_env_vars(**kwargs):
        for key, value in kwargs.items():
            original_vars[key] = os.environ.get(key)
            os.environ[key] = value

    yield _set_env_vars

    # Restore original environment variables
    for key, value in original_vars.items():
        if value is not None:
            os.environ[key] = value
        else:
            os.environ.pop(key, None)
