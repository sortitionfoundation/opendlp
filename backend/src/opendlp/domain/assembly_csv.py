"""ABOUTME: CSV data source configuration for assemblies
ABOUTME: Contains AssemblyCSV for configuring CSV-based respondent imports"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sortition_algorithms import settings


@dataclass
class AssemblyCSV:
    """CSV data source configuration for an assembly"""

    assembly_id: uuid.UUID
    assembly_csv_id: uuid.UUID | None = None

    # Source details
    last_import_filename: str = ""  # Track what was last imported
    last_import_timestamp: datetime | None = None

    # Selection settings (same as AssemblyGSheet)
    id_column: str = "external_id"  # Default for CSV
    check_same_address: bool = True
    check_same_address_cols: list[str] = field(default_factory=list)
    columns_to_keep: list[str] = field(default_factory=list)
    selection_algorithm: str = "maximin"

    # Timestamps
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now(UTC)
        if self.updated_at is None:
            self.updated_at = datetime.now(UTC)

    def to_settings(self) -> settings.Settings:
        """Convert to sortition-algorithms Settings"""
        return settings.Settings(
            id_column=self.id_column,
            columns_to_keep=self.columns_to_keep,
            check_same_address=self.check_same_address,
            check_same_address_columns=self.check_same_address_cols,
            selection_algorithm=self.selection_algorithm,
        )

    def create_detached_copy(self) -> "AssemblyCSV":
        """Create a detached copy for use outside SQLAlchemy sessions"""
        return AssemblyCSV(**asdict(self))
