"""ABOUTME: CSV data source configuration for assemblies
ABOUTME: Contains AssemblyCSV for configuring CSV-based respondent imports"""

import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime

from sortition_algorithms import settings

from opendlp import config


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
    # This field is NOT used as the id_column in sortition-algorithms Settings —
    # see to_settings() for why.
    id_column: str = "external_id"
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
        """Convert to sortition-algorithms Settings.

        Note: id_column is always "external_id" here, not self.id_column.
        self.id_column records the column name in the *uploaded CSV*, but during
        import that value is extracted and stored as respondent.external_id. The
        data adapter (OpenDLPDataAdapter) always outputs the column as "external_id",
        so Settings.id_column must match.
        """
        return settings.Settings(
            id_column="external_id",
            columns_to_keep=self.columns_to_keep,
            check_same_address=self.check_same_address,
            check_same_address_columns=self.check_same_address_cols,
            selection_algorithm=self.selection_algorithm,
            solver_backend=config.get_solver_backend(),
        )

    def create_detached_copy(self) -> "AssemblyCSV":
        """Create a detached copy for use outside SQLAlchemy sessions"""
        return AssemblyCSV(**asdict(self))
