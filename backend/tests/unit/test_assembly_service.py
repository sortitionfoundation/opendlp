"""ABOUTME: Unit tests for assembly service layer operations
ABOUTME: Tests assembly creation, updates, permissions, and lifecycle management with fake repositories"""

import uuid
from datetime import date, timedelta

import pytest

from opendlp.domain.assembly import Assembly, AssemblyGSheet
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import assembly_service, target_service
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    GoogleSheetConfigNotFoundError,
    InsufficientPermissions,
    UserNotFoundError,
)
from tests.data import VALID_GSHEET_URL


class TestCreateAssembly:
    """Test assembly creation functionality."""

    def test_create_assembly_success_admin(self, uow):
        """Test successful assembly creation by admin."""
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

    def test_create_assembly_success_organiser(self, uow):
        """Test successful assembly creation by an organiser."""
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
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

    def test_creator_becomes_assembly_manager(self, uow):
        """An organiser can reach what they create, which needs a role on it."""
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(organiser_user)

        assembly = assembly_service.create_assembly(
            uow=uow, title="Test Assembly", created_by_user_id=organiser_user.id
        )

        assert organiser_user.get_assembly_role(assembly.id) == AssemblyRole.ASSEMBLY_MANAGER

    def test_admin_creator_also_becomes_assembly_manager(self, uow):
        """Uniform with an organiser - the case most likely to regress if a branch reappears."""
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        assembly = assembly_service.create_assembly(uow=uow, title="Test Assembly", created_by_user_id=admin_user.id)

        assert admin_user.get_assembly_role(assembly.id) == AssemblyRole.ASSEMBLY_MANAGER

    def test_creator_is_recorded_on_the_assembly(self, uow):
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(organiser_user)

        assembly = assembly_service.create_assembly(
            uow=uow, title="Test Assembly", created_by_user_id=organiser_user.id
        )

        assert assembly.created_by_user_id == organiser_user.id

    def test_create_assembly_insufficient_permissions(self, uow):
        """Test assembly creation fails for regular user."""
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

    def test_create_assembly_user_not_found(self, uow):
        """Test assembly creation fails when user not found."""
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

    def test_create_assembly_minimal_data(self, uow):
        """Test creating assembly with only required fields."""
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


class TestUpdateAssembly:
    """Test assembly update functionality."""

    def test_update_assembly_success_admin(self, uow):
        """Test successful assembly update by admin."""
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

    def test_update_assembly_success_assembly_manager(self, uow):
        """Test successful assembly update by assembly manager."""
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

    def test_update_assembly_insufficient_permissions(self, uow):
        """Test assembly update fails for user without permissions."""
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

    def test_update_assembly_not_found(self, uow):
        """Test assembly update fails when assembly not found."""
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

    def test_get_assembly_success_admin(self, uow):
        """Test successful assembly retrieval by admin."""
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

    def test_get_assembly_success_with_role(self, uow):
        """Test successful assembly retrieval by user with assembly role."""
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

    def test_get_assembly_insufficient_permissions(self, uow):
        """Test assembly retrieval fails without permissions."""
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

    def test_archive_assembly_success(self, uow):
        """Test successful assembly archival."""
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

    def test_archive_assembly_insufficient_permissions(self, uow):
        """Test assembly archival fails without permissions."""
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

    def test_get_accessible_assemblies_admin(self, uow):
        """Test admin can access all assemblies."""
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

    def test_get_accessible_assemblies_user_not_found(self, uow):
        """Test error when user not found."""

        with pytest.raises(UserNotFoundError) as exc_info:
            assembly_service.get_user_accessible_assemblies(uow=uow, user_id=uuid.uuid4())

        assert "not found" in str(exc_info.value)


