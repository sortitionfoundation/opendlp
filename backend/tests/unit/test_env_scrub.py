"""ABOUTME: Tests for the autouse fixture that keeps a developer's .env out of the test run.
ABOUTME: Includes a guard that fails when a new setting is added and not classified."""

import ast
import os
import pathlib

from opendlp.feature_flags import has_feature
from tests.conftest import (
    ENV_KEYS_TESTS_MAY_INHERIT,
    FEATURE_FLAG_PREFIX,
    LEAKY_ENV_KEYS,
    LEAKY_ENV_PREFIXES,
    SCRUBBED_ENV_PREFIXES,
    TEST_FEATURE_FLAGS,
)

SOURCE_ROOT = pathlib.Path(__file__).parents[2] / "src" / "opendlp"


def _env_key_node(node: ast.AST) -> ast.AST | None:
    """The node giving the variable name, if this node reads the environment."""
    if isinstance(node, ast.Subscript):
        value = node.value
        if isinstance(value, ast.Attribute) and value.attr == "environ":
            return node.slice
        return None
    if isinstance(node, ast.Call):
        func = node.func
        environ_get = (
            isinstance(func, ast.Attribute)
            and func.attr == "get"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "environ"
        )
        getenv = isinstance(func, ast.Attribute) and func.attr == "getenv"
        if (environ_get or getenv) and node.args:
            return node.args[0]
    return None


def _string_value(node: ast.AST | None) -> str:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else ""


def _literal_keys(tree: ast.AST) -> set[str]:
    """Names read directly, as in ``os.environ.get("DB_HOST")``."""
    return {name for node in ast.walk(tree) if (name := _string_value(_env_key_node(node)))}


def _env_reading_helpers(tree: ast.AST) -> dict[str, int]:
    """Functions that read the environment using one of their own parameters as the key.

    Found rather than listed: naming the helpers here would rot exactly the way
    this test exists to prevent.
    """
    helpers: dict[str, int] = {}
    for function in ast.walk(tree):
        if not isinstance(function, ast.FunctionDef):
            continue
        params = {arg.arg: index for index, arg in enumerate(function.args.args)}
        for node in ast.walk(function):
            key = _env_key_node(node)
            if isinstance(key, ast.Name) and key.id in params:
                helpers[function.name] = params[key.id]
    return helpers


def _keys_passed_to_helpers(tree: ast.AST, helpers: dict[str, int]) -> set[str]:
    """Names handed to one of those helpers as a literal, at its call site."""
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
            continue
        index = helpers.get(node.func.id)
        if index is not None and len(node.args) > index and (name := _string_value(node.args[index])):
            keys.add(name)
    return keys


def environment_variables_the_app_reads() -> set[str]:
    """Every environment variable name the application looks up, read from the source.

    Two passes, because several settings are read through a helper that takes the
    name as an argument, so the name only appears at the call site.
    """
    trees = [ast.parse(path.read_text()) for path in SOURCE_ROOT.rglob("*.py")]

    helpers: dict[str, int] = {}
    keys: set[str] = set()
    for tree in trees:
        helpers.update(_env_reading_helpers(tree))
        keys |= _literal_keys(tree)

    for tree in trees:
        keys |= _keys_passed_to_helpers(tree, helpers)

    return keys


def _is_scrubbed(key: str) -> bool:
    return key.startswith(SCRUBBED_ENV_PREFIXES) or key in LEAKY_ENV_KEYS


class TestEverySettingIsClassified:
    def test_the_scanner_finds_the_settings_it_is_meant_to(self):
        """Guards the guard: a scanner that silently found nothing would pass everything."""
        found = environment_variables_the_app_reads()

        assert "DB_HOST" in found, "direct os.environ.get() read not found"
        assert "MAX_CSV_UPLOAD_MB" in found, "read via a helper taking the name as an argument not found"
        assert len(found) > 50

    def test_no_setting_is_left_unclassified(self):
        unclassified = sorted(
            key
            for key in environment_variables_the_app_reads()
            if not _is_scrubbed(key) and key not in ENV_KEYS_TESTS_MAY_INHERIT
        )

        assert not unclassified, (
            f"tests/conftest.py neither scrubs nor allows: {', '.join(unclassified)}.\n"
            "Add each to LEAKY_ENV_KEYS (or a prefix) if a value in someone's .env could change "
            "how a test behaves, or to ENV_KEYS_TESTS_MAY_INHERIT if the suite needs it from .env."
        )

    def test_nothing_is_both_scrubbed_and_allowed(self):
        assert [key for key in ENV_KEYS_TESTS_MAY_INHERIT if _is_scrubbed(key)] == []


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

    def test_the_infrastructure_settings_are_left_alone(self):
        """The integration and BDD suites need these from .env."""
        for key in ("DB_HOST", "DB_PASSWORD", "REDIS_HOST"):
            assert not _is_scrubbed(key)
