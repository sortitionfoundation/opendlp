"""ABOUTME: Google Sheet configuration for an assembly's exports
ABOUTME: One saved spreadsheet and worksheet per export kind, keyed by GSheetExportKind"""

import uuid
from dataclasses import asdict, dataclass, fields
from datetime import UTC, datetime

from opendlp.domain.validators import GoogleSpreadsheetURLValidator
from opendlp.domain.value_objects import GSheetExportKind
from opendlp.translations import lazy_gettext as _l

# What an export writes to when the organiser has not named a worksheet. The
# organiser reads these as a tab in their own spreadsheet, so they are translated
# - lazily, because this is module level and the language is only known per
# request.
DEFAULT_WORKSHEET_NAMES = {
    GSheetExportKind.RESPONDENTS: _l("Respondents"),
    GSheetExportKind.DASHBOARD: _l("Results"),
}


def default_worksheet_name(export_kind: GSheetExportKind) -> str:
    """The worksheet an export writes to by default, in the caller's language.

    Resolved here rather than at import, so call it where the name is needed - a
    module-level constant or a default argument would freeze it in whatever
    language happened to be active when the module was first imported. The result
    is a plain str because it goes on to be stored in a String column.
    """
    return str(DEFAULT_WORKSHEET_NAMES[export_kind])


@dataclass
class AssemblyExportGSheet:
    """Google Sheet target for one kind of export from an assembly.

    Separate from AssemblyGSheet (which drives selection): here the sheet is
    only a destination for exported data. The organiser sets the URL and
    worksheet once; later exports of that kind reuse and can edit them.

    An assembly has at most one row per ``export_kind``, and each row carries its
    own URL, so an organiser *can* send each kind to a different spreadsheet - the
    respondent export carries personal data and the dashboard export does not, so
    they may need to be shared with different people. Nothing forces that: two
    kinds may point at one spreadsheet if the organiser wants them to.
    """

    assembly_id: uuid.UUID
    # Required, with no default: defaulting to one kind would let a new export kind
    # silently write over the respondent export's row by forgetting to pass it.
    export_kind: GSheetExportKind
    assembly_export_gsheet_id: uuid.UUID | None = None
    url: str = ""
    worksheet_name: str = ""
    # Captured from the sheet on the last export: the spreadsheet's own title and
    # the direct link to the exported worksheet, used to show a link on the
    # respondents page. Blank until the first successful export.
    spreadsheet_title: str = ""
    worksheet_url: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.url = self._validate_url(self.url.strip())
        if not self.worksheet_name:
            self.worksheet_name = default_worksheet_name(self.export_kind)
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
        non_updatable = ("assembly_id", "export_kind", "assembly_export_gsheet_id", "created_at")
        return [f.name for f in fields(cls) if f.name not in non_updatable]

    def update_values(self, url: str = "", **kwargs: str) -> None:
        """Update the export target's editable fields."""
        if url:
            self.url = self._validate_url(url.strip())
        for field_name, value in kwargs.items():
            if field_name not in self._updatable_fields():
                raise ValueError(f"Cannot update field {field_name} in AssemblyExportGSheet")
            setattr(self, field_name, value)
        self.updated_at = datetime.now(UTC)

    def create_detached_copy(self) -> "AssemblyExportGSheet":
        """Create a detached copy for use outside SQLAlchemy sessions."""
        return AssemblyExportGSheet(**asdict(self))
