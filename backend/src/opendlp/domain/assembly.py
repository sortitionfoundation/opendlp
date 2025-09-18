"""ABOUTME: Assembly domain model for Citizens' Assembly management
ABOUTME: Contains Assembly class representing policy questions and selection configuration"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime

from sortition_algorithms import adapters, settings

from opendlp import config
from opendlp.domain.validators import GoogleSpreadsheetURLValidator
from opendlp.domain.value_objects import AssemblyStatus


class Assembly:
    """Assembly domain model for Citizens' Assembly configuration."""

    def __init__(
        self,
        title: str,
        question: str = "",
        first_assembly_date: date | None = None,
        assembly_id: uuid.UUID | None = None,
        status: AssemblyStatus = AssemblyStatus.ACTIVE,
        gsheet: "AssemblyGSheet | None" = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
    ):
        if not title or not title.strip():
            raise ValueError("Assembly title is required")

        self.id = assembly_id or uuid.uuid4()
        self.title = title.strip()
        self.question = question.strip()

        self.first_assembly_date = first_assembly_date
        self.status = status
        self.gsheet = gsheet
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

        self.updated_at = datetime.now(UTC)

    def is_active(self) -> bool:
        """Check if assembly is active."""
        return self.status == AssemblyStatus.ACTIVE

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
            assembly_id=self.id,
            status=self.status,
            gsheet=self.gsheet,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
        return detached_assembly


DEFAULT_ID_COLUMN = {
    "uk": "nationbuilder_id",
    "eu": "unique_id",
    "aus": "nationbuilder_id",
}
DEFAULT_ADDRESS_COLS = {
    "uk": ["primary_address1", "zip_royal_mail"],
    "eu": ["address_line1", "postcode"],
    "aus": ["primary_address1", "primary_zip"],
}
DEFAULT_COLS_TO_KEEP = {
    "uk": [
        "first_name",
        "last_name",
        "mobile_number",
        "email",
        "primary_address1",
        "primary_address2",
        "primary_city",
        "zip_royal_mail",
        "tag_list",
        "age",
        "gender",
    ],
    "eu": [
        "first_name",
        "last_name",
        "email",
        "phone_country",
        "phone_number",
        "address_line1",
        "address_line2",
        "city",
        "postcode",
        "country",
        "LocationNearest",
        "gender",
        "age",
        "nationality",
        "keep_informed",
    ],
    "aus": [
        "first_name",
        "last_name",
        "mobile_number",
        "email",
        "primary_address1",
        "primary_address2",
        "primary_city",
        "primary_zip",
        "tag_list",
        "age",
        "gender",
    ],
}


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
    generate_remaining_tab: bool = True
    id_column: str = "nationbuilder_id"
    check_same_address: bool = True
    check_same_address_cols: list[str] = field(default_factory=list)
    columns_to_keep: list[str] = field(default_factory=list)
    selection_algorithm: str = "maximin"

    # other things to consider
    # - number to select - just get that from the sheets?

    def __post_init__(self) -> None:
        self.url = self._validate_url(self.url.strip())

    def _validate_url(self, url: str) -> str:
        if url:
            validator = GoogleSpreadsheetURLValidator()
            validator.validate_str(url.strip())
        return url

    @classmethod
    def for_team(cls, team: str, assembly_id: uuid.UUID, url: str) -> "AssemblyGSheet":
        return AssemblyGSheet(
            assembly_id=assembly_id,
            url=url,
            id_column=DEFAULT_ID_COLUMN[team],
            check_same_address_cols=DEFAULT_ADDRESS_COLS[team],
            columns_to_keep=DEFAULT_COLS_TO_KEEP[team],
        )

    def to_settings(self) -> settings.Settings:
        return settings.Settings(
            id_column=self.id_column,
            columns_to_keep=self.columns_to_keep,
            check_same_address=self.check_same_address,
            check_same_address_columns=self.check_same_address_cols,
            selection_algorithm=self.selection_algorithm,
        )

    def to_adapter(self) -> adapters.GSheetAdapter:
        return adapters.GSheetAdapter(
            auth_json_path=config.get_google_auth_json_path(),
            gen_rem_tab=self.generate_remaining_tab,
        )

    def registrants_tab(self, for_replacements: bool = False) -> str:
        return self.replace_registrants_tab if for_replacements else self.select_registrants_tab

    def targets_tab(self, for_replacements: bool = False) -> str:
        return self.replace_targets_tab if for_replacements else self.select_targets_tab

    def create_detached_copy(self) -> "AssemblyGSheet":
        """Create a detached copy of this assembly gsheet for use outside SQLAlchemy sessions"""
        detached_assembly_gsheet = AssemblyGSheet(**asdict(self))
        return detached_assembly_gsheet
