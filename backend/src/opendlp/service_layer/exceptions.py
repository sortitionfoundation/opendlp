"""ABOUTME: Custom exceptions for service layer operations
ABOUTME: Defines business logic exceptions with proper error messages and codes"""

from opendlp.translations import _l


class ServiceLayerError(Exception):
    """Base exception for all service layer errors."""

    pass


class PasswordTooWeak(ServiceLayerError):
    """Exception if the password is too weak."""


class UserAlreadyExists(ServiceLayerError):
    """Raised when attempting to create a user that already exists."""

    def __init__(self, username: str = "", email: str = "") -> None:
        if username:
            message = _l("User with username '%(username)s' already exists", username=username)
        elif email:
            message = _l("User with email '%(email)s' already exists", email=email)
        else:
            message = _l("User already exists")
        super().__init__(message)
        self.username = username
        self.email = email


class InvalidCredentials(ServiceLayerError):
    """Raised when authentication fails due to invalid credentials."""

    def __init__(self, message: str = "") -> None:
        if not message:
            message = _l("Invalid username or password")
        super().__init__(message)


class InvalidInvite(ServiceLayerError):
    """Raised when an invite code is invalid, expired, or already used."""

    def __init__(self, code: str = "", reason: str = "") -> None:
        if code and reason:
            message = _l("Invalid invite code '%(code)s': %(reason)s", code=code, reason=reason)
        elif code:
            message = _l("Invalid invite code '%(code)s'", code=code)
        elif reason:
            message = _l("Invalid invite code: %(reason)s", reason=reason)
        else:
            message = _l("Invalid invite code")
        super().__init__(message)
        self.code = code
        self.reason = reason


class InsufficientPermissions(ServiceLayerError):
    """Raised when a user lacks permissions for an operation."""

    def __init__(self, action: str = "", required_role: str = "") -> None:
        if action and required_role:
            message = _l(
                "Insufficient permissions for action: %(action)s (requires role: %(required_role)s)",
                action=action,
                required_role=required_role,
            )
        elif action:
            message = _l("Insufficient permissions for action: %(action)s", action=action)
        elif required_role:
            message = _l("Insufficient permissions (requires role: %(required_role)s)", required_role=required_role)
        else:
            message = _l("Insufficient permissions")
        super().__init__(message)
        self.action = action
        self.required_role = required_role
