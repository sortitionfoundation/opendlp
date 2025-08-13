"""ABOUTME: Value objects and enums for OpenDLP domain models
ABOUTME: Defines shared enums and validation functions used across domain objects"""

from enum import Enum

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator


class GlobalRole(Enum):
    ADMIN = "admin"
    GLOBAL_ORGANISER = "global-organiser"
    USER = "user"


class AssemblyRole(Enum):
    ASSEMBLY_MANAGER = "assembly-manager"
    CONFIRMATION_CALLER = "confirmation-caller"


class AssemblyStatus(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


def validate_email(email: str) -> None:
    """Basic email validation."""
    # we use the well-tested and maintained Django EmailValidator
    # Note that passing in the message is important - if we don't do that then
    # the validator will try to use the default message, which will trigger the
    # auto localisation of the string which then blows up.
    # If this breaks, consider copying in the whole file.
    validator = EmailValidator(message="Invalid email address")
    try:
        validator(email)
    except ValidationError as error:
        raise ValueError("Invalid email address") from error


def validate_username(username: str) -> None:
    """Basic username validation."""
    if not username or len(username) < 3 or len(username) > 200:
        raise ValueError("Username must be between 3 and 200 characters long")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username must contain only letters, numbers, underscores, and hyphens")
