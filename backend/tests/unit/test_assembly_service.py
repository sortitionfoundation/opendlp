"""ABOUTME: Unit tests for assembly service layer operations
ABOUTME: Tests assembly creation, updates, permissions, and lifecycle management with fake repositories"""

import uuid
from datetime import date, timedelta

import pytest

from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import assembly_service
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InsufficientPermissions,
    UserNotFoundError,
)
from tests.data import VALID_GSHEET_URL
from tests.fakes import FakeUnitOfWork


class TestCreateAssembly:
    """Test assembly creation functionality."""

    def test_create_assembly_success_admin(self):
        """Test successful assembly creation by admin."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)

        assembly = assembly_service.create_assembly(
            uow=uow,
            title="Test Assembly",
            created_by_user_id=admin_user.id,
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert assembly.title == "Test Assembly"
        assert assembly.question == "Test question?"
        assert assembly.first_assembly_date == future_date
        assert assembly.status == AssemblyStatus.ACTIVE
        assert len(uow.assemblies.all()) == 1
        assert uow.committed

    def test_create_assembly_success_global_organiser(self):
        """Test successful assembly creation by global organiser."""
        uow = FakeUnitOfWork()
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )
        uow.users.add(organiser_user)

        future_date = date.today() + timedelta(days=30)

        assembly = assembly_service.create_assembly(
            uow=uow,
            title="Test Assembly",
            created_by_user_id=organiser_user.id,
            question="Test question?",
            first_assembly_date=future_date,
        )

        assert assembly.title == "Test Assembly"
        assert uow.committed

    def test_create_assembly_insufficient_permissions(self):
        """Test assembly creation fails for regular user."""
        uow = FakeUnitOfWork()
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)

        with pytest.raises(InsufficientPermissions):
            assembly_service.create_assembly(
                uow=uow,
                title="Test Assembly",
                created_by_user_id=regular_user.id,
                question="Test question?",
                first_assembly_date=future_date,
            )

    def test_create_assembly_user_not_found(self):
        """Test assembly creation fails when user not found."""
        uow = FakeUnitOfWork()
        future_date = date.today() + timedelta(days=30)

        with pytest.raises(UserNotFoundError) as exc_info:
            assembly_service.create_assembly(
                uow=uow,
                title="Test Assembly",
                created_by_user_id=uuid.uuid4(),
                question="Test question?",
                first_assembly_date=future_date,
            )

        assert "not found" in str(exc_info.value)

    def test_create_assembly_minimal_data(self):
        """Test creating assembly with only required fields."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = assembly_service.create_assembly(
            uow=uow,
            title="Minimal Assembly",
            created_by_user_id=admin_user.id,
        )

        assert assembly.title == "Minimal Assembly"
        assert assembly.question == ""
        assert assembly.first_assembly_date is None
        assert assembly.status == AssemblyStatus.ACTIVE
        assert len(uow.assemblies.all()) == 1
        assert uow.committed


class TestUpdateAssembly:
    """Test assembly update functionality."""

    def test_update_assembly_success_admin(self):
        """Test successful assembly update by admin."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Original Title",
            question="Original question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        updated_assembly = assembly_service.update_assembly(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
            title="Updated Title",
            question="Updated question?",
        )

        assert updated_assembly.title == "Updated Title"
        assert updated_assembly.question == "Updated question?"
        assert uow.committed

    def test_update_assembly_success_assembly_manager(self):
        """Test successful assembly update by assembly manager."""
        uow = FakeUnitOfWork()
        manager_user = User(email="manager@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(manager_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add assembly role
        assembly_role = UserAssemblyRole(
            user_id=manager_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )
        manager_user.assembly_roles.append(assembly_role)

        updated_assembly = assembly_service.update_assembly(
            uow=uow, assembly_id=assembly.id, user_id=manager_user.id, title="Updated Title"
        )

        assert updated_assembly.title == "Updated Title"
        assert uow.committed

    def test_update_assembly_insufficient_permissions(self):
        """Test assembly update fails for user without permissions."""
        uow = FakeUnitOfWork()
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        with pytest.raises(InsufficientPermissions):
            assembly_service.update_assembly(
                uow=uow, assembly_id=assembly.id, user_id=regular_user.id, title="Updated Title"
            )

    def test_update_assembly_not_found(self):
        """Test assembly update fails when assembly not found."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        with pytest.raises(AssemblyNotFoundError) as exc_info:
            assembly_service.update_assembly(
                uow=uow, assembly_id=uuid.uuid4(), user_id=admin_user.id, title="Updated Title"
            )

        assert "Assembly" in str(exc_info.value)
        assert "not found" in str(exc_info.value)


