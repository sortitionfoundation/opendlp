# ABOUTME: Unit tests for the password helpers in service_layer.security
# ABOUTME: Hashes that must never match, and the password rules the sign-up page lists and ticks against those enforced

import json
from pathlib import Path

import pytest

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import security
from opendlp.service_layer.security import (
    PASSWORD_RULE_VALIDATORS,
    TempUser,
    get_password_validators,
    hash_password,
    password_requirements,
    password_rule_results,
    validate_password_strength,
    verify_password,
)
from opendlp.vendor import password_validation as pv

# The cases password-rules.test.js runs through the page's script.
BROWSER_CHECKS = json.loads((Path(__file__).parents[1] / "fixtures" / "password_browser_checks.json").read_text())

ANN = TempUser(email="ann.smith@example.org", first_name="Ann", last_name="Smith")

ENFORCED_AS_WRITTEN = [
    pytest.param("Kx7#mQ2vLp", True, id="10 characters"),
    pytest.param("Kx7#mQ2vL", False, id="9 characters"),
    pytest.param("Kx7#mQ2vLp" * 25 + "Kx7#mQ", True, id="256 characters"),
    pytest.param("Kx7#mQ2vLp" * 25 + "Kx7#mQ2", False, id="257 characters"),
    pytest.param("password123", False, id="a commonly used password"),
    pytest.param("ann.smith@example", False, id="too similar to the email address"),
    pytest.param("4719305826", False, id="numbers only"),
    pytest.param("4719305826!", True, id="numbers and a symbol, no letter"),
]


class TestVerifyPassword:
    """A hash only matches when it is a real hash of the password given."""

    def test_the_right_password_matches_its_hash(self):
        assert verify_password("CorrectHorse123!", hash_password("CorrectHorse123!")) is True

    def test_the_wrong_password_does_not_match(self):
        assert verify_password("WrongHorse123!", hash_password("CorrectHorse123!")) is False

    def test_an_unusable_hash_never_matches(self):
        """The hash a lockout leaves behind: no input may open the account."""
        user = User(
            email="locked@example.com",
            global_role=GlobalRole.USER,
            password_hash=hash_password("OriginalPassw0rd!"),
        )
        user.set_unusable_password()

        assert verify_password("OriginalPassw0rd!", user.password_hash) is False
        assert verify_password(user.password_hash, user.password_hash) is False
        assert verify_password("", user.password_hash) is False

    def test_an_empty_hash_never_matches(self):
        """An OAuth-only user has no password hash, and an empty guess is still not a password."""
        assert verify_password("anything", "") is False
        assert verify_password("", "") is False


class TestPasswordRequirements:
    """The sign-up page's short list of password rules, held to the validators that enforce them."""

    def test_the_list_is_the_designs_wording(self):
        assert [requirement.text for requirement in password_requirements()] == [
            "10–256 characters",
            "Not be numbers only",
            "Not be a commonly used password",
            "Not be too similar to your personal information",
        ]

    def test_the_length_line_takes_its_numbers_from_the_validators(self, monkeypatch):
        validators = (pv.MinimumLengthValidator(min_length=12), pv.MaximumLengthValidator(max_length=64))
        monkeypatch.setattr(security, "get_password_validators", lambda: validators)

        length = password_requirements()[0]
        assert length.text == "12–64 characters"
        assert (length.min_length, length.max_length) == (12, 64)

    def test_every_validator_has_a_line(self):
        """Adding or removing a validator has to change the list as well.

        The two length validators share the first line. If this fails, make
        password_requirements() say what the new set of validators enforces.
        """
        assert {type(validator) for validator in get_password_validators()} == {
            pv.MinimumLengthValidator,
            pv.MaximumLengthValidator,
            pv.NumericPasswordValidator,
            pv.SafeCommonPasswordValidator,
            pv.UserAttributeSimilarityValidator,
        }

    def test_each_line_has_the_key_its_validators_are_listed_under(self):
        """The keys name the lines to the page's script and to the password check."""
        assert [requirement.key for requirement in password_requirements()] == list(PASSWORD_RULE_VALIDATORS)

    def test_the_browser_checks_the_length_and_digits_lines_and_the_server_the_rest(self):
        """The browser decides only what it can decide exactly as the validators do."""
        assert {requirement.key: requirement.live_check for requirement in password_requirements()} == {
            "length": "browser",
            "not-numbers-only": "browser",
            "not-common": "server",
            "not-similar": "server",
        }

    @pytest.mark.parametrize(("password", "accepted"), ENFORCED_AS_WRITTEN)
    def test_each_line_is_enforced_as_written(self, password: str, accepted: bool):
        assert validate_password_strength(password, ANN)[0] is accepted


