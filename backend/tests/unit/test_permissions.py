"""ABOUTME: Unit tests for permission checking utilities
ABOUTME: Tests role-based access control functions and decorators with various user roles"""

import uuid
from datetime import date, timedelta

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.exceptions import InsufficientPermissions
from opendlp.service_layer.permissions import (
    can_call_confirmations,
    can_manage_assembly,
    can_view_assembly,
    has_global_admin,
    has_global_organiser,
    require_assembly_permission,
    require_global_role,
)
from tests.fakes import FakeUnitOfWork


class TestCanManageAssembly:
    """Test assembly management permission checks."""

    def test_admin_can_manage_any_assembly(self):
        """Test admin can manage any assembly."""
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert can_manage_assembly(admin_user, assembly) is True

    def test_global_organiser_can_manage_any_assembly(self):
        """Test global organiser can manage any assembly."""
        organiser_user = User(
            username="organiser",
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert can_manage_assembly(organiser_user, assembly) is True

    def test_assembly_manager_can_manage_specific_assembly(self):
        """Test assembly manager can manage their assigned assembly."""
        manager_user = User(
            username="manager", email="manager@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        # Add assembly role
        assembly_role = UserAssemblyRole(
            user_id=manager_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )
        manager_user.assembly_roles.append(assembly_role)

        assert can_manage_assembly(manager_user, assembly) is True

    def test_confirmation_caller_cannot_manage_assembly(self):
        """Test confirmation caller cannot manage assembly."""
        caller_user = User(
            username="caller", email="caller@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        # Add confirmation caller role
        assembly_role = UserAssemblyRole(
            user_id=caller_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        caller_user.assembly_roles.append(assembly_role)

        assert can_manage_assembly(caller_user, assembly) is False

    def test_regular_user_cannot_manage_assembly(self):
        """Test regular user cannot manage assembly."""
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert can_manage_assembly(regular_user, assembly) is False


class TestCanViewAssembly:
    """Test assembly viewing permission checks."""

    def test_admin_can_view_any_assembly(self):
        """Test admin can view any assembly."""
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert can_view_assembly(admin_user, assembly) is True

    def test_global_organiser_can_view_any_assembly(self):
        """Test global organiser can view any assembly."""
        organiser_user = User(
            username="organiser",
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert can_view_assembly(organiser_user, assembly) is True

    def test_assembly_role_can_view_assembly(self):
        """Test user with assembly role can view assembly."""
        user = User(username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        # Add any assembly role
        assembly_role = UserAssemblyRole(
            user_id=user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        user.assembly_roles.append(assembly_role)

        assert can_view_assembly(user, assembly) is True

    def test_regular_user_cannot_view_assembly(self):
        """Test regular user cannot view assembly without role."""
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert can_view_assembly(regular_user, assembly) is False


class TestCanCallConfirmations:
    """Test confirmation calling permission checks."""

    def test_admin_can_call_confirmations(self):
        """Test admin can call confirmations for any assembly."""
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert can_call_confirmations(admin_user, assembly) is True

    def test_assembly_manager_can_call_confirmations(self):
        """Test assembly manager can call confirmations."""
        manager_user = User(
            username="manager", email="manager@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        # Add assembly manager role
        assembly_role = UserAssemblyRole(
            user_id=manager_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )
        manager_user.assembly_roles.append(assembly_role)

        assert can_call_confirmations(manager_user, assembly) is True

    def test_confirmation_caller_can_call_confirmations(self):
        """Test confirmation caller can call confirmations."""
        caller_user = User(
            username="caller", email="caller@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        # Add confirmation caller role
        assembly_role = UserAssemblyRole(
            user_id=caller_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        caller_user.assembly_roles.append(assembly_role)

        assert can_call_confirmations(caller_user, assembly) is True

    def test_regular_user_cannot_call_confirmations(self):
        """Test regular user cannot call confirmations."""
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )

        assert can_call_confirmations(regular_user, assembly) is False


class TestGlobalRoleChecks:
    """Test global role checking functions."""

    def test_has_global_admin(self):
        """Test global admin detection."""
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )
        organiser_user = User(
            username="organiser",
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        assert has_global_admin(admin_user) is True
        assert has_global_admin(organiser_user) is False
        assert has_global_admin(regular_user) is False

    def test_has_global_organiser(self):
        """Test global organiser detection."""
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )
        organiser_user = User(
            username="organiser",
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        assert has_global_organiser(admin_user) is True  # Admin includes organiser privileges
        assert has_global_organiser(organiser_user) is True
        assert has_global_organiser(regular_user) is False


class TestRequireGlobalRoleDecorator:
    """Test global role requirement decorator."""

    def test_require_global_role_success(self):
        """Test decorator allows access with sufficient role."""
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )

        @require_global_role(GlobalRole.GLOBAL_ORGANISER)
        def test_function(uow, user):
            return "success"

        # Should succeed because admin >= global organiser
        result = test_function(None, admin_user)
        assert result == "success"

    def test_require_global_role_failure(self):
        """Test decorator blocks access with insufficient role."""
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        @require_global_role(GlobalRole.GLOBAL_ORGANISER)
        def test_function(uow, user):
            return "success"

        # Should fail because user < global organiser
        with pytest.raises(InsufficientPermissions):
            test_function(None, regular_user)

    def test_require_global_role_exact_match(self):
        """Test decorator allows access with exact role match."""
        organiser_user = User(
            username="organiser",
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )

        @require_global_role(GlobalRole.GLOBAL_ORGANISER)
        def test_function(uow, user):
            return "success"

        # Should succeed with exact match
        result = test_function(None, organiser_user)
        assert result == "success"


class TestRequireAssemblyPermissionDecorator:
    """Test assembly permission requirement decorator."""

    def test_require_assembly_permission_success(self):
        """Test decorator allows access with sufficient permission."""
        uow = FakeUnitOfWork()
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )
        uow.users.add(admin_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        @require_assembly_permission(can_manage_assembly)
        def test_function(uow, user_id, assembly_id, data):
            return f"success with {data}"

        # Should succeed because admin can manage any assembly
        result = test_function(uow, admin_user.id, assembly.id, "test_data")
        assert result == "success with test_data"

    def test_require_assembly_permission_failure(self):
        """Test decorator blocks access with insufficient permission."""
        uow = FakeUnitOfWork()
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        @require_assembly_permission(can_manage_assembly)
        def test_function(uow, user_id, assembly_id, data):
            return f"success with {data}"

        # Should fail because regular user cannot manage assembly
        with pytest.raises(InsufficientPermissions):
            test_function(uow, regular_user.id, assembly.id, "test_data")

    def test_require_assembly_permission_user_not_found(self):
        """Test decorator handles user not found."""
        uow = FakeUnitOfWork()
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        @require_assembly_permission(can_manage_assembly)
        def test_function(uow, user_id, assembly_id, data):
            return f"success with {data}"

        # Should fail with user not found
        with pytest.raises(ValueError) as exc_info:
            test_function(uow, uuid.uuid4(), assembly.id, "test_data")
        assert "User" in str(exc_info.value) and "not found" in str(exc_info.value)

    def test_require_assembly_permission_assembly_not_found(self):
        """Test decorator handles assembly not found."""
        uow = FakeUnitOfWork()
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )
        uow.users.add(admin_user)

        @require_assembly_permission(can_manage_assembly)
        def test_function(uow, user_id, assembly_id, data):
            return f"success with {data}"

        # Should fail with assembly not found
        with pytest.raises(ValueError) as exc_info:
            test_function(uow, admin_user.id, uuid.uuid4(), "test_data")
        assert "Assembly" in str(exc_info.value) and "not found" in str(exc_info.value)

    def test_require_assembly_permission_different_permission_functions(self):
        """Test decorator works with different permission functions."""
        uow = FakeUnitOfWork()
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        uow.users.add(regular_user)

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            gsheet="test-sheet",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        # Add assembly role so user can view but not manage
        assembly_role = UserAssemblyRole(
            user_id=regular_user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.CONFIRMATION_CALLER,
        )
        regular_user.assembly_roles.append(assembly_role)

        @require_assembly_permission(can_view_assembly)
        def view_function(uow, user_id, assembly_id):
            return "can view"

        @require_assembly_permission(can_manage_assembly)
        def manage_function(uow, user_id, assembly_id):
            return "can manage"

        # Should succeed for view (user has assembly role)
        result = view_function(uow, regular_user.id, assembly.id)
        assert result == "can view"

        # Should fail for manage (user cannot manage)
        with pytest.raises(InsufficientPermissions):
            manage_function(uow, regular_user.id, assembly.id)
