"""ABOUTME: Unit tests for AssemblyCSV domain model
ABOUTME: Tests creation, validation, and detached copy functionality"""

import uuid
from datetime import UTC, datetime

from opendlp.domain.assembly_csv import AssemblyCSV


class TestAssemblyCSV:
    """Test AssemblyCSV domain model"""

    def test_create_with_defaults(self):
        """Test creating AssemblyCSV with default values"""
        assembly_id = uuid.uuid4()
        csv_config = AssemblyCSV(assembly_id=assembly_id)

        assert csv_config.assembly_id == assembly_id
        assert csv_config.assembly_csv_id is None
        assert csv_config.last_import_filename == ""
        assert csv_config.last_import_timestamp is None
        assert csv_config.csv_id_column == "external_id"
        assert csv_config.settings_confirmed is False
        assert csv_config.created_at is not None
        assert csv_config.updated_at is not None

    def test_create_with_custom_values(self):
        """Test creating AssemblyCSV with custom values"""
        assembly_id = uuid.uuid4()
        csv_id = uuid.uuid4()
        now = datetime.now(UTC)

        csv_config = AssemblyCSV(
            assembly_id=assembly_id,
            assembly_csv_id=csv_id,
            last_import_filename="data.csv",
            last_import_timestamp=now,
            csv_id_column="custom_id",
            created_at=now,
            updated_at=now,
        )

        assert csv_config.assembly_id == assembly_id
        assert csv_config.assembly_csv_id == csv_id
        assert csv_config.last_import_filename == "data.csv"
        assert csv_config.last_import_timestamp == now
        assert csv_config.csv_id_column == "custom_id"
        assert csv_config.created_at == now
        assert csv_config.updated_at == now

    def test_create_detached_copy(self):
        """Test creating a detached copy of AssemblyCSV"""
        assembly_id = uuid.uuid4()
        csv_id = uuid.uuid4()
        now = datetime.now(UTC)

        original = AssemblyCSV(
            assembly_id=assembly_id,
            assembly_csv_id=csv_id,
            last_import_filename="import.csv",
            last_import_timestamp=now,
            csv_id_column="test_id",
            created_at=now,
            updated_at=now,
        )

        copy = original.create_detached_copy()

        # Verify all fields are copied
        assert copy.assembly_id == original.assembly_id
        assert copy.assembly_csv_id == original.assembly_csv_id
        assert copy.last_import_filename == original.last_import_filename
        assert copy.last_import_timestamp == original.last_import_timestamp
        assert copy.csv_id_column == original.csv_id_column
        assert copy.created_at == original.created_at
        assert copy.updated_at == original.updated_at

        # Verify it's a different object
        assert copy is not original

    def test_timestamps_auto_set(self):
        """Test that timestamps are automatically set on creation"""
        before = datetime.now(UTC)
        csv_config = AssemblyCSV(assembly_id=uuid.uuid4())
        after = datetime.now(UTC)

        assert csv_config.created_at is not None
        assert csv_config.updated_at is not None
        assert before <= csv_config.created_at <= after
        assert before <= csv_config.updated_at <= after
