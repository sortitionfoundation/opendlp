"""ABOUTME: Unit tests for the user_msg() convention on OpenDLP exceptions
ABOUTME: Pins down that only exceptions opting in via CuratedMessage expose their own message"""

import pytest

from opendlp.domain.registration_page import RegistrationPageNotReady
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    CannotDisableSelf,
    CannotRemoveLastAuthMethod,
    CuratedMessage,
    DocumentQuotaExceeded,
    EmailNotConfirmed,
    EmailTemplateInvalid,
    EmailTemplateNotFoundError,
    GoogleSheetConfigNotFoundError,
    ImageQuotaExceeded,
    InsufficientPermissions,
    InvalidConfirmationToken,
    InvalidCredentials,
    InvalidInvite,
    InvalidResetToken,
    InvalidSelection,
    InviteNotFoundError,
    NotFoundError,
    OAuthError,
    OAuthStateError,
    OpenDLPError,
    PasswordTooWeak,
    RateLimitExceeded,
    RegistrationDocumentNotFoundError,
    RegistrationImageNotFoundError,
    RegistrationPageNotFoundError,
    RespondentNotFoundError,
    SelectionRunRecordNotFoundError,
    ServiceLayerError,
    UserAlreadyExists,
    UserNotFoundError,
)

CURATED = [
    UserAlreadyExists("someone@example.org"),
    InvalidCredentials(),
    InvalidInvite(code="ABC123", reason="expired"),
    InsufficientPermissions(action="publish", required_role="organiser"),
    InvalidResetToken(reason="already used"),
    EmailNotConfirmed(),
    InvalidConfirmationToken(reason="expired"),
    RateLimitExceeded(operation="password reset", retry_after_seconds=60),
    ImageQuotaExceeded(limit=5),
    DocumentQuotaExceeded(limit=3),
    EmailTemplateInvalid(["Subject is empty"]),
    OAuthError(provider="google", reason="the token exchange was refused"),
    OAuthStateError(),
    CannotRemoveLastAuthMethod(),
    CannotDisableSelf(),
]

UNCURATED = [
    ServiceLayerError("uow.commit() failed after 3 retries"),
    PasswordTooWeak("hash comparison against bcrypt round 12 failed"),
    InvalidSelection("CSV must have 'id' column"),
    NotFoundError("Assembly 0f8f-... not found in table assemblies"),
    UserNotFoundError("no row for user_id=0f8f-... in table users"),
    AssemblyNotFoundError("Assembly 0f8f-... not found"),
    InviteNotFoundError("Invite 0f8f-... not found in table user_invites"),
    GoogleSheetConfigNotFoundError("No sheet config for assembly 0f8f-..."),
    RegistrationPageNotFoundError("Registration page 0f8f-... has no HTML source"),
    RegistrationImageNotFoundError("Image 0f8f-... not found in table registration_images"),
    RegistrationDocumentNotFoundError("Document 0f8f-... not found in table registration_documents"),
    EmailTemplateNotFoundError("Template 0f8f-... not found in table email_templates"),
    SelectionRunRecordNotFoundError("Selection run 0f8f-... not found"),
    RespondentNotFoundError("no row for respondent_id=0f8f-... in table respondents"),
]


def _all_subclasses(cls: type) -> set[type]:
    """Every subclass of ``cls``, however deep in the tree."""
    found = set()
    for subclass in cls.__subclasses__():
        found.add(subclass)
        found |= _all_subclasses(subclass)
    return found


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


class TestEveryExceptionIsClassified:
    """The lists above must name every exception, so each one is a decision someone made.

    Without this, a new user-facing exception that forgets the mixin degrades to the
    generic message and no test notices - the failure the convention is most exposed to.
    """

    def test_no_exception_is_left_unclassified(self) -> None:
        # Only our own classes: a subclass defined inside a test would otherwise show up
        # here, its presence depending on which test modules had been imported.
        ours = {cls for cls in _all_subclasses(OpenDLPError) if cls.__module__.startswith("opendlp")}
        classified = {type(exc) for exc in CURATED + UNCURATED}
        unclassified = sorted(cls.__name__ for cls in ours - classified)

        assert not unclassified, (
            f"Not listed in CURATED or UNCURATED: {', '.join(unclassified)}. "
            "Decide for each whether its message is written for a user to read - if it is, "
            "mix in CuratedMessage and add it to CURATED; if not, add it to UNCURATED."
        )


class TestTheOptInDoesNotDependOnBaseOrder:
    """CuratedMessage supplies curated_msg(), a name the base does not define.

    That is the whole reason both base orders work. These tests pin the property
    down so a future tidy-up cannot quietly remove it.
    """

    def test_the_base_does_not_define_the_hook(self) -> None:
        assert not hasattr(OpenDLPError, "curated_msg")

    def test_the_mixin_works_listed_first(self) -> None:
        class MixinFirst(CuratedMessage, ServiceLayerError):
            pass

        assert MixinFirst("a message written for a user").user_msg() == "a message written for a user"

    def test_the_mixin_works_listed_last(self) -> None:
        class MixinLast(ServiceLayerError, CuratedMessage):
            pass

        assert MixinLast("a message written for a user").user_msg() == "a message written for a user"


class TestDomainExceptionsFollowingTheSameProtocol:
    """RegistrationPageNotReady cannot use the mixin - the domain must not import the service layer."""

    def test_readiness_problems_are_user_facing(self) -> None:
        exc = RegistrationPageNotReady(["The form HTML is empty", "The page needs a URL slug"])

        assert exc.user_msg() == "The form HTML is empty; The page needs a URL slug"

    def test_implements_user_msg_so_callers_can_duck_type(self) -> None:
        assert hasattr(RegistrationPageNotReady([]), "user_msg")
