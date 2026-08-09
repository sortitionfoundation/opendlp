"""ABOUTME: Unit tests for the user_msg() convention on OpenDLP exceptions
ABOUTME: Pins down that only exceptions opting in via CuratedMessage expose their own message"""

import pytest

from opendlp.domain.registration_page import RegistrationPageNotReady
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    CannotRemoveLastAuthMethod,
    CuratedMessage,
    DocumentQuotaExceeded,
    EmailTemplateInvalid,
    ImageQuotaExceeded,
    InsufficientPermissions,
    InvalidCredentials,
    InvalidSelection,
    NotFoundError,
    OpenDLPError,
    PasswordTooWeak,
    RegistrationPageNotFoundError,
    UserAlreadyExists,
)

CURATED = [
    UserAlreadyExists("someone@example.org"),
    InvalidCredentials(),
    InsufficientPermissions(action="publish", required_role="organiser"),
    ImageQuotaExceeded(limit=5),
    DocumentQuotaExceeded(limit=3),
    EmailTemplateInvalid(["Subject is empty"]),
    CannotRemoveLastAuthMethod(),
]

UNCURATED = [
    PasswordTooWeak("hash comparison against bcrypt round 12 failed"),
    InvalidSelection("CSV must have 'id' column"),
    NotFoundError("Assembly 0f8f-... not found in table assemblies"),
    AssemblyNotFoundError("Assembly 0f8f-... not found"),
    RegistrationPageNotFoundError("Registration page 0f8f-... has no HTML source"),
]


class TestCuratedExceptions:
    """Exceptions that opt in expose their own message, which is written for a reader."""

    @pytest.mark.parametrize("exc", CURATED, ids=lambda e: type(e).__name__)
    def test_user_msg_is_the_exception_message(self, exc: OpenDLPError) -> None:
        assert exc.user_msg() == str(exc)

    @pytest.mark.parametrize("exc", CURATED, ids=lambda e: type(e).__name__)
    def test_opts_in_through_the_mixin(self, exc: OpenDLPError) -> None:
        assert isinstance(exc, CuratedMessage)


class TestUncuratedExceptions:
    """Everything else gets the generic message, whatever its str() happens to hold."""

    @pytest.mark.parametrize("exc", UNCURATED, ids=lambda e: type(e).__name__)
    def test_user_msg_does_not_expose_the_exception_message(self, exc: OpenDLPError) -> None:
        assert exc.user_msg() != str(exc)

    @pytest.mark.parametrize("exc", UNCURATED, ids=lambda e: type(e).__name__)
    def test_user_msg_is_generic(self, exc: OpenDLPError) -> None:
        assert "Something went wrong" in exc.user_msg()

    def test_the_base_class_default_is_generic(self) -> None:
        assert "Something went wrong" in OpenDLPError("psycopg2 could not connect to host db").user_msg()

    def test_internal_detail_does_not_reach_the_user_message(self) -> None:
        exc = NotFoundError("no row for user_id=3f2b in table users on host db-primary")

        assert "db-primary" not in exc.user_msg()
        assert "3f2b" not in exc.user_msg()


class TestDomainExceptionsFollowingTheSameProtocol:
    """RegistrationPageNotReady cannot use the mixin - the domain must not import the service layer."""

    def test_readiness_problems_are_user_facing(self) -> None:
        exc = RegistrationPageNotReady(["The form HTML is empty", "The page needs a URL slug"])

        assert exc.user_msg() == "The form HTML is empty; The page needs a URL slug"

    def test_implements_user_msg_so_callers_can_duck_type(self) -> None:
        assert hasattr(RegistrationPageNotReady([]), "user_msg")
