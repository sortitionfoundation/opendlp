"""ABOUTME: Google Sheet configuration for exporting respondents
ABOUTME: Stores the spreadsheet URL and worksheet used for respondent exports"""

import uuid
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime

from opendlp.domain.validators import GoogleSpreadsheetURLValidator


@dataclass
class AssemblyRespondentGSheet:
    """Google Sheet target for exporting an assembly's respondents.

    Separate from AssemblyGSheet (which drives selection): here the sheet is
    only a destination for exported respondent data. The organiser sets the
    URL and worksheet once; later exports reuse and can edit them.
    """

    assembly_id: uuid.UUID
    assembly_respondent_gsheet_id: uuid.UUID | None = None
    url: str = ""
    worksheet_name: str = "Respondents"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.url = self._validate_url(self.url.strip())
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        if self.updated_at is None:
            self.updated_at = datetime.now(UTC)

    def _validate_url(self, url: str) -> str:
        if url:
            GoogleSpreadsheetURLValidator().validate_str(url.strip())
        return url

    @classmethod
    def _updatable_fields(cls) -> list[str]:
        non_updatable = ("assembly_id", "assembly_respondent_gsheet_id", "created_at")
        return [f.name for f in fields(cls) if f.name not in non_updatable]

    def update_values(self, url: str = "", **kwargs: str) -> None:
        """Update the export target's editable fields."""
        if url:
            self.url = self._validate_url(url.strip())
        for field_name, value in kwargs.items():
            if field_name not in self._updatable_fields():
                raise ValueError(f"Cannot update field {field_name} in AssemblyRespondentGSheet")
            setattr(self, field_name, value)
        self.updated_at = datetime.now(UTC)

    def create_detached_copy(self) -> "AssemblyRespondentGSheet":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return AssemblyRespondentGSheet(**asdict(self))
