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


# for forms etc
assembly_role_options = {
    AssemblyRole.ASSEMBLY_MANAGER.name: _l("Assembly Manager - Can manage the assembly and add other users"),
    AssemblyRole.CONFIRMATION_CALLER.name: _l("Confirmation Caller - Can call confirmations for selected participants"),
}


class AssemblyStatus(Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SelectionRunStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ManageOldTabsState(Enum):
    FRESH = "fresh"
    ERROR = "error"
    LIST_RUNNING = "list_running"
    LIST_COMPLETED = "list_completed"
    DELETE_RUNNING = "delete_running"
    DELETE_COMPLETED = "delete_completed"


class ManageOldTabsStatus:
    def __init__(self, state: ManageOldTabsState = ManageOldTabsState.FRESH) -> None:
        self.state = state

    @property
    def is_fresh(self) -> bool:
        return self.state == ManageOldTabsState.FRESH

    @property
    def is_running(self) -> bool:
        return self.state in (ManageOldTabsState.LIST_RUNNING, ManageOldTabsState.DELETE_RUNNING)

    @property
    def is_completed(self) -> bool:
        return self.state in (ManageOldTabsState.LIST_COMPLETED, ManageOldTabsState.DELETE_COMPLETED)

    @property
    def is_error(self) -> bool:
        return self.state == ManageOldTabsState.ERROR

    @property
    def is_list_completed(self) -> bool:
        return self.state == ManageOldTabsState.LIST_COMPLETED


class SelectionTaskType(Enum):
    LOAD_GSHEET = "load_gsheet"
    SELECT_GSHEET = "select_gsheet"
    TEST_SELECT_GSHEET = "test_select_gsheet"
    LOAD_REPLACEMENT_GSHEET = "load_replacement_gsheet"
    SELECT_REPLACEMENT_GSHEET = "select_replacement_gsheet"
    LIST_OLD_TABS = "list_old_tabs"
    DELETE_OLD_TABS = "delete_old_tabs"
    SELECT_FROM_DB = "select_from_db"
    TEST_SELECT_FROM_DB = "test_select_from_db"


class RespondentStatus(Enum):
    """Status of a respondent in the selection process"""

    POOL = "POOL"
    SELECTED = "SELECTED"
    CONFIRMED = "CONFIRMED"
    WITHDRAWN = "WITHDRAWN"
    PARTICIPATED = "PARTICIPATED"
    EXCLUDED = "EXCLUDED"


class RespondentSourceType(Enum):
    """Source of respondent data"""

    REGISTRATION_FORM = "REGISTRATION_FORM"
    CSV_IMPORT = "CSV_IMPORT"
    NATIONBUILDER_SYNC = "NATIONBUILDER_SYNC"
    MANUAL_ENTRY = "MANUAL_ENTRY"


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
