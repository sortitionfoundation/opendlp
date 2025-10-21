"""ABOUTME: Value objects and enums for OpenDLP domain models
ABOUTME: Defines shared enums and validation functions used across domain objects"""

from enum import Enum

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator

from opendlp.translations import lazy_gettext as _l


class GlobalRole(Enum):
    ADMIN = "admin"
    GLOBAL_ORGANISER = "global-organiser"
    USER = "user"


# for forms etc
global_role_options = {
    GlobalRole.USER.name: _l("User - Basic access to assigned assemblies"),
    GlobalRole.GLOBAL_ORGANISER.name: _l("Global Organiser - Can create and manage all assemblies"),
    GlobalRole.ADMIN.name: _l("Admin - Full system access including user management"),
}


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


class SelectionRunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SelectionTaskType(Enum):
    LOAD_GSHEET = "load_gsheet"
    SELECT_GSHEET = "select_gsheet"
    TEST_SELECT_GSHEET = "test_select_gsheet"
    LOAD_REPLACEMENT_GSHEET = "load_replacement_gsheet"
    SELECT_REPLACEMENT_GSHEET = "select_replacement_gsheet"


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