class TestAssemblyGSheetOperations:
    """Test AssemblyGSheet management operations."""

    def test_add_assembly_gsheet_success_admin(self, uow):
        """Test successful AssemblyGSheet creation by admin."""
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
        assert len(uow.assembly_gsheets.all()) == 1
        # UK team defaults are applied to selection settings, not to gsheet
        assert assembly.selection_settings is not None
        assert assembly.selection_settings.id_column == "nationbuilder_id"  # UK default

    def test_add_assembly_gsheet_with_overrides(self, uow):
        """Test adding AssemblyGSheet with custom options."""
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
        # id_column is now on selection settings, not on gsheet
        assert assembly.selection_settings is not None
        assert assembly.selection_settings.id_column == "custom_id"

    def test_add_assembly_gsheet_assembly_manager(self, uow):
        """Test AssemblyGSheet creation by assembly manager."""
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

    def test_add_assembly_gsheet_insufficient_permissions(self, uow):
        """Test AssemblyGSheet creation fails for user without permissions."""
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

    def test_add_assembly_gsheet_already_exists(self, uow):
        """Test AssemblyGSheet creation fails when assembly already has one."""
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

    def test_update_assembly_gsheet_success(self, uow):
        """Test successful AssemblyGSheet update."""
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
        # id_column and check_same_address_cols are now on selection settings
        assert assembly.selection_settings is not None
        assert assembly.selection_settings.id_column == "updated_id"
        assert assembly.selection_settings.check_same_address_cols == ["updated", "columns", "here"]

    def test_update_assembly_gsheet_not_found(self, uow):
        """Test AssemblyGSheet update fails when gsheet doesn't exist."""
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

    def test_remove_assembly_gsheet_success(self, uow):
        """Test successful AssemblyGSheet removal."""
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

    def test_remove_assembly_gsheet_not_found(self, uow):
        """Test AssemblyGSheet removal fails when gsheet doesn't exist."""
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

    def test_get_assembly_gsheet_success(self, uow):
        """Test successful AssemblyGSheet retrieval."""
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

    def test_get_assembly_gsheet_not_found(self, uow):
        """Test AssemblyGSheet retrieval returns None when not found."""
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

    def test_get_assembly_gsheet_insufficient_permissions(self, uow):
        """Test AssemblyGSheet retrieval fails without permissions."""
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