class TestGetAssemblyWithPermissions:
    """Test assembly retrieval with permission checks."""

    def test_get_assembly_success_admin(self):
        """Test successful assembly retrieval by admin."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        retrieved_assembly = assembly_service.get_assembly_with_permissions(
            uow=uow, assembly_id=assembly.id, user_id=admin_user.id
        )

        assert retrieved_assembly == assembly

    def test_get_assembly_success_with_role(self):
        """Test successful assembly retrieval by user with assembly role."""
        uow = FakeUnitOfWork()
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add assembly role
        assembly_role = UserAssemblyRole(
            user_id=user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        user.assembly_roles.append(assembly_role)

        retrieved_assembly = assembly_service.get_assembly_with_permissions(
            uow=uow, assembly_id=assembly.id, user_id=user.id
        )

        assert retrieved_assembly == assembly

    def test_get_assembly_insufficient_permissions(self):
        """Test assembly retrieval fails without permissions."""
        uow = FakeUnitOfWork()
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        with pytest.raises(InsufficientPermissions):
            assembly_service.get_assembly_with_permissions(uow=uow, assembly_id=assembly.id, user_id=regular_user.id)


class TestArchiveAssembly:
    """Test assembly archival functionality."""

    def test_archive_assembly_success(self):
        """Test successful assembly archival."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        archived_assembly = assembly_service.archive_assembly(uow=uow, assembly_id=assembly.id, user_id=admin_user.id)

        assert archived_assembly.status == AssemblyStatus.ARCHIVED
        assert uow.committed

    def test_archive_assembly_insufficient_permissions(self):
        """Test assembly archival fails without permissions."""
        uow = FakeUnitOfWork()
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        with pytest.raises(InsufficientPermissions):
            assembly_service.archive_assembly(uow=uow, assembly_id=assembly.id, user_id=regular_user.id)


class TestGetUserAccessibleAssemblies:
    """Test getting user's accessible assemblies."""

    def test_get_accessible_assemblies_admin(self):
        """Test admin can access all assemblies."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Add assemblies
        future_date = date.today() + timedelta(days=30)
        assembly1 = Assembly(
            title="Assembly 1",
            question="Question 1?",
            first_assembly_date=future_date,
        )
        assembly2 = Assembly(
            title="Assembly 2",
            question="Question 2?",
            first_assembly_date=future_date + timedelta(days=1),
        )
        uow.assemblies.add(assembly1)
        uow.assemblies.add(assembly2)

        assemblies = assembly_service.get_user_accessible_assemblies(uow=uow, user_id=admin_user.id)

        assert len(assemblies) == 2

    def test_get_accessible_assemblies_user_not_found(self):
        """Test error when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(UserNotFoundError) as exc_info:
            assembly_service.get_user_accessible_assemblies(uow=uow, user_id=uuid.uuid4())

        assert "not found" in str(exc_info.value)


