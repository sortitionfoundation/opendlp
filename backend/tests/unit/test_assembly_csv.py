"""ABOUTME: Unit tests for AssemblyCSV domain model
ABOUTME: Tests creation, validation, to_settings conversion, and detached copy functionality"""

import uuid
from datetime import UTC, datetime

from sortition_algorithms.settings import Settings

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
        assert csv_config.id_column == "external_id"
        assert csv_config.check_same_address is True
        assert csv_config.check_same_address_cols == []
        assert csv_config.columns_to_keep == []
        assert csv_config.selection_algorithm == "maximin"
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
            id_column="custom_id",
            check_same_address=False,
            check_same_address_cols=["address", "postcode"],
            columns_to_keep=["name", "email", "age"],
            selection_algorithm="random",
            created_at=now,
            updated_at=now,
        )

        assert csv_config.assembly_id == assembly_id
        assert csv_config.assembly_csv_id == csv_id
        assert csv_config.last_import_filename == "data.csv"
        assert csv_config.last_import_timestamp == now
        assert csv_config.id_column == "custom_id"
        assert csv_config.check_same_address is False
        assert csv_config.check_same_address_cols == ["address", "postcode"]
        assert csv_config.columns_to_keep == ["name", "email", "age"]
        assert csv_config.selection_algorithm == "random"
        assert csv_config.created_at == now
        assert csv_config.updated_at == now

    def test_to_settings_conversion(self):
        """Test converting AssemblyCSV to sortition-algorithms Settings"""
        assembly_id = uuid.uuid4()
        csv_config = AssemblyCSV(
            assembly_id=assembly_id,
            id_column="participant_id",
            check_same_address=True,
            check_same_address_cols=["street", "zip"],
            columns_to_keep=["first_name", "last_name", "email"],
            selection_algorithm="nash",
        )

        settings = csv_config.to_settings()

        assert isinstance(settings, Settings)
        assert settings.id_column == "participant_id"
        assert settings.check_same_address is True
        assert settings.check_same_address_columns == ["street", "zip"]
        assert settings.columns_to_keep == ["first_name", "last_name", "email"]
        assert settings.selection_algorithm == "nash"

    def test_to_settings_with_defaults(self):
        """Test to_settings with default values (check_same_address disabled when no columns)"""
        assembly_id = uuid.uuid4()
        # Need to disable check_same_address when no columns are provided
        csv_config = AssemblyCSV(assembly_id=assembly_id, check_same_address=False)

        settings = csv_config.to_settings()

        assert isinstance(settings, Settings)
        assert settings.id_column == "external_id"
        assert settings.check_same_address is False
        assert settings.check_same_address_columns == []
        assert settings.columns_to_keep == []
        assert settings.selection_algorithm == "maximin"

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
            id_column="test_id",
            check_same_address=False,
            check_same_address_cols=["col1", "col2"],
            columns_to_keep=["col3", "col4"],
            selection_algorithm="stratified",
            created_at=now,
            updated_at=now,
        )

        copy = original.create_detached_copy()

        # Verify all fields are copied
        assert copy.assembly_id == original.assembly_id
        assert copy.assembly_csv_id == original.assembly_csv_id
        assert copy.last_import_filename == original.last_import_filename
        assert copy.last_import_timestamp == original.last_import_timestamp
        assert copy.id_column == original.id_column
        assert copy.check_same_address == original.check_same_address
        assert copy.check_same_address_cols == original.check_same_address_cols
        assert copy.columns_to_keep == original.columns_to_keep
        assert copy.selection_algorithm == original.selection_algorithm
        assert copy.created_at == original.created_at
        assert copy.updated_at == original.updated_at

        # Verify it's a different object
        assert copy is not original

        # Verify lists are copies, not references
        assert copy.check_same_address_cols is not original.check_same_address_cols
        assert copy.columns_to_keep is not original.columns_to_keep

    def test_timestamps_auto_set(self):
        """Test that timestamps are automatically set on creation"""
        before = datetime.now(UTC)
        csv_config = AssemblyCSV(assembly_id=uuid.uuid4())
        after = datetime.now(UTC)

        assert csv_config.created_at is not None
        assert csv_config.updated_at is not None
        assert before <= csv_config.created_at <= after
        assert before <= csv_config.updated_at <= after