class TestSelectionSettingsDomainModel:
    """Test SelectionSettings domain model functionality used in assembly service context."""

    def test_check_same_address_cols_string_property(self):
        """Test check_same_address_cols_string property converts list to comma-separated string."""
        sel_settings = SelectionSettings(
            assembly_id=uuid.uuid4(),
            check_same_address_cols=["primary_address1", "zip_royal_mail", "city"],
        )

        assert sel_settings.check_same_address_cols_string == "primary_address1, zip_royal_mail, city"

    def test_check_same_address_cols_string_property_empty_list(self):
        """Test check_same_address_cols_string property with empty list."""
        sel_settings = SelectionSettings(assembly_id=uuid.uuid4(), check_same_address_cols=[])

        assert sel_settings.check_same_address_cols_string == ""

    def test_columns_to_keep_string_property(self):
        """Test columns_to_keep_string property converts list to comma-separated string."""
        sel_settings = SelectionSettings(
            assembly_id=uuid.uuid4(),
            columns_to_keep=["first_name", "last_name", "email", "mobile_number"],
        )

        assert sel_settings.columns_to_keep_string == "first_name, last_name, email, mobile_number"

    def test_columns_to_keep_string_property_empty_list(self):
        """Test columns_to_keep_string property with empty list."""
        sel_settings = SelectionSettings(assembly_id=uuid.uuid4(), columns_to_keep=[])

        assert sel_settings.columns_to_keep_string == ""

    def test_convert_str_kwargs_address_cols(self):
        """Test convert_str_kwargs method updates check_same_address_cols from string."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            check_same_address_cols_string="address1, postal_code, city",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.check_same_address_cols == ["address1", "postal_code", "city"]

    def test_convert_str_kwargs_columns_to_keep(self):
        """Test convert_str_kwargs method updates columns_to_keep from string."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            columns_to_keep_string="first_name, last_name, email",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.columns_to_keep == ["first_name", "last_name", "email"]

    def test_convert_str_kwargs_both_fields(self):
        """Test convert_str_kwargs method updates both fields simultaneously."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            check_same_address_cols_string="street, postcode",
            columns_to_keep_string="name, email, phone",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.check_same_address_cols == ["street", "postcode"]
        assert sel_settings.columns_to_keep == ["name", "email", "phone"]

    def test_convert_str_kwargs_with_spaces_and_empty_values(self):
        """Test convert_str_kwargs handles extra spaces and empty values."""
        kwargs = dict(
            assembly_id=uuid.uuid4(),
            check_same_address_cols_string="  address1 ,  , postal_code ,  city  ",
            columns_to_keep_string="first_name, , last_name,  email , ",
        )
        sel_settings = SelectionSettings(**SelectionSettings.convert_str_kwargs(**kwargs))

        assert sel_settings.check_same_address_cols == ["address1", "postal_code", "city"]
        assert sel_settings.columns_to_keep == ["first_name", "last_name", "email"]

    def test_convert_str_kwargs_empty_strings(self):
        """Test convert_str_kwargs with empty strings produces empty lists."""
        sel_settings = SelectionSettings(
            assembly_id=uuid.uuid4(),
            check_same_address_cols=["original_address"],
            columns_to_keep=["original_column"],
        )
        converted = SelectionSettings.convert_str_kwargs(check_same_address_cols_string="", columns_to_keep_string="")
        for key, value in converted.items():
            setattr(sel_settings, key, value)

        assert sel_settings.check_same_address_cols == []
        assert sel_settings.columns_to_keep == []

    def test_convert_str_kwargs_single_field(self):
        """Test convert_str_kwargs with only one field provided."""
        sel_settings = SelectionSettings(
            assembly_id=uuid.uuid4(),
            check_same_address_cols=["original_address"],
            columns_to_keep=["original_column"],
        )
        # Update only address columns
        converted = SelectionSettings.convert_str_kwargs(check_same_address_cols_string="new_address, new_postcode")
        for key, value in converted.items():
            setattr(sel_settings, key, value)

        assert sel_settings.check_same_address_cols == ["new_address", "new_postcode"]
        assert sel_settings.columns_to_keep == ["original_column"]  # Should remain unchanged


class TestCreateTargetCategoryAutoPopulate:
    """Test auto-population of target category values from respondent data."""

    def _setup(self, uow):
        admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin)
        assembly = Assembly(title="Test", question="?", number_to_select=30)
        uow.assemblies.add(assembly)
        return admin, assembly

    def test_auto_populates_values_from_matching_respondent_column(self, uow):
        """Creating a category whose name matches a respondent column auto-adds its values."""
        admin, assembly = self._setup(uow)
        uow.respondents.add(Respondent(assembly_id=assembly.id, external_id="1", attributes={"Gender": "Male"}))
        uow.respondents.add(Respondent(assembly_id=assembly.id, external_id="2", attributes={"Gender": "Female"}))
        uow.respondents.add(Respondent(assembly_id=assembly.id, external_id="3", attributes={"Gender": "Non-binary"}))

        category = target_service.create_target_category(uow, admin.id, assembly.id, name="Gender")

        value_names = sorted(v.value for v in category.values)
        assert value_names == ["Female", "Male", "Non-binary"]
        assert all(v.min == 0 for v in category.values)
        assert all(v.max == 0 for v in category.values)

    def test_auto_populates_case_insensitive(self, uow):
        """Auto-population matches column names case-insensitively."""
        admin, assembly = self._setup(uow)
        uow.respondents.add(Respondent(assembly_id=assembly.id, external_id="1", attributes={"Gender": "Male"}))
        uow.respondents.add(Respondent(assembly_id=assembly.id, external_id="2", attributes={"Gender": "Female"}))

        category = target_service.create_target_category(uow, admin.id, assembly.id, name="gender")

        value_names = sorted(v.value for v in category.values)
        assert value_names == ["Female", "Male"]

    def test_no_auto_populate_when_no_matching_column(self, uow):
        """No values are added when category name doesn't match any respondent column."""
        admin, assembly = self._setup(uow)
        uow.respondents.add(Respondent(assembly_id=assembly.id, external_id="1", attributes={"Gender": "Male"}))

        category = target_service.create_target_category(uow, admin.id, assembly.id, name="Ethnicity")

        assert category.values == []

    def test_no_auto_populate_when_no_respondents(self, uow):
        """No values are added when there are no respondents."""
        admin, assembly = self._setup(uow)

        category = target_service.create_target_category(uow, admin.id, assembly.id, name="Gender")

        assert category.values == []

    def test_no_auto_populate_for_high_cardinality_column(self, uow):
        """Columns with >= 20 distinct values are not auto-populated."""
        admin, assembly = self._setup(uow)
        for i in range(25):
            uow.respondents.add(
                Respondent(assembly_id=assembly.id, external_id=str(i), attributes={"PostCode": f"PC{i:03d}"})
            )

        category = target_service.create_target_category(uow, admin.id, assembly.id, name="PostCode")

        assert category.values == []