class TestAssemblyGSheetOperations:
    """Test AssemblyGSheet management operations."""

    def test_add_assembly_gsheet_success_admin(self):
        """Test successful AssemblyGSheet creation by admin."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        assembly_gsheet = assembly_service.add_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
            url=VALID_GSHEET_URL,
            team="uk",
        )

        assert assembly_gsheet.assembly_id == assembly.id
        assert assembly_gsheet.url == VALID_GSHEET_URL
        assert assembly_gsheet.id_column == "nationbuilder_id"  # UK default
        assert len(uow.assembly_gsheets.all()) == 1
        assert uow.committed

    def test_add_assembly_gsheet_with_overrides(self):
        """Test adding AssemblyGSheet with custom options."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        assembly_gsheet = assembly_service.add_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
            url=VALID_GSHEET_URL,
            team="other",
            select_registrants_tab="Custom Registrants",
            id_column="custom_id",
        )

        assert assembly_gsheet.select_registrants_tab == "Custom Registrants"
        assert assembly_gsheet.id_column == "custom_id"
        assert uow.committed

    def test_add_assembly_gsheet_assembly_manager(self):
        """Test AssemblyGSheet creation by assembly manager."""
        uow = FakeUnitOfWork()
        manager_user = User(email="manager@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(manager_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add assembly role
        assembly_role = UserAssemblyRole(
            user_id=manager_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )
        manager_user.assembly_roles.append(assembly_role)

        assembly_gsheet = assembly_service.add_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=manager_user.id,
            url=VALID_GSHEET_URL,
        )

        assert assembly_gsheet.assembly_id == assembly.id
        assert uow.committed

    def test_add_assembly_gsheet_insufficient_permissions(self):
        """Test AssemblyGSheet creation fails for user without permissions."""
        uow = FakeUnitOfWork()
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        with pytest.raises(InsufficientPermissions):
            assembly_service.add_assembly_gsheet(
                uow=uow,
                assembly_id=assembly.id,
                user_id=regular_user.id,
                url=VALID_GSHEET_URL,
            )

    def test_add_assembly_gsheet_already_exists(self):
        """Test AssemblyGSheet creation fails when assembly already has one."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add first gsheet
        existing_gsheet = AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL)
        uow.assembly_gsheets.add(existing_gsheet)

        with pytest.raises(ValueError) as exc_info:
            assembly_service.add_assembly_gsheet(
                uow=uow,
                assembly_id=assembly.id,
                user_id=admin_user.id,
                url=VALID_GSHEET_URL,
            )

        assert "already has a Google Spreadsheet configuration" in str(exc_info.value)

    def test_update_assembly_gsheet_success(self):
        """Test successful AssemblyGSheet update."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add existing gsheet
        existing_gsheet = AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL)
        uow.assembly_gsheets.add(existing_gsheet)

        updated_gsheet = assembly_service.update_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
            select_registrants_tab="Updated Tab",
            id_column="updated_id",
            check_same_address_cols_string="updated, columns, here",
            team="other",
        )

        assert updated_gsheet.select_registrants_tab == "Updated Tab"
        assert updated_gsheet.id_column == "updated_id"
        assert updated_gsheet.check_same_address_cols == ["updated", "columns", "here"]
        assert uow.committed

    def test_update_assembly_gsheet_not_found(self):
        """Test AssemblyGSheet update fails when gsheet doesn't exist."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        with pytest.raises(GoogleSheetConfigNotFoundError) as exc_info:
            assembly_service.update_assembly_gsheet(
                uow=uow,
                assembly_id=assembly.id,
                user_id=admin_user.id,
                select_registrants_tab="Updated Tab",
            )

        assert "does not have a Google Spreadsheet configuration" in str(exc_info.value)

    def test_remove_assembly_gsheet_success(self):
        """Test successful AssemblyGSheet removal."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add existing gsheet
        existing_gsheet = AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL)
        uow.assembly_gsheets.add(existing_gsheet)

        assembly_service.remove_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
        )

        assert len(uow.assembly_gsheets.all()) == 0
        assert uow.committed

    def test_remove_assembly_gsheet_not_found(self):
        """Test AssemblyGSheet removal fails when gsheet doesn't exist."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        with pytest.raises(GoogleSheetConfigNotFoundError) as exc_info:
            assembly_service.remove_assembly_gsheet(
                uow=uow,
                assembly_id=assembly.id,
                user_id=admin_user.id,
            )

        assert "does not have a Google Spreadsheet configuration" in str(exc_info.value)

    def test_get_assembly_gsheet_success(self):
        """Test successful AssemblyGSheet retrieval."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add existing gsheet
        existing_gsheet = AssemblyGSheet(
            assembly_id=assembly.id,
            url=VALID_GSHEET_URL,
            select_registrants_tab="Custom Tab",
        )
        uow.assembly_gsheets.add(existing_gsheet)

        retrieved_gsheet = assembly_service.get_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
        )

        assert retrieved_gsheet is not None
        assert retrieved_gsheet.assembly_id == assembly.id
        assert retrieved_gsheet.url == VALID_GSHEET_URL
        assert retrieved_gsheet.select_registrants_tab == "Custom Tab"

    def test_get_assembly_gsheet_not_found(self):
        """Test AssemblyGSheet retrieval returns None when not found."""
        uow = FakeUnitOfWork()
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        retrieved_gsheet = assembly_service.get_assembly_gsheet(
            uow=uow,
            assembly_id=assembly.id,
            user_id=admin_user.id,
        )

        assert retrieved_gsheet is None

    def test_get_assembly_gsheet_insufficient_permissions(self):
        """Test AssemblyGSheet retrieval fails without permissions."""
        uow = FakeUnitOfWork()
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add existing gsheet
        existing_gsheet = AssemblyGSheet(assembly_id=assembly.id, url=VALID_GSHEET_URL)
        uow.assembly_gsheets.add(existing_gsheet)

        with pytest.raises(InsufficientPermissions):
            assembly_service.get_assembly_gsheet(
                uow=uow,
                assembly_id=assembly.id,
                user_id=regular_user.id,
            )


