"""ABOUTME: Custom exceptions for service layer operations
ABOUTME: Defines business logic exceptions with proper error messages and codes"""

from typing import Protocol, runtime_checkable

# Re-exported so service-layer callers import it from the usual exceptions module.
from opendlp.domain.registration_page import RegistrationPageNotReady
from opendlp.domain.validators import SlugError
from opendlp.translations import gettext as _

__all__ = [
    "AssemblyNotFoundError",
    "CannotRemoveLastAuthMethod",
    "CuratedMessage",
    "DocumentQuotaExceeded",
    "EmailNotConfirmed",
    "EmailTemplateInvalid",
    "EmailTemplateNotFoundError",
    "GoogleSheetConfigNotFoundError",
    "HasCuratedMessage",
    "ImageQuotaExceeded",
    "InsufficientPermissions",
    "InvalidConfirmationToken",
    "InvalidCredentials",
    "InvalidInvite",
    "InvalidResetToken",
    "InvalidSelection",
    "InviteNotFoundError",
    "NotFoundError",
    "OAuthError",
    "OAuthStateError",
    "OpenDLPError",
    "PasswordTooWeak",
    "RateLimitExceeded",
    "RegistrationDocumentNotFoundError",
    "RegistrationImageNotFoundError",
    "RegistrationPageNotFoundError",
    "RegistrationPageNotReady",
    "RespondentNotFoundError",
    "SelectionRunRecordNotFoundError",
    "ServiceLayerError",
    "SlugError",
    "UserAlreadyExists",
    "UserNotFoundError",
]


@runtime_checkable
class HasCuratedMessage(Protocol):
    """Structural type for exceptions that supply their own user-facing message.

    ``curated_msg`` is deliberately a name :class:`OpenDLPError` does not itself
    define, which is what makes the opt-in independent of base-class order. The
    method exists in one place only, so there is no resolution for
    ``class X(ServiceLayerError, CuratedMessage)`` to lose.

    Do not give ``OpenDLPError`` a ``curated_msg()`` of its own. That reinstates
    the name collision, and then whether a class gets its curated message back
    depends on which way round its bases happen to be written.
    """

    def curated_msg(self) -> str: ...


class OpenDLPError(Exception):
    """Base exception for all our custom errors."""

    def user_msg(self) -> str:
        """The message that may be shown to a user or returned in a JSON response.

        Deliberately generic rather than ``str(self)``. An exception message may
        carry internal detail, so the default assumes it does; subclasses whose
        message is written for a user opt in via :class:`CuratedMessage`. A class
        that forgets says too little, which is a much better failure than leaking
        internals - and better than raising, which would turn a handled error
        into a 500 with no feedback at all.

        Do not change the fallback to return ``str(self)``: that would silently
        make every exception in the tree claim to be safe to show, which is the
        problem this method exists to solve.
        """
        if isinstance(self, HasCuratedMessage):
            return self.curated_msg()
        return _("Something went wrong. Please try again.")


class CuratedMessage:
    """Mixin for exceptions whose ``str()`` is a curated, user-facing message.

    Mix in only where the message is built for a user to read - translated, and
    free of internal detail. It is what makes "is this safe to show?" answerable
    by looking at the class rather than by reading every call site.

    Supplies the :class:`HasCuratedMessage` hook rather than overriding
    ``user_msg()``, so it works whichever order the bases are written in.
    """

    def curated_msg(self) -> str:
        return str(self)


class ServiceLayerError(OpenDLPError):
    """Base exception for all service layer errors."""


class PasswordTooWeak(ServiceLayerError):
    """Exception if the password is too weak."""


class UserAlreadyExists(CuratedMessage, ServiceLayerError):
    """Raised when attempting to create a user that already exists."""

    def __init__(self, email: str = "") -> None:
        message = _("User with email '%(email)s' already exists", email=email) if email else _("User already exists")
        super().__init__(message)
        self.email = email


class InvalidCredentials(CuratedMessage, ServiceLayerError):
    """Raised when authentication fails due to invalid credentials."""

    def __init__(self, message: str = "") -> None:
        if not message:
            message = _("Invalid email or password")
        super().__init__(message)


class InvalidInvite(CuratedMessage, ServiceLayerError):
    """Raised when an invite code is invalid, expired, or already used."""

    def __init__(self, code: str = "", reason: str = "") -> None:
        if code and reason:
            message = _("Invalid invite code '%(code)s': %(reason)s", code=code, reason=reason)
        elif code:
            message = _("Invalid invite code '%(code)s'", code=code)
        elif reason:
            message = _("Invalid invite code: %(reason)s", reason=reason)
        else:
            message = _("Invalid invite code")
        super().__init__(message)
        self.code = code
        self.reason = reason


class InsufficientPermissions(CuratedMessage, ServiceLayerError):
    """Raised when a user lacks permissions for an operation."""

    def __init__(self, action: str = "", required_role: str = "") -> None:
        if action and required_role:
            message = _(
                "Insufficient permissions for action: %(action)s (requires role: %(required_role)s)",
                action=action,
                required_role=required_role,
            )
        elif action:
            message = _("Insufficient permissions for action: %(action)s", action=action)
        elif required_role:
            message = _("Insufficient permissions (requires role: %(required_role)s)", required_role=required_role)
        else:
            message = _("Insufficient permissions")
        super().__init__(message)
        self.action = action
        self.required_role = required_role


