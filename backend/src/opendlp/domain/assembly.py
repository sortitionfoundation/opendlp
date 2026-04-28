"""ABOUTME: Assembly domain model for Citizens' Assembly management
ABOUTME: Contains Assembly class representing policy questions and selection configuration"""

import uuid
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, date, datetime
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar

from sortition_algorithms import adapters
from sortition_algorithms.utils import RunReport

from opendlp import config
from opendlp.adapters.sortition_algorithms import CSVGSheetDataSource
from opendlp.domain.respondents import normalise_field_name
from opendlp.domain.validators import GoogleSpreadsheetURLValidator
from opendlp.domain.value_objects import AssemblyStatus, ProgressInfo, SelectionRunStatus, SelectionTaskType
from opendlp.translations import lazy_gettext as _l

if TYPE_CHECKING:
    from opendlp.domain.assembly_csv import AssemblyCSV
    from opendlp.domain.respondents import Respondent
    from opendlp.domain.selection_settings import SelectionSettings
    from opendlp.domain.targets import TargetCategory


class Assembly:
    """Assembly domain model for Citizens' Assembly configuration."""

    def __init__(
        self,
        title: str,
        question: str = "",
        first_assembly_date: date | None = None,
        number_to_select: int = 0,
        assembly_id: uuid.UUID | None = None,
        status: AssemblyStatus = AssemblyStatus.ACTIVE,
        gsheet: "AssemblyGSheet | None" = None,
        csv: "AssemblyCSV | None" = None,
        selection_settings: "SelectionSettings | None" = None,
        target_categories: list["TargetCategory"] | None = None,
        respondents: list["Respondent"] | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        if not title or not title.strip():
            raise ValueError("Assembly title is required")

        self.id = assembly_id or uuid.uuid4()
        self.title = title.strip()
        self.question = question.strip()

        self.first_assembly_date = first_assembly_date
        self.number_to_select = number_to_select
        self.status = status
        self.gsheet = gsheet
        self.csv = csv
        self.selection_settings = selection_settings
        self.target_categories = target_categories or []
        self.respondents = respondents or []
        self.created_at = created_at or datetime.now(UTC)
        self.updated_at = updated_at or datetime.now(UTC)

    def archive(self) -> None:
        """Archive this assembly."""
        self.status = AssemblyStatus.ARCHIVED
        self.updated_at = datetime.now(UTC)

    def reactivate(self) -> None:
        """Reactivate this assembly."""
        self.status = AssemblyStatus.ACTIVE
        self.updated_at = datetime.now(UTC)

    def update_details(
        self,
        title: str | None = None,
        question: str | None = None,
        first_assembly_date: date | None = None,
        number_to_select: int | None = None,
    ) -> None:
        """Update assembly details."""
        if title is not None:
            if not title.strip():
                raise ValueError("Assembly title cannot be empty")
            self.title = title.strip()

        if question is not None:
            self.question = question.strip()

        if first_assembly_date is not None:
            self.first_assembly_date = first_assembly_date

        if number_to_select is not None:
            if number_to_select < 0:
                raise ValueError("Number to select cannot be negative")
            self.number_to_select = number_to_select

        self.updated_at = datetime.now(UTC)

    def is_active(self) -> bool:
        """Check if assembly is active."""
        return self.status == AssemblyStatus.ACTIVE

    @cached_property
    def name_fields(self) -> list[str]:
        """Attribute keys on respondents to use for building a display name.

        Inspects the first respondent's attribute keys, normalises them
        (lowercase, alphanumeric only), and returns the original keys that
        match one of the supported name schemas, in precedence order:
        firstname + lastname, firstname + surname, fullname, name.
        """
        if not self.respondents:
            return []
        normalised_to_original: dict[str, str] = {}
        for key in self.respondents[0].attributes:
            normalised = normalise_field_name(key)
            if normalised and normalised not in normalised_to_original:
                normalised_to_original[normalised] = key
        for candidate in (("firstname", "lastname"), ("firstname", "surname"), ("fullname",), ("name",)):
            if all(part in normalised_to_original for part in candidate):
                return [normalised_to_original[part] for part in candidate]
        return []

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Assembly):  # pragma: no cover
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def create_detached_copy(self) -> "Assembly":
        """Create a detached copy of this assembly for use outside SQLAlchemy sessions"""
        detached_assembly = Assembly(
            title=self.title,
            question=self.question,
            first_assembly_date=self.first_assembly_date,
            number_to_select=self.number_to_select,
            assembly_id=self.id,
            status=self.status,
            gsheet=self.gsheet.create_detached_copy() if self.gsheet else None,
            csv=self.csv.create_detached_copy() if self.csv else None,
            selection_settings=self.selection_settings.create_detached_copy() if self.selection_settings else None,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
        detached_assembly.target_categories = [c.create_detached_copy() for c in self.target_categories]
        detached_assembly.respondents = [r.create_detached_copy() for r in self.respondents]
        return detached_assembly


@dataclass
class AssemblyGSheet:
    """Google Spreadsheet Details for an Assembly"""

    assembly_id: uuid.UUID  # foreign key to Assembly
    url: str
    assembly_gsheet_id: uuid.UUID | None = None
    select_registrants_tab: str = "Respondents"
    select_targets_tab: str = "Categories"
    replace_registrants_tab: str = "Remaining"
    replace_targets_tab: str = "Replacement Categories"
    already_selected_tab: str = "Selected"
    generate_remaining_tab: bool = True

    def __post_init__(self) -> None:
        self.url = self._validate_url(self.url.strip())

    def _validate_url(self, url: str) -> str:
        if url:
            validator = GoogleSpreadsheetURLValidator()
            validator.validate_str(url.strip())
        return url

    @classmethod
    def _updatable_fields(cls) -> list[str]:
        non_updatable = ("assembly_id", "assembly_gsheet_id")
        return [f.name for f in fields(AssemblyGSheet) if f not in non_updatable]

    def update_values(self, url: str = "", **kwargs: str | bool | list[str]) -> None:
        """Update values of the object."""
        if url:
            self.url = self._validate_url(url)
        for field_name, value in kwargs.items():
            if field_name not in self._updatable_fields():
                raise ValueError(f"Cannot update field {field_name} in AssemblyGSheet")
            setattr(self, field_name, value)

    def to_data_source(
        self, *, for_replacements: bool = False, id_column: str = ""
    ) -> adapters.GSheetDataSource | CSVGSheetDataSource:
        # import here to avoid circular import
        from opendlp.bootstrap import update_data_source_from_assembly_gsheet  # noqa: PLC0415

        if for_replacements:
            # already selected only makes sense for replacements
            # and we only need id_column set when using already_selected_tab
            gsheet_data_source = adapters.GSheetDataSource(
                feature_tab_name=self.replace_targets_tab,
                people_tab_name=self.replace_registrants_tab,
                already_selected_tab_name=self.already_selected_tab,
                id_column=id_column,
                auth_json_path=config.get_google_auth_json_path(),
            )
        else:
            gsheet_data_source = adapters.GSheetDataSource(
                feature_tab_name=self.select_targets_tab,
                people_tab_name=self.select_registrants_tab,
                auth_json_path=config.get_google_auth_json_path(),
            )
        gsheet_data_source.set_g_sheet_name(self.url)

        return update_data_source_from_assembly_gsheet(gsheet_data_source)

    def registrants_tab(self, for_replacements: bool = False) -> str:
        return self.replace_registrants_tab if for_replacements else self.select_registrants_tab

    def targets_tab(self, for_replacements: bool = False) -> str:
        return self.replace_targets_tab if for_replacements else self.select_targets_tab

    def create_detached_copy(self) -> "AssemblyGSheet":
        """Create a detached copy of this assembly gsheet for use outside SQLAlchemy sessions"""
        return AssemblyGSheet(**asdict(self))

    def dict_for_json(self) -> dict[str, Any]:
        """Return a dict that can be serialised to JSON - so convert UUID to str"""
        new_dict: dict[str, Any] = {}
        for key, value in asdict(self).items():
            new_dict[key] = str(value) if isinstance(value, uuid.UUID) else value
        return new_dict


@dataclass
class SelectionRunRecord:
    """Record of a selection task execution for audit and progress tracking"""

    assembly_id: uuid.UUID  # foreign key to Assembly
    task_id: uuid.UUID  # unique identifier for this task run
    status: SelectionRunStatus
    task_type: SelectionTaskType
    celery_task_id: str = ""  # the ID of the task in celery
    log_messages: list[str] = field(default_factory=list)  # stored as JSON in DB
    settings_used: dict[str, Any] = field(default_factory=dict)  # stored as JSON in DB
    error_message: str = ""
    created_at: datetime | None = None
    completed_at: datetime | None = None
    user_id: uuid.UUID | None = None  # foreign key to User - who started the run
    comment: str = ""  # comment when starting the selection (max 512 chars)
    selected_ids: list[list[str]] | None = None  # JSON: list of panels, each panel is list of IDs
    run_report: RunReport = field(default_factory=RunReport)  # serialized RunReport for persistence
    remaining_ids: list[str] | None = None  # JSON: external IDs of remaining pool at selection time
    progress: dict[str, Any] | None = None  # JSON: live progress payload written by DatabaseProgressReporter
    targets_used: list[dict[str, Any]] = field(default_factory=list)  # JSON: snapshot of target categories

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(UTC)

    def create_detached_copy(self) -> "SelectionRunRecord":
        """Create a detached copy of this assembly gsheet for use outside SQLAlchemy sessions"""
        detached_run_record = SelectionRunRecord(**asdict(self))
        return detached_run_record

    @property
    def is_pending(self) -> bool:
        return self.status == SelectionRunStatus.PENDING

    @property
    def is_running(self) -> bool:
        return self.status == SelectionRunStatus.RUNNING

    @property
    def is_completed(self) -> bool:
        return self.status == SelectionRunStatus.COMPLETED

    @property
    def is_failed(self) -> bool:
        return self.status == SelectionRunStatus.FAILED

    @property
    def is_cancelled(self) -> bool:
        return self.status == SelectionRunStatus.CANCELLED

    @property
    def has_finished(self) -> bool:
        return self.status in (SelectionRunStatus.COMPLETED, SelectionRunStatus.FAILED, SelectionRunStatus.CANCELLED)

    @property
    def task_type_verbose(self) -> str:
        return self.task_type.value.replace("_", " ").replace("gsheet", "Google Spreadsheet").capitalize()

    # Phase → user-facing label mapping for sortition-algorithms progress.
    # Labels use gettext format strings with %(current)s and %(total)s placeholders.
    _PHASE_LABELS: ClassVar[dict[str, str]] = {
        "read_gsheet": _l("Reading spreadsheet…"),
        "write_gsheet": _l("Writing results back to spreadsheet…"),
        "legacy_attempt": _l("Running selection attempt %(current)s of %(total)s"),
        "multiplicative_weights": _l("Finding diverse committees (%(current)s of %(total)s rounds)"),
        "maximin_optimization": _l("Optimising for maximin fairness (iteration %(current)s)"),
        "nash_optimization": _l("Optimising for Nash fairness (iteration %(current)s)"),
        "leximin_outer": _l("Optimising for leximin fairness (%(current)s of %(total)s fixed)"),
        "diversimax": _l("Running diversimax optimisation"),
    }

    _DEFAULT_PROGRESS_LABEL: ClassVar[str] = _l("Processing…")

    @property
    def progress_info(self) -> ProgressInfo:
        """Convert the raw progress dict into a ProgressInfo for UI display."""
        if self.progress is None:
            return ProgressInfo(label=str(self._DEFAULT_PROGRESS_LABEL))

        phase = self.progress.get("phase", "")
        current = self.progress.get("current", 0)
        total = self.progress.get("total")

        raw_label = self._PHASE_LABELS.get(phase, phase or str(self._DEFAULT_PROGRESS_LABEL))
        label = str(raw_label) % {"current": current, "total": total}

        return ProgressInfo(label=label, current=current, total=total)

    def add_report(self, report: RunReport) -> None:
        """
        Add the new report to our existing report.

        We always have an empty report to add new reports to.
        """
        self.run_report.add_report(report)
