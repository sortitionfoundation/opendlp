"""ABOUTME: CSV data source configuration for assemblies
ABOUTME: Contains AssemblyCSV for configuring CSV-based respondent imports"""

import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime


@dataclass
class AssemblyCSV:
    """CSV data source configuration for an assembly"""

    assembly_id: uuid.UUID
    assembly_csv_id: uuid.UUID | None = None

    # Source details
    last_import_filename: str = ""  # Track what was last imported
    last_import_timestamp: datetime | None = None

    # The name of the column in uploaded CSV files that contains the unique identifier.
    # During import, the value is extracted and stored as respondent.external_id.
    csv_id_column: str = "external_id"

    # Whether settings have been explicitly reviewed and saved by a user.
    # Selection cannot be run until this is True.
    settings_confirmed: bool = False

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        if self.updated_at is None:
            self.updated_at = datetime.now(UTC)

    def create_detached_copy(self) -> "AssemblyCSV":
        """Create a detached copy for use outside SQLAlchemy sessions"""
        return AssemblyCSV(**asdict(self))