class InvalidResetToken(CuratedMessage, ServiceLayerError):
    """Raised when a password reset token is invalid, expired, or already used."""

    def __init__(self, reason: str = "") -> None:
        if reason:
            message = _("Invalid password reset token: %(reason)s", reason=reason)
        else:
            message = _("Invalid password reset token")
        super().__init__(message)
        self.reason = reason


class EmailNotConfirmed(CuratedMessage, ServiceLayerError):
    """Raised when user tries to login without confirming email."""

    def __init__(self) -> None:
        super().__init__(_("Please confirm your email address before logging in."))


class InvalidConfirmationToken(CuratedMessage, ServiceLayerError):
    """Raised when email confirmation token is invalid, expired, or already used."""

    def __init__(self, reason: str = "") -> None:
        if reason:
            message = _("Invalid or expired confirmation link: %(reason)s", reason=reason)
        else:
            message = _("Invalid or expired confirmation link")
        super().__init__(message)
        self.reason = reason


class RateLimitExceeded(CuratedMessage, ServiceLayerError):
    """Raised when a user has exceeded rate limits for an operation."""

    def __init__(self, operation: str = "", retry_after_seconds: int = 0) -> None:
        if operation and retry_after_seconds:
            message = _(
                "Rate limit exceeded for %(operation)s. Please try again in %(seconds)s seconds",
                operation=operation,
                seconds=retry_after_seconds,
            )
        elif operation:
            message = _("Rate limit exceeded for %(operation)s", operation=operation)
        else:
            message = _("Rate limit exceeded. Please try again later")
        super().__init__(message)
        self.operation = operation
        self.retry_after_seconds = retry_after_seconds


class InvalidSelection(ServiceLayerError):
    """Error for when we can't do selection because something is invalid"""


class NotFoundError(ServiceLayerError):
    """General error to indicate something cannot be found in a repository"""


class UserNotFoundError(NotFoundError):
    """A user could not be found in the database"""


class AssemblyNotFoundError(NotFoundError):
    """An assembly could not be found in the database"""


class InviteNotFoundError(NotFoundError):
    """A user invite could not be found in the database"""


class GoogleSheetConfigNotFoundError(NotFoundError):
    """A Google Sheets configuration could not be found in the database"""


class RegistrationPageNotFoundError(NotFoundError):
    """A registration page could not be found in the database"""


class RegistrationImageNotFoundError(NotFoundError):
    """A registration image could not be found in the database"""


class RegistrationDocumentNotFoundError(NotFoundError):
    """A registration document could not be found in the database"""


class EmailTemplateNotFoundError(NotFoundError):
    """An email template could not be found in the database"""


class EmailTemplateInvalid(CuratedMessage, ServiceLayerError):
    """Raised when an email template fails validation, carrying the problem list."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


class ImageQuotaExceeded(CuratedMessage, ServiceLayerError):
    """Raised when a registration page already has the maximum number of images."""

    def __init__(self, limit: int) -> None:
        super().__init__(_("This registration page already has the maximum of %(limit)s images", limit=limit))


class DocumentQuotaExceeded(CuratedMessage, ServiceLayerError):
    """Raised when a registration page already has the maximum number of documents."""

    def __init__(self, limit: int) -> None:
        super().__init__(_("This registration page already has the maximum of %(limit)s documents", limit=limit))


class SelectionRunRecordNotFoundError(NotFoundError):
    """A selection run record could not be found in the database"""


class RespondentNotFoundError(NotFoundError):
    """A respondent could not be found in the database"""


class OAuthError(CuratedMessage, ServiceLayerError):
    """Raised when OAuth authentication fails."""

    def __init__(self, provider: str = "", reason: str = "") -> None:
        if provider and reason:
            message = _("OAuth authentication failed for %(provider)s: %(reason)s", provider=provider, reason=reason)
        elif provider:
            message = _("OAuth authentication failed for %(provider)s", provider=provider)
        elif reason:
            message = _("OAuth authentication failed: %(reason)s", reason=reason)
        else:
            message = _("OAuth authentication failed")
        super().__init__(message)
        self.provider = provider
        self.reason = reason


class OAuthStateError(OAuthError):
    """Raised when OAuth state validation fails (CSRF protection)."""

    def __init__(self) -> None:
        super().__init__(reason=_("Invalid OAuth state parameter"))


class CannotRemoveLastAuthMethod(CuratedMessage, ServiceLayerError):
    """Raised when attempting to remove the last authentication method."""

    def __init__(self) -> None:
        super().__init__(_("Cannot remove last authentication method. Add another method first."))


class CannotDisableSelf(CuratedMessage, ServiceLayerError):
    """Raised when an admin attempts to disable their own account."""

    def __init__(self) -> None:
        super().__init__(_("You cannot disable your own account"))