class TestOrganiserIsConfinedToTheirOwnAssemblies:
    """An organiser holds nothing over an assembly they were not added to.

    Creating assemblies and reading everyone else's are different capabilities;
    before issue 913 the one role granted both.
    """

    def _setup(self, uow):
        organiser = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(organiser)
        assembly = Assembly(title="Someone else's", question="?")
        uow.assemblies.add(assembly)
        return organiser, assembly

    def test_cannot_view(self, uow):
        organiser, assembly = self._setup(uow)

        with pytest.raises(InsufficientPermissions):
            assembly_service.get_assembly_with_permissions(uow, assembly.id, organiser.id)

    def test_cannot_update(self, uow):
        organiser, assembly = self._setup(uow)

        with pytest.raises(InsufficientPermissions):
            assembly_service.update_assembly(uow=uow, assembly_id=assembly.id, user_id=organiser.id, title="Mine now")

    def test_cannot_archive(self, uow):
        organiser, assembly = self._setup(uow)

        with pytest.raises(InsufficientPermissions):
            assembly_service.archive_assembly(uow=uow, assembly_id=assembly.id, user_id=organiser.id)

    def test_can_do_all_three_on_an_assembly_they_created(self, uow):
        """The mirror: creating it grants the assembly-manager role that permits all this."""
        organiser, _ = self._setup(uow)
        mine = assembly_service.create_assembly(uow=uow, title="Mine", created_by_user_id=organiser.id)

        assert assembly_service.get_assembly_with_permissions(uow, mine.id, organiser.id).title == "Mine"
        assembly_service.update_assembly(uow=uow, assembly_id=mine.id, user_id=organiser.id, title="Mine, renamed")
        assembly_service.archive_assembly(uow=uow, assembly_id=mine.id, user_id=organiser.id)


class TestGetAssemblyCreatorName:
    """Naming the creator on the details page, and the three ways there is nobody to name."""

    def test_returns_the_creators_display_name(self, uow):
        creator = User(
            email="creator@example.com",
            first_name="Ada",
            last_name="Lovelace",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(creator)
        assembly = assembly_service.create_assembly(uow=uow, title="Theirs", created_by_user_id=creator.id)

        assert assembly_service.get_assembly_creator_name(uow, assembly) == "Ada Lovelace"

    def test_returns_empty_when_no_creator_was_recorded(self, uow):
        """Assemblies created before the column existed carry no creator."""
        assembly = Assembly(title="Predates the column", question="?")
        uow.assemblies.add(assembly)

        assert assembly_service.get_assembly_creator_name(uow, assembly) == ""

    def test_returns_empty_when_the_creator_has_been_deleted(self, uow):
        """The foreign key is SET NULL, but a stale id must not blow up the page either."""
        assembly = Assembly(title="Orphaned", question="?", created_by_user_id=uuid.uuid4())
        uow.assemblies.add(assembly)

        assert assembly_service.get_assembly_creator_name(uow, assembly) == ""

    def test_falls_back_to_the_email_prefix_when_the_creator_has_no_name(self, uow):
        """display_name's own fallback, which matters for accounts created by invite."""
        creator = User(
            email="nameless@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(creator)
        assembly = assembly_service.create_assembly(uow=uow, title="Theirs", created_by_user_id=creator.id)

        assert assembly_service.get_assembly_creator_name(uow, assembly) == "nameless"
