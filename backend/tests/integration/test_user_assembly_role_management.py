"""ABOUTME: Unit tests for UserAssemblyRole management service layer
ABOUTME: Tests grant and revoke functions with permission checks and error handling"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    InsufficientPermissions,
    NotFoundError,
    UserNotFoundError,
)
from opendlp.service_layer.user_service import grant_user_assembly_role, revoke_user_assembly_role
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def admin_user():
    """Create an admin user."""
    return User(
        email="admin@example.com",
        global_role=GlobalRole.ADMIN,
        password_hash="hash123",  # pragma: allowlist secret
    )


@pytest.fixture
def organiser_user():
    """Create a global organiser user."""
    return User(
        email="organiser@example.com",
        global_role=GlobalRole.GLOBAL_ORGANISER,
        password_hash="hash123",  # pragma: allowlist secret
    )


@pytest.fixture
def assembly_organiser_user():
    """Create a user with organiser role on a specific assembly."""
    return User(
        email="assembly_organiser@example.com",
        global_role=GlobalRole.USER,
        password_hash="hash123",  # pragma: allowlist secret
    )


@pytest.fixture
def regular_user():
    """Create a regular user."""
    return User(
        email="regular@example.com",
        global_role=GlobalRole.USER,
        password_hash="hash123",  # pragma: allowlist secret
    )


@pytest.fixture
def target_user():
    """Create a user to be granted/revoked roles."""
    return User(
        email="target@example.com",
        global_role=GlobalRole.USER,
        password_hash="hash123",  # pragma: allowlist secret
    )


@pytest.fixture
def assembly():
    """Create an assembly."""
    return Assembly(
        title="Test Assembly",
        question="What should we do?",
    )


@pytest.fixture
def uow():
    """Create a fake Unit of Work for testing."""
    return FakeUnitOfWork()


@pytest.fixture
def setup_database(uow, admin_user, organiser_user, assembly_organiser_user, regular_user, target_user, assembly):
    """Setup fake database with test users and assembly."""
    # Add users
    uow.users.add(admin_user)
    uow.users.add(organiser_user)
    uow.users.add(assembly_organiser_user)
    uow.users.add(regular_user)
    uow.users.add(target_user)

    # Add assembly
    uow.assemblies.add(assembly)

    # Give assembly_organiser_user the ASSEMBLY_MANAGER role on the assembly
    assembly_role = UserAssemblyRole(
        user_id=assembly_organiser_user.id,
        assembly_id=assembly.id,
        role=AssemblyRole.ASSEMBLY_MANAGER,
    )
    uow.user_assembly_roles.add(assembly_role)
    assembly_organiser_user.assembly_roles.append(assembly_role)

    return {
        "admin_user": admin_user,
        "organiser_user": organiser_user,
        "assembly_organiser_user": assembly_organiser_user,
        "regular_user": regular_user,
        "target_user": target_user,
        "assembly": assembly,
    }


class TestGrantUserAssemblyRole:
    """Tests for granting users assembly roles."""

    def test_admin_can_grant_role(self, uow, setup_database):
        """Admin can grant roles to any user on any assembly."""
        data = setup_database
        result = grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.CONFIRMATION_CALLER,
            current_user=data["admin_user"],
        )

        assert isinstance(result, UserAssemblyRole)
        assert result.user_id == data["target_user"].id
        assert result.assembly_id == data["assembly"].id
        assert result.role == AssemblyRole.CONFIRMATION_CALLER

    def test_global_organiser_can_grant_role(self, uow, setup_database):
        """Global organiser can grant roles to any user on any assembly."""
        data = setup_database
        result = grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
            current_user=data["organiser_user"],
        )

        assert isinstance(result, UserAssemblyRole)
        assert result.role == AssemblyRole.ASSEMBLY_MANAGER

    def test_assembly_organiser_can_grant_role_on_their_assembly(self, uow, setup_database):
        """Assembly organiser can grant roles on their own assembly."""
        data = setup_database
        result = grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.CONFIRMATION_CALLER,
            current_user=data["assembly_organiser_user"],
        )

        assert isinstance(result, UserAssemblyRole)
        assert result.role == AssemblyRole.CONFIRMATION_CALLER

    def test_regular_user_cannot_grant_role(self, uow, setup_database):
        """Regular user cannot grant roles."""
        data = setup_database
        with pytest.raises(InsufficientPermissions):
            grant_user_assembly_role(
                uow=uow,
                user_id=data["target_user"].id,
                assembly_id=data["assembly"].id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=data["regular_user"],
            )

    def test_user_cannot_grant_role_on_assembly_they_dont_organise(self, uow, setup_database):
        """User cannot grant roles on assembly they don't organise."""
        data = setup_database
        # Create another assembly
        other_assembly = Assembly(title="Other Assembly")
        with uow:
            uow.assemblies.add(other_assembly)
            uow.commit()

        with pytest.raises(InsufficientPermissions):
            grant_user_assembly_role(
                uow=uow,
                user_id=data["target_user"].id,
                assembly_id=other_assembly.id,
                role=AssemblyRole.ASSEMBLY_MANAGER,
                current_user=data["assembly_organiser_user"],
            )

    def test_grant_role_when_target_user_does_not_exist(self, uow, setup_database):
        """Raises exception when target user doesn't exist."""
        data = setup_database
        nonexistent_user_id = uuid.uuid4()

        with pytest.raises(UserNotFoundError, match="User .* not found"):
            grant_user_assembly_role(
                uow=uow,
                user_id=nonexistent_user_id,
                assembly_id=data["assembly"].id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=data["admin_user"],
            )

    def test_grant_role_when_assembly_does_not_exist(self, uow, setup_database):
        """Raises exception when assembly doesn't exist."""
        data = setup_database
        nonexistent_assembly_id = uuid.uuid4()

        with pytest.raises(AssemblyNotFoundError, match="Assembly .* not found"):
            grant_user_assembly_role(
                uow=uow,
                user_id=data["target_user"].id,
                assembly_id=nonexistent_assembly_id,
                role=AssemblyRole.CONFIRMATION_CALLER,
                current_user=data["admin_user"],
            )

    def test_update_existing_role(self, uow, setup_database):
        """Updating existing role replaces the old role."""
        data = setup_database
        # First grant a role
        first_result = grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.CONFIRMATION_CALLER,
            current_user=data["admin_user"],
        )

        # Now update to a different role
        second_result = grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
            current_user=data["admin_user"],
        )

        # Should be the same ID (updated, not new)
        assert first_result.id == second_result.id
        assert second_result.role == AssemblyRole.ASSEMBLY_MANAGER


