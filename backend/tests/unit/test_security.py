# ABOUTME: Unit tests for the password helpers in service_layer.security
# ABOUTME: Hashes that must never match, and the password rules the sign-up page lists against those enforced

import pytest

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import security
from opendlp.service_layer.security import (
    TempUser,
    get_password_validators,
    hash_password,
    password_requirements,
    validate_password_strength,
    verify_password,
)
from opendlp.vendor import password_validation as pv


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
        assert password_requirements() == [
            "10–256 characters",
            "Include at least one letter",
            "Not be a commonly used password",
            "Not be too similar to your personal information",
        ]

    def test_the_length_line_takes_its_numbers_from_the_validators(self, monkeypatch):
        validators = (pv.MinimumLengthValidator(min_length=12), pv.MaximumLengthValidator(max_length=64))
        monkeypatch.setattr(security, "get_password_validators", lambda: validators)

        assert password_requirements()[0] == "12–64 characters"

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

    @pytest.mark.parametrize(
        ("password", "accepted"),
        [
            pytest.param("Kx7#mQ2vLp", True, id="10 characters"),
            pytest.param("Kx7#mQ2vL", False, id="9 characters"),
            pytest.param("Kx7#mQ2vLp" * 25 + "Kx7#mQ", True, id="256 characters"),
            pytest.param("Kx7#mQ2vLp" * 25 + "Kx7#mQ2", False, id="257 characters"),
            pytest.param("password123", False, id="a commonly used password"),
            pytest.param("ann.smith@example", False, id="too similar to the email address"),
            pytest.param("4719305826", False, id="digits alone"),
        ],
    )
    def test_each_line_is_enforced_as_written(self, password: str, accepted: bool):
        user = TempUser(email="ann.smith@example.org", first_name="Ann", last_name="Smith")

        assert validate_password_strength(password, user)[0] is accepted
