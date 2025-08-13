"""ABOUTME: Custom exceptions for service layer operations
ABOUTME: Defines business logic exceptions with proper error messages and codes"""


class ServiceLayerError(Exception):
    """Base exception for all service layer errors."""

    pass


class PasswordTooWeak(ServiceLayerError):
    """Exception if the password is too weak."""


class UserAlreadyExists(ServiceLayerError):
    """Raised when attempting to create a user that already exists."""

    def __init__(self, username: str = "", email: str = "") -> None:
        if username:
            message = f"User with username '{username}' already exists"
        elif email:
            message = f"User with email '{email}' already exists"
        else:
            message = "User already exists"
        super().__init__(message)
        self.username = username
        self.email = email


class InvalidCredentials(ServiceLayerError):
    """Raised when authentication fails due to invalid credentials."""

    def __init__(self, message: str = "Invalid username or password") -> None:
        super().__init__(message)


class InvalidInvite(ServiceLayerError):
    """Raised when an invite code is invalid, expired, or already used."""

    def __init__(self, code: str = "", reason: str = "Invalid invite code") -> None:
        message = "Invalid invite code"
        if code:
            message = f"Invalid invite code '{code}'"
        if reason != "Invalid invite code":
            message = f"{message}: {reason}"
        super().__init__(message)
        self.code = code
        self.reason = reason


class InsufficientPermissions(ServiceLayerError):
    """Raised when a user lacks permissions for an operation."""

    def __init__(self, action: str = "", required_role: str = "") -> None:
        message = "Insufficient permissions"
        if action:
            message = f"Insufficient permissions for action: {action}"
        if required_role:
            message = f"{message} (requires role: {required_role})"
        super().__init__(message)
        self.action = action
        self.required_role = required_role