class TestRevokeUserAssemblyRole:
    """Tests for revoking user assembly roles."""

    def test_admin_can_revoke_role(self, uow, setup_database):
        """Admin can revoke roles from any user on any assembly."""
        data = setup_database
        # First grant a role
        grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.CONFIRMATION_CALLER,
            current_user=data["admin_user"],
        )

        # Now revoke it
        result = revoke_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            current_user=data["admin_user"],
        )

        assert isinstance(result, UserAssemblyRole)
        assert result.user_id == data["target_user"].id
        assert result.assembly_id == data["assembly"].id

    def test_global_organiser_can_revoke_role(self, uow, setup_database):
        """Global organiser can revoke roles from any user on any assembly."""
        data = setup_database
        grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
            current_user=data["admin_user"],
        )

        result = revoke_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            current_user=data["organiser_user"],
        )

        assert isinstance(result, UserAssemblyRole)

    def test_assembly_organiser_can_revoke_role_on_their_assembly(self, uow, setup_database):
        """Assembly organiser can revoke roles on their own assembly."""
        data = setup_database
        grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.CONFIRMATION_CALLER,
            current_user=data["admin_user"],
        )

        result = revoke_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            current_user=data["assembly_organiser_user"],
        )

        assert isinstance(result, UserAssemblyRole)

    def test_regular_user_cannot_revoke_role(self, uow, setup_database):
        """Regular user cannot revoke roles."""
        data = setup_database
        grant_user_assembly_role(
            uow=uow,
            user_id=data["target_user"].id,
            assembly_id=data["assembly"].id,
            role=AssemblyRole.CONFIRMATION_CALLER,
            current_user=data["admin_user"],
        )

        with pytest.raises(InsufficientPermissions):
            revoke_user_assembly_role(
                uow=uow,
                user_id=data["target_user"].id,
                assembly_id=data["assembly"].id,
                current_user=data["regular_user"],
            )

    def test_user_cannot_revoke_role_on_assembly_they_dont_organise(self, uow, setup_database):
        """User cannot revoke roles on assembly they don't organise."""
        data = setup_database
        # Create another assembly
        other_assembly = Assembly(title="Other Assembly")
        with uow:
            uow.assemblies.add(other_assembly)
            # Add a user role on the other assembly
            other_role = UserAssemblyRole(
                user_id=data["target_user"].id,
                assembly_id=other_assembly.id,
                role=AssemblyRole.CONFIRMATION_CALLER,
            )
            uow.user_assembly_roles.add(other_role)
            uow.commit()

        with pytest.raises(InsufficientPermissions):
            revoke_user_assembly_role(
                uow=uow,
                user_id=data["target_user"].id,
                assembly_id=other_assembly.id,
                current_user=data["assembly_organiser_user"],
            )

    def test_revoke_role_when_target_user_does_not_exist(self, uow, setup_database):
        """Raises exception when target user doesn't exist."""
        data = setup_database
        nonexistent_user_id = uuid.uuid4()

        with pytest.raises(UserNotFoundError, match="User .* not found"):
            revoke_user_assembly_role(
                uow=uow,
                user_id=nonexistent_user_id,
                assembly_id=data["assembly"].id,
                current_user=data["admin_user"],
            )

    def test_revoke_role_when_assembly_does_not_exist(self, uow, setup_database):
        """Raises exception when assembly doesn't exist."""
        data = setup_database
        nonexistent_assembly_id = uuid.uuid4()

        with pytest.raises(AssemblyNotFoundError, match="Assembly .* not found"):
            revoke_user_assembly_role(
                uow=uow,
                user_id=data["target_user"].id,
                assembly_id=nonexistent_assembly_id,
                current_user=data["admin_user"],
            )

    def test_revoke_role_when_user_has_no_role_on_assembly(self, uow, setup_database):
        """Raises exception when user has no role on assembly to revoke."""
        data = setup_database
        with pytest.raises(NotFoundError, match="User .* has no role on assembly"):
            revoke_user_assembly_role(
                uow=uow,
                user_id=data["target_user"].id,
                assembly_id=data["assembly"].id,
                current_user=data["admin_user"],
            )
