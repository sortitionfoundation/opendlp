"""ABOUTME: Integration tests for CSV import with AssemblyCSV configuration
ABOUTME: Tests CSV import service with configurable id_column and auto-detection from first CSV column"""

import pytest

from opendlp.adapters.database import start_mappers
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.assembly_service import create_assembly, get_or_create_csv_config, update_csv_config
from opendlp.service_layer.exceptions import InvalidSelection
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user


@pytest.fixture(autouse=True)
def setup_mappers():
    """Ensure database mappers are started before tests."""
    start_mappers()


class TestCSVImportWithConfig:
    """Integration tests for CSV import with configuration"""

    @pytest.fixture
    def admin_user(self, sqlite_session_factory):
        """Create an admin user for tests"""
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            user, _ = create_user(
                uow=uow,
                email="csvadmin@example.com",
                password="testpass123",  # pragma: allowlist secret
                first_name="CSV",
                last_name="Admin",
                global_role=GlobalRole.ADMIN,
            )
            return user

    @pytest.fixture
    def test_assembly(self, sqlite_session_factory, admin_user):
        """Create a test assembly"""
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            assembly = create_assembly(
                uow=uow,
                title="CSV Test Assembly",
                created_by_user_id=admin_user.id,
                question="Test question?",
                number_to_select=10,
            )
            return assembly

    def test_import_with_default_id_column(self, sqlite_session_factory, admin_user, test_assembly):
        """Test CSV import uses first column when no id_column specified"""
        csv_content = """external_id,name,email,age
user001,Alice Smith,alice@example.com,35
user002,Bob Jones,bob@example.com,42
user003,Charlie Brown,charlie@example.com,28"""

        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            respondents, errors, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                csv_content=csv_content,
                replace_existing=False,
            )

            assert len(respondents) == 3
            assert len(errors) == 0
            assert respondents[0].external_id == "user001"
            assert respondents[1].external_id == "user002"
            assert respondents[2].external_id == "user003"
            assert resolved_id_column == "external_id"

    def test_import_with_custom_id_column(self, sqlite_session_factory, admin_user, test_assembly):
        """Test CSV import with custom id_column configured"""
        # Configure custom id_column
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            update_csv_config(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                id_column="participant_id",
            )

        csv_content = """participant_id,name,email,age
P001,Alice Smith,alice@example.com,35
P002,Bob Jones,bob@example.com,42
P003,Charlie Brown,charlie@example.com,28"""

        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            respondents, errors, _ = import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                csv_content=csv_content,
                replace_existing=False,
            )

            assert len(respondents) == 3
            assert len(errors) == 0
            assert respondents[0].external_id == "P001"
            assert respondents[1].external_id == "P002"
            assert respondents[2].external_id == "P003"

    def test_import_with_override_id_column(self, sqlite_session_factory, admin_user, test_assembly):
        """Test CSV import with id_column override parameter"""
        csv_content = """custom_id,name,email,age
C001,Alice Smith,alice@example.com,35
C002,Bob Jones,bob@example.com,42"""

        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            respondents, errors, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                csv_content=csv_content,
                replace_existing=False,
                id_column="custom_id",  # Override
            )

            assert len(respondents) == 2
            assert len(errors) == 0
            assert respondents[0].external_id == "C001"
            assert respondents[1].external_id == "C002"
            assert resolved_id_column == "custom_id"

    def test_import_missing_explicit_id_column_raises_error(self, sqlite_session_factory, admin_user, test_assembly):
        """Test CSV import raises error when explicitly specified id_column is missing from CSV"""
        csv_content = """external_id,name,email
EXT001,Alice Smith,alice@example.com"""

        with (
            pytest.raises(InvalidSelection) as exc_info,
            SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow,
        ):
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                csv_content=csv_content,
                replace_existing=False,
                id_column="participant_id",
            )

        assert "CSV must have 'participant_id' column" in str(exc_info.value)

    def test_import_with_no_id_column_uses_first_csv_column(self, sqlite_session_factory, admin_user, test_assembly):
        """Test CSV import uses the first column as id_column when none is specified"""
        csv_content = """person_id,name
user001,Alice
user002,Bob"""

        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            respondents, errors, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                csv_content=csv_content,
                replace_existing=False,
            )

            assert len(respondents) == 2
            assert len(errors) == 0
            assert resolved_id_column == "person_id"
            assert respondents[0].external_id == "user001"
            assert respondents[1].external_id == "user002"

    def test_import_with_no_id_column_ignores_saved_config(self, sqlite_session_factory, admin_user, test_assembly):
        """Test that when no id_column is specified, saved config is ignored in favour of first CSV column"""
        # Save a config with a different id_column
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            update_csv_config(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                id_column="old_col",
            )

        csv_content = """new_col,name
user001,Alice"""

        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            respondents, _, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                csv_content=csv_content,
                replace_existing=False,
            )

            assert resolved_id_column == "new_col"
            assert len(respondents) == 1
            assert respondents[0].external_id == "user001"

    def test_import_returns_explicit_id_column(self, sqlite_session_factory, admin_user, test_assembly):
        """Test that an explicit id_column is returned as the resolved column"""
        csv_content = """custom_id,name
user001,Alice"""

        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            respondents, _, resolved_id_column = import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                csv_content=csv_content,
                replace_existing=False,
                id_column="custom_id",
            )

            assert resolved_id_column == "custom_id"
            assert len(respondents) == 1

    def test_get_or_create_csv_config(self, sqlite_session_factory, admin_user, test_assembly):
        """Test get_or_create_csv_config service function"""
        # First call creates config
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            config = get_or_create_csv_config(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
            )

            assert config is not None
            assert config.id_column == "external_id"
            assert config.assembly_id == test_assembly.id

        # Second call returns existing config
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            config2 = get_or_create_csv_config(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
            )

            assert config2.assembly_id == config.assembly_id
            assert config2.id_column == config.id_column

    def test_update_csv_config(self, sqlite_session_factory, admin_user, test_assembly):
        """Test update_csv_config service function"""
        # Create initial config
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            config = update_csv_config(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=test_assembly.id,
                id_column="custom_id",
                check_same_address=False,
                selection_algorithm="nash",
                columns_to_keep=["name", "email", "age"],
            )

            assert config.id_column == "custom_id"
            assert config.check_same_address is False
            assert config.selection_algorithm == "nash"
            assert config.columns_to_keep == ["name", "email", "age"]

        # Verify changes persisted
        with SqlAlchemyUnitOfWork(session_factory=sqlite_session_factory) as uow:
            assembly = uow.assemblies.get(test_assembly.id)
            assert assembly.csv.id_column == "custom_id"
            assert assembly.csv.check_same_address is False
            assert assembly.csv.selection_algorithm == "nash"
            assert assembly.csv.columns_to_keep == ["name", "email", "age"]
