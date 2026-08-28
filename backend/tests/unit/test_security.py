# ABOUTME: Unit tests for the password hashing and verification helpers in service_layer.security
# ABOUTME: Covers the hashes that must never match - unusable ones from a lockout, and empty ones

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.security import hash_password, verify_password


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
