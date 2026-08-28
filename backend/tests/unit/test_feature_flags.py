"""ABOUTME: Unit tests for the feature flags module.
ABOUTME: Tests has_feature() with various truthy/falsy values, case-insensitivity, and reload."""

import os

import pytest

from opendlp.feature_flags import has_feature, reload_flags, showcase_enabled


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Remove any FF_* vars that may leak between tests, then reload flags."""
    # Clear all FF_* vars from env
    for key in list(os.environ):
        if key.startswith("FF_"):
            monkeypatch.delenv(key, raising=False)
    reload_flags()
    yield
    reload_flags()


class TestHasFeature:
    """Test the has_feature function."""

    def test_returns_true_for_enabled_flag(self, monkeypatch):
        monkeypatch.setenv("FF_MY_FEATURE", "true")
        reload_flags()
        assert has_feature("my_feature") is True

    def test_returns_false_for_unset_flag(self):
        assert has_feature("nonexistent_flag") is False

    def test_returns_false_for_disabled_flag(self, monkeypatch):
        monkeypatch.setenv("FF_DISABLED", "false")
        reload_flags()
        assert has_feature("disabled") is False

    def test_case_insensitive_lookup(self, monkeypatch):
        monkeypatch.setenv("FF_SOME_THING", "1")
        reload_flags()
        assert has_feature("some_thing") is True
        assert has_feature("SOME_THING") is True
        assert has_feature("Some_Thing") is True

    @pytest.mark.parametrize("value", ["true", "yes", "on", "1", "True", "YES", "ON"])
    def test_truthy_values(self, monkeypatch, value):
        monkeypatch.setenv("FF_TRUTHY", value)
        reload_flags()
        assert has_feature("truthy") is True

    @pytest.mark.parametrize("value", ["false", "no", "off", "0", "False", "NO", "OFF"])
    def test_falsy_values(self, monkeypatch, value):
        monkeypatch.setenv("FF_FALSY", value)
        reload_flags()
        assert has_feature("falsy") is False

    def test_empty_value_is_false(self, monkeypatch):
        monkeypatch.setenv("FF_EMPTY", "")
        reload_flags()
        assert has_feature("empty") is False

    def test_non_ff_vars_are_ignored(self, monkeypatch):
        monkeypatch.setenv("NOT_A_FLAG", "true")
        reload_flags()
        assert has_feature("not_a_flag") is False
        assert has_feature("a_flag") is False

    def test_multiple_flags(self, monkeypatch):
        monkeypatch.setenv("FF_ALPHA", "true")
        monkeypatch.setenv("FF_BETA", "false")
        monkeypatch.setenv("FF_GAMMA", "1")
        reload_flags()
        assert has_feature("alpha") is True
        assert has_feature("beta") is False
        assert has_feature("gamma") is True

    def test_reload_picks_up_new_vars(self, monkeypatch):
        assert has_feature("late_add") is False
        monkeypatch.setenv("FF_LATE_ADD", "yes")
        reload_flags()
        assert has_feature("late_add") is True


class TestShowcaseEnabled:
    """Where the component showcase at /backoffice/showcase is served.

    The only flag whose default depends on the environment: always on where
    people are building the thing, opt-in on an install that faces the world.
    """

    def test_on_in_development_without_any_flag(self, monkeypatch):
        monkeypatch.setenv("FLASK_ENV", "development")
        assert showcase_enabled() is True

    def test_on_in_testing_without_any_flag(self, monkeypatch):
        """Every existing showcase test relies on this."""
        monkeypatch.setenv("FLASK_ENV", "testing")
        assert showcase_enabled() is True

    def test_off_in_production_by_default(self, monkeypatch):
        monkeypatch.setenv("FLASK_ENV", "production")
        assert showcase_enabled() is False

    def test_on_in_production_when_the_install_asks_for_it(self, monkeypatch):
        """What a staging server sets."""
        monkeypatch.setenv("FLASK_ENV", "production")
        monkeypatch.setenv("FF_SHOWCASE", "true")
        reload_flags()
        assert showcase_enabled() is True

    def test_the_flag_alone_does_not_turn_it_off_elsewhere(self, monkeypatch):
        """FF_SHOWCASE=false is about production; development keeps it."""
        monkeypatch.setenv("FLASK_ENV", "development")
        monkeypatch.setenv("FF_SHOWCASE", "false")
        reload_flags()
        assert showcase_enabled() is True
