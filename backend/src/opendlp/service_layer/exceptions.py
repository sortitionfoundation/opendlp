"""ABOUTME: Custom exceptions for service layer operations
ABOUTME: Defines business logic exceptions with proper error messages and codes"""

from opendlp.translations import gettext as _


class OpenDLPError(Exception):
    """Base exception for all our custom errors."""


class ServiceLayerError(OpenDLPError):
    """Base exception for all service layer errors."""


class PasswordTooWeak(ServiceLayerError):
    """Exception if the password is too weak."""


class UserAlreadyExists(ServiceLayerError):
    """Raised when attempting to create a user that already exists."""

    def __init__(self, email: str = "") -> None:
        message = _("User with email '%(email)s' already exists", email=email) if email else _("User already exists")
        super().__init__(message)
        self.email = email


class InvalidCredentials(ServiceLayerError):
    """Raised when authentication fails due to invalid credentials."""

    def __init__(self, message: str = "") -> None:
        if not message:
            message = _("Invalid email or password")
        super().__init__(message)


class InvalidInvite(ServiceLayerError):
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


class InsufficientPermissions(ServiceLayerError):
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


class SelectionRunRecordNotFoundError(NotFoundError):
    """A selection run record could not be found in the database"""
