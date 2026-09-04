"""ABOUTME: Value objects and enums for OpenDLP domain models
ABOUTME: Defines shared enums and validation functions used across domain objects"""

from dataclasses import dataclass
from enum import Enum

from opendlp.translations import lazy_gettext as _l


class GlobalRole(Enum):
    ADMIN = "admin"
    ORGANISER = "organiser"
    USER = "user"


# for forms etc
global_role_options = {
    GlobalRole.USER.name: _l("User - Access to the assemblies they are added to"),
    GlobalRole.ORGANISER.name: _l("Organiser - Can create assemblies, and manage the ones they belong to"),
    GlobalRole.ADMIN.name: _l("Admin - Full system access including user management"),
}

# Short labels, for a tag or a badge. Kept next to the role definitions so a
# renamed role cannot leave a stale label behind somewhere.
global_role_labels = {
    GlobalRole.USER: _l("User"),
    GlobalRole.ORGANISER: _l("Organiser"),
    GlobalRole.ADMIN: _l("Admin"),
}

# What the role means, written for the person who holds it. Shown on the
# profile page under the label.
global_role_descriptions = {
    GlobalRole.USER: _l("You can see the assemblies you have been added to. An organiser can add you to one."),
    GlobalRole.ORGANISER: _l(
        "You can create assemblies. You can see the assemblies you have been added to, and the ones you create."
    ),
    GlobalRole.ADMIN: _l("You can see and manage every assembly, and manage users and invites."),
}


def get_role_level(role: GlobalRole) -> int:
    """Get numeric level for role comparison."""
    role_levels = {
        GlobalRole.USER: 1,
        GlobalRole.ORGANISER: 2,
        GlobalRole.ADMIN: 3,
    }
    return role_levels.get(role, 0)


class AssemblyRole(Enum):
    ASSEMBLY_MANAGER = "assembly-manager"
    CONFIRMATION_CALLER = "confirmation-caller"
    READ_ONLY = "read-only"


# for forms etc
assembly_role_options = {
    AssemblyRole.ASSEMBLY_MANAGER.name: _l("Assembly Manager - Can manage the assembly and add other users"),
    AssemblyRole.CONFIRMATION_CALLER.name: _l("Confirmation Caller - Can call confirmations for selected participants"),
    AssemblyRole.READ_ONLY.name: _l("Read Only - Can view the assembly but cannot make changes"),
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


class GSheetExportKind(Enum):
    """What an assembly's saved Google Sheet export target is for.

    Each kind gets its own row, so it can have its own spreadsheet as well as its
    own worksheet - respondent data is personal and its sheet needs tight sharing,
    while the dashboard's is aggregate counts an organiser may want to publish.
    Nothing stops an organiser pointing two kinds at the same spreadsheet; what
    keeps the personal data safe is the sharing on the sheet holding it, not this.
    """

    RESPONDENTS = "RESPONDENTS"
    DASHBOARD = "DASHBOARD"


class RespondentStatus(Enum):
    """Status of a respondent in the selection process.

    TEST_SUBMISSION is for respondents created via a TEST registration page.
    They are quarantined from the selection pool but can be promoted to POOL.
    """

    TEST_SUBMISSION = "TEST_SUBMISSION"
    POOL = "POOL"
    SELECTED = "SELECTED"
    CONFIRMED = "CONFIRMED"
    WITHDRAWN = "WITHDRAWN"
    DELETED = "DELETED"

    @classmethod
    def from_str(cls, value: str) -> "RespondentStatus | None":
        """Parse a string to RespondentStatus, returning None for invalid values."""
        if not value:
            return None
        try:
            return cls(value)
        except ValueError:
            return None


# The statuses that make someone one of the assembly's respondents: in the pool,
# picked from it, or picked and confirmed. A withdrawn person is no longer part
# of the pool a target is measured against, a test submission was never in it,
# and a deleted one has had its details blanked. Written as the statuses that do
# count rather than the ones that do not, so a status added later has to be
# considered rather than quietly counted.
COUNTED_RESPONDENT_STATUSES: list["RespondentStatus"] = [
    RespondentStatus.POOL,
    RespondentStatus.SELECTED,
    RespondentStatus.CONFIRMED,
]

# Everyone who ever became one of the assembly's respondents, withdrawals
# included. Wider than COUNTED_RESPONDENT_STATUSES on purpose: a withdrawal is no
# longer part of the pool a target is measured against, but it is still a
# registration that happened, so a headline "how many people registered" figure
# has to count it. Test submissions were never real and deleted details are gone.
HEADLINE_RESPONDENT_STATUSES: list["RespondentStatus"] = [
    RespondentStatus.POOL,
    RespondentStatus.SELECTED,
    RespondentStatus.CONFIRMED,
    RespondentStatus.WITHDRAWN,
]

# Confirmed is selected and then confirmed, so both count as selected.
SELECTED_RESPONDENT_STATUSES: list["RespondentStatus"] = [
    RespondentStatus.SELECTED,
    RespondentStatus.CONFIRMED,
]


# Manual transitions allowed from the backoffice view-respondent page.
# Any move between the four active statuses is permitted; moves to or from
# DELETED are excluded (DELETED is reached only via the GDPR delete form).
# TEST_SUBMISSION can only be promoted to POOL (one-way).
ALLOWED_SELECTION_STATUS_TRANSITIONS: dict["RespondentStatus", list["RespondentStatus"]] = {
    RespondentStatus.TEST_SUBMISSION: [RespondentStatus.POOL],
    RespondentStatus.POOL: [RespondentStatus.SELECTED, RespondentStatus.CONFIRMED, RespondentStatus.WITHDRAWN],
    RespondentStatus.SELECTED: [RespondentStatus.POOL, RespondentStatus.CONFIRMED, RespondentStatus.WITHDRAWN],
    RespondentStatus.CONFIRMED: [RespondentStatus.POOL, RespondentStatus.SELECTED, RespondentStatus.WITHDRAWN],
    RespondentStatus.WITHDRAWN: [RespondentStatus.POOL, RespondentStatus.SELECTED, RespondentStatus.CONFIRMED],
    RespondentStatus.DELETED: [],
}


class RespondentAction(Enum):
    """Type of action a RespondentComment records.

    NONE is a plain comment with no system action attached.
    CREATE records the initial creation of the respondent.
    EDIT records a change to the respondent's attributes or eligibility flags.
    STATUS_CHANGE records a manual selection-status transition.
    SELECT records inclusion in a selection run.
    DELETE records a GDPR personal-data deletion.
    """

    NONE = "NONE"
    CREATE = "CREATE"
    EDIT = "EDIT"
    STATUS_CHANGE = "STATUS_CHANGE"
    SELECT = "SELECT"
    DELETE = "DELETE"


class RespondentSourceType(Enum):
    """Source of respondent data"""

    REGISTRATION_FORM = "REGISTRATION_FORM"
    CSV_IMPORT = "CSV_IMPORT"
    NATIONBUILDER_SYNC = "NATIONBUILDER_SYNC"
    MANUAL_ENTRY = "MANUAL_ENTRY"


@dataclass(frozen=True)
class ProgressInfo:
    """Generic progress information for display in UI components.

    Consumed by the progress_indicator Jinja macro in modal.html.
    When total is set, the macro renders a determinate progress bar.
    When total is None, it renders a spinner with the label.
    """

    label: str
    current: int | None = None
    total: int | None = None

    @property
    def percent(self) -> float | None:
        """Percentage complete, or None if total is not set or zero."""
        if self.total and self.current is not None:
            return self.current / self.total * 100
        return None
