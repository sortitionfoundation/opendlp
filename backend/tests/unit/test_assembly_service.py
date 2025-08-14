"""ABOUTME: Unit tests for assembly service layer operations
ABOUTME: Tests assembly creation, updates, permissions, and lifecycle management with fake repositories"""

import uuid
from datetime import date, timedelta

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import assembly_service
from opendlp.service_layer.exceptions import InsufficientPermissions
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
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert assembly.title == "Test Assembly"
        assert assembly.question == "Test question?"
        assert assembly.gsheet == "test-sheet"
        assert assembly.first_assembly_date == future_date
        assert assembly.status == AssemblyStatus.ACTIVE
        assert len(uow.assemblies.list()) == 1
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
            gsheet="test-sheet",
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
                gsheet="test-sheet",
                first_assembly_date=future_date,
            )

    def test_create_assembly_user_not_found(self):
        """Test assembly creation fails when user not found."""
        uow = FakeUnitOfWork()
        future_date = date.today() + timedelta(days=30)

        with pytest.raises(ValueError) as exc_info:
            assembly_service.create_assembly(
                uow=uow,
                title="Test Assembly",
                created_by_user_id=uuid.uuid4(),
                question="Test question?",
                gsheet="test-sheet",
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
        assert assembly.gsheet == ""
        assert assembly.first_assembly_date is None
        assert assembly.status == AssemblyStatus.ACTIVE
        assert len(uow.assemblies.list()) == 1
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
            gsheet="original-sheet",
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
        assert updated_assembly.gsheet == "original-sheet"  # Unchanged
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
            gsheet="test-sheet",
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
            gsheet="test-sheet",
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

        with pytest.raises(ValueError) as exc_info:
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
            gsheet="test-sheet",
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
            gsheet="test-sheet",
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
            gsheet="test-sheet",
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
            gsheet="test-sheet",
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
            gsheet="test-sheet",
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
            gsheet="sheet1",
            first_assembly_date=future_date,
        )
        assembly2 = Assembly(
            title="Assembly 2",
            question="Question 2?",
            gsheet="sheet2",
            first_assembly_date=future_date + timedelta(days=1),
        )
        uow.assemblies.add(assembly1)
        uow.assemblies.add(assembly2)

        assemblies = assembly_service.get_user_accessible_assemblies(uow=uow, user_id=admin_user.id)

        assert len(assemblies) == 2

    def test_get_accessible_assemblies_user_not_found(self):
        """Test error when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(ValueError) as exc_info:
            assembly_service.get_user_accessible_assemblies(uow=uow, user_id=uuid.uuid4())

        assert "not found" in str(exc_info.value)