class TestPasswordRuleResults:
    """The password check's verdicts, rule by rule, from the validators that run when the form is sent."""

    @pytest.mark.parametrize(
        ("password", "unmet"),
        [
            pytest.param("Kx7#mQ2vLp", set(), id="every rule met"),
            pytest.param("Kx7#mQ2vL", {"length"}, id="9 characters"),
            pytest.param("4719305826", {"not-numbers-only"}, id="numbers only"),
            pytest.param("password123", {"not-common"}, id="a commonly used password"),
            pytest.param("ann.smith@example", {"not-similar"}, id="too similar to the email address"),
            pytest.param("1234567", {"length", "not-numbers-only", "not-common"}, id="short, digits, common"),
        ],
    )
    def test_each_rule_is_decided_by_its_own_validators(self, password: str, unmet: set[str]):
        results = password_rule_results(password, ANN)

        assert set(results) == {"length", "not-numbers-only", "not-common", "not-similar"}
        assert {key for key, met in results.items() if not met} == unmet

    @pytest.mark.parametrize(("password", "accepted"), ENFORCED_AS_WRITTEN)
    def test_every_rule_is_met_exactly_when_the_form_would_accept_the_password(self, password: str, accepted: bool):
        assert all(password_rule_results(password, ANN).values()) is accepted

    def test_the_personal_information_rule_compares_with_the_details_given(self):
        """The page asks again when the email or a name changes, because the answer depends on them."""
        assert password_rule_results("ann.smith@example", TempUser(email=""))["not-similar"] is True
        assert password_rule_results("ann.smith@example", ANN)["not-similar"] is False

    def test_every_validator_decides_one_rule(self):
        """A validator added or removed has to change the rules as well."""
        listed = [validator_type for types in PASSWORD_RULE_VALIDATORS.values() for validator_type in types]

        assert list(PASSWORD_RULE_VALIDATORS) == ["length", "not-numbers-only", "not-common", "not-similar"]
        assert len(listed) == len(set(listed))
        assert set(listed) == {type(validator) for validator in get_password_validators()}


class TestBrowserChecksAgreeWithTheValidators:
    """The two rules the page decides in the browser, on passwords where that is easy to get wrong.

    password-rules.test.js runs the same cases through the page's script, so a
    rule the browser ticks is a rule the validators accept.
    """

    def test_the_cases_use_the_validators_numbers(self):
        length = password_requirements()[0]

        assert (BROWSER_CHECKS["min_length"], BROWSER_CHECKS["max_length"]) == (length.min_length, length.max_length)

    def test_the_cases_cover_the_rules_the_browser_checks(self):
        browser_keys = {
            requirement.key for requirement in password_requirements() if requirement.live_check == "browser"
        }

        assert all(set(case["rules"]) == browser_keys for case in BROWSER_CHECKS["cases"])

    @pytest.mark.parametrize("case", BROWSER_CHECKS["cases"], ids=lambda case: case["why"])
    def test_the_validators_decide_each_case_as_the_browser_does(self, case: dict):
        results = password_rule_results(case["typed"], TempUser(email=""))

        assert {key: results[key] for key in case["rules"]} == case["rules"]
