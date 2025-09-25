"""ABOUTME: Value objects and enums for OpenDLP domain models
ABOUTME: Defines shared enums and validation functions used across domain objects"""

from enum import Enum

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator


class GlobalRole(Enum):
    ADMIN = "admin"
    GLOBAL_ORGANISER = "global-organiser"
    USER = "user"


def get_role_level(role: GlobalRole) -> int:
    """Get numeric level for role comparison."""
    role_levels = {
        GlobalRole.USER: 1,
        GlobalRole.GLOBAL_ORGANISER: 2,
        GlobalRole.ADMIN: 3,
    }
    return role_levels.get(role, 0)


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