class TestAssemblyGSheetDomainModel:
    """Test AssemblyGSheet domain model functionality."""

    def test_check_same_address_cols_string_property(self):
        """Test check_same_address_cols_string property converts list to comma-separated string."""
        gsheet = AssemblyGSheet(
            assembly_id=uuid.uuid4(),
            url=VALID_GSHEET_URL,
            check_same_address_cols=["primary_address1", "zip_royal_mail", "city"],
        )

        assert gsheet.check_same_address_cols_string == "primary_address1, zip_royal_mail, city"

    def test_check_same_address_cols_string_property_empty_list(self):
        """Test check_same_address_cols_string property with empty list."""
        gsheet = AssemblyGSheet(assembly_id=uuid.uuid4(), url=VALID_GSHEET_URL, check_same_address_cols=[])

        assert gsheet.check_same_address_cols_string == ""

    def test_columns_to_keep_string_property(self):
        """Test columns_to_keep_string property converts list to comma-separated string."""
        gsheet = AssemblyGSheet(
            assembly_id=uuid.uuid4(),
            url=VALID_GSHEET_URL,
            columns_to_keep=["first_name", "last_name", "email", "mobile_number"],
        )

        assert gsheet.columns_to_keep_string == "first_name, last_name, email, mobile_number"

    def test_columns_to_keep_string_property_empty_list(self):
        """Test columns_to_keep_string property with empty list."""
        gsheet = AssemblyGSheet(assembly_id=uuid.uuid4(), url=VALID_GSHEET_URL, columns_to_keep=[])

        assert gsheet.columns_to_keep_string == ""

    def test_convert_str_kwargs_address_cols(self):
        """Test convert_str_kwargs method updates check_same_address_cols from string."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            url=VALID_GSHEET_URL,
            check_same_address_cols_string="address1, postal_code, city",
        )
        gsheet = AssemblyGSheet(**AssemblyGSheet.convert_str_kwargs(**kwargs))

        assert gsheet.check_same_address_cols == ["address1", "postal_code", "city"]

    def test_convert_str_kwargs_columns_to_keep(self):
        """Test convert_str_kwargs method updates columns_to_keep from string."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            url=VALID_GSHEET_URL,
            columns_to_keep_string="first_name, last_name, email",
        )
        gsheet = AssemblyGSheet(**AssemblyGSheet.convert_str_kwargs(**kwargs))

        assert gsheet.columns_to_keep == ["first_name", "last_name", "email"]

    def test_convert_str_kwargs_both_fields(self):
        """Test convert_str_kwargs method updates both fields simultaneously."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            url=VALID_GSHEET_URL,
            check_same_address_cols_string="street, postcode",
            columns_to_keep_string="name, email, phone",
        )
        gsheet = AssemblyGSheet(**AssemblyGSheet.convert_str_kwargs(**kwargs))

        assert gsheet.check_same_address_cols == ["street", "postcode"]
        assert gsheet.columns_to_keep == ["name", "email", "phone"]

    def test_convert_str_kwargs_with_spaces_and_empty_values(self):
        """Test convert_str_kwargs handles extra spaces and empty values."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            url=VALID_GSHEET_URL,
            check_same_address_cols_string="  address1 ,  , postal_code ,  city  ",
            columns_to_keep_string="first_name, , last_name,  email , ",
        )
        gsheet = AssemblyGSheet(**AssemblyGSheet.convert_str_kwargs(**kwargs))

        assert gsheet.check_same_address_cols == ["address1", "postal_code", "city"]
        assert gsheet.columns_to_keep == ["first_name", "last_name", "email"]

    def test_convert_str_kwargs_empty_strings(self):
        """Test convert_str_kwargs with empty strings does update fields."""
        original_address_cols = ["original_address"]
        original_columns = ["original_column"]

        gsheet = AssemblyGSheet(
            assembly_id=uuid.uuid4(),
            url=VALID_GSHEET_URL,
            check_same_address_cols=original_address_cols.copy(),
            columns_to_keep=original_columns.copy(),
        )
        gsheet.update_values(
            **AssemblyGSheet.convert_str_kwargs(check_same_address_cols_string="", columns_to_keep_string="")
        )

        # Should remain unchanged
        assert gsheet.check_same_address_cols == []
        assert gsheet.columns_to_keep == []

    def test_convert_str_kwargs_single_field(self):
        """Test convert_str_kwargs with only one field provided."""
        gsheet = AssemblyGSheet(
            assembly_id=uuid.uuid4(),
            url=VALID_GSHEET_URL,
            check_same_address_cols=["original_address"],
            columns_to_keep=["original_column"],
        )
        # Update only address columns
        gsheet.update_values(
            **AssemblyGSheet.convert_str_kwargs(check_same_address_cols_string="new_address, new_postcode")
        )

        assert gsheet.check_same_address_cols == ["new_address", "new_postcode"]
        assert gsheet.columns_to_keep == ["original_column"]  # Should remain unchanged
