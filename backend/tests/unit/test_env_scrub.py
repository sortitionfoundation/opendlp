"""ABOUTME: Tests for the autouse fixture that keeps a developer's .env out of the test run.
ABOUTME: Without it a green CI run says nothing about whether the suite passes locally."""

import os

from opendlp.feature_flags import has_feature
from tests.conftest import FEATURE_FLAG_PREFIX, LEAKY_ENV_KEYS, LEAKY_ENV_PREFIXES, TEST_FEATURE_FLAGS


class TestTheEnvironmentEveryTestSees:
    def test_no_feature_flag_is_on_unless_the_suite_asked_for_it(self):
        """A flag set in .env must not reach a test that did not opt into it."""
        on = {
            key
            for key in os.environ
            if key.startswith(FEATURE_FLAG_PREFIX) and has_feature(key[len(FEATURE_FLAG_PREFIX) :])
        }
        assert on == set(TEST_FEATURE_FLAGS)

    def test_the_declared_test_flags_are_on(self):
        for key in TEST_FEATURE_FLAGS:
            assert has_feature(key[len(FEATURE_FLAG_PREFIX) :])

    def test_the_leaky_variables_are_unset(self):
        """Deleted rather than blanked: "not set" is the state the config defaults assume."""
        assert [key for key in LEAKY_ENV_KEYS if key in os.environ] == []
        assert [key for key in os.environ if key.startswith(LEAKY_ENV_PREFIXES)] == []

    def test_the_database_settings_are_left_alone(self):
        """The integration and BDD suites need these from .env."""
        for key in ("DB_HOST", "DB_PASSWORD", "REDIS_HOST"):
            assert key not in LEAKY_ENV_KEYS
            assert not key.startswith(LEAKY_ENV_PREFIXES)
