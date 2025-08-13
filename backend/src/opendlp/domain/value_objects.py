"""ABOUTME: Value objects and enums for OpenDLP domain models
ABOUTME: Defines shared enums and validation functions used across domain objects"""

from enum import Enum


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
    if not email or "@" not in email:
        raise ValueError("Invalid email address")


def validate_username(username: str) -> None:
    """Basic username validation."""
    if not username or len(username) < 3:
        raise ValueError("Username must be at least 3 characters long")
    if not username.replace("_", "").replace("-", "").isalnum():
        raise ValueError("Username must contain only letters, numbers, underscores, and hyphens")
