"""ABOUTME: Integration tests for SQL-specific repository behaviour.
ABOUTME: Tests methods not in the abstract interface and cross-repository queries requiring real DB."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from opendlp.adapters.sql_repository import (
    SqlAlchemyAssemblyRepository,
    SqlAlchemyUserAssemblyRoleRepository,
    SqlAlchemyUserInviteRepository,
    SqlAlchemyUserRepository,
)
from opendlp.domain.assembly import Assembly
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole


@pytest.fixture
def user_repo(postgres_session):
    """Create a UserRepository."""
    return SqlAlchemyUserRepository(postgres_session)


@pytest.fixture
def assembly_repo(postgres_session):
    """Create an AssemblyRepository."""
    return SqlAlchemyAssemblyRepository(postgres_session)


@pytest.fixture
def invite_repo(postgres_session):
    """Create a UserInviteRepository."""
    return SqlAlchemyUserInviteRepository(postgres_session)


@pytest.fixture
def role_repo(postgres_session):
    """Create a UserAssemblyRoleRepository."""
    return SqlAlchemyUserAssemblyRoleRepository(postgres_session)


class TestUserRepository:
    """Tests for SQL-specific UserRepository methods not in the abstract interface."""

    def test_get_users_for_assembly(
        self,
        user_repo: SqlAlchemyUserRepository,
        assembly_repo: SqlAlchemyAssemblyRepository,
        role_repo: SqlAlchemyUserAssemblyRoleRepository,
        postgres_session: Session,
    ):
        """Test getting users who have roles in an assembly."""
        # Create users and assembly
        user1 = User(email="user1@example.com", global_role=GlobalRole.USER, password_hash="hash1")
        user2 = User(email="user2@example.com", global_role=GlobalRole.USER, password_hash="hash2")
        user3 = User(email="user3@example.com", global_role=GlobalRole.USER, password_hash="hash3")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly",
            question="Test question?",
            first_assembly_date=future_date,
        )

        user_repo.add(user1)
        user_repo.add(user2)
        user_repo.add(user3)
        assembly_repo.add(assembly)
        postgres_session.flush()

        # Assign roles to user1 and user2 only
        role1 = UserAssemblyRole(user_id=user1.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        role2 = UserAssemblyRole(user_id=user2.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)

        role_repo.add(role1)
        role_repo.add(role2)
        postgres_session.commit()

        # Get users for assembly
        users = list(user_repo.get_users_for_assembly(assembly.id))
        assert len(users) == 2
        emails = [u.email for u in users]
        assert "user1@example.com" in emails
        assert "user2@example.com" in emails
        assert "user3@example.com" not in emails

    def test_get_active_users(self, user_repo: SqlAlchemyUserRepository, postgres_session: Session):
        """Test getting only active users."""
        active_user = User(
            email="active@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
            is_active=True,
        )
        inactive_user = User(
            email="inactive@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
            is_active=False,
        )

        user_repo.add(active_user)
        user_repo.add(inactive_user)
        postgres_session.commit()

        active_users = list(user_repo.get_active_users())
        assert len(active_users) == 1
        assert active_users[0].email == "active@example.com"

    def test_get_admins(self, user_repo: SqlAlchemyUserRepository, postgres_session: Session):
        """Test getting users with admin privileges."""
        regular_user = User(email="regular@example.com", global_role=GlobalRole.USER, password_hash="hash")
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )

        user_repo.add(regular_user)
        user_repo.add(admin_user)
        user_repo.add(organiser_user)
        postgres_session.commit()

        admins = list(user_repo.get_admins())
        assert len(admins) == 2
        emails = [u.email for u in admins]
        assert "admin@example.com" in emails
        assert "organiser@example.com" in emails
        assert "regular@example.com" not in emails


class TestAssemblyRepository:
    """Tests for SQL-specific AssemblyRepository methods requiring cross-repo queries."""

    def test_get_assemblies_for_user_global_role(
        self,
        assembly_repo: SqlAlchemyAssemblyRepository,
        user_repo: SqlAlchemyUserRepository,
        postgres_session: Session,
    ):
        """Test getting assemblies for a user with global role."""
        future_date = date.today() + timedelta(days=30)

        # Create admin user
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        # Create assemblies
        assembly1 = Assembly(title="Assembly 1", question="Question 1?", first_assembly_date=future_date)
        assembly2 = Assembly(title="Assembly 2", question="Question 2?", first_assembly_date=future_date)

        user_repo.add(admin_user)
        assembly_repo.add(assembly1)
        assembly_repo.add(assembly2)
        postgres_session.commit()

        # Admin should see all active assemblies
        assemblies = list(assembly_repo.get_assemblies_for_user(admin_user.id))
        assert len(assemblies) == 2

    def test_get_assemblies_for_user_specific_role(
        self,
        assembly_repo: SqlAlchemyAssemblyRepository,
        user_repo: SqlAlchemyUserRepository,
        role_repo: SqlAlchemyUserAssemblyRoleRepository,
        postgres_session: Session,
    ):
        """Test getting assemblies for a user with specific assembly roles."""
        future_date = date.today() + timedelta(days=30)

        # Create regular user
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        # Create assemblies
        assembly1 = Assembly(title="Assembly 1", question="Question 1?", first_assembly_date=future_date)
        assembly2 = Assembly(title="Assembly 2", question="Question 2?", first_assembly_date=future_date)

        user_repo.add(user)
        assembly_repo.add(assembly1)
        assembly_repo.add(assembly2)
        postgres_session.flush()

        # Give user role in assembly1 only
        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly1.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        role_repo.add(role)
        postgres_session.commit()

        # User should only see assembly1
        assemblies = list(assembly_repo.get_assemblies_for_user(user.id))
        assert len(assemblies) == 1
        assert assemblies[0].title == "Assembly 1"


class TestUserInviteRepository:
    """Tests for SQL-specific UserInviteRepository methods not in the abstract interface."""

    def test_cleanup_expired_invites(
        self,
        invite_repo: SqlAlchemyUserInviteRepository,
        user_repo: SqlAlchemyUserRepository,
        postgres_session: Session,
    ):
        """Test cleanup of expired invites."""
        user = User(email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        user_repo.add(user)
        postgres_session.flush()

        # Create expired invite
        past_time = datetime.now(UTC) - timedelta(hours=2)
        expired_invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=user.id,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),
        )

        # Create valid invite
        valid_invite = UserInvite(global_role=GlobalRole.USER, created_by=user.id, expires_in_hours=24)

        invite_repo.add(expired_invite)
        invite_repo.add(valid_invite)
        postgres_session.commit()

        # Cleanup expired invites
        deleted_count = invite_repo.cleanup_expired_invites()
        assert deleted_count == 1
        postgres_session.commit()

        # Check that only valid invite remains
        remaining_invites = list(invite_repo.all())
        assert len(remaining_invites) == 1
        assert remaining_invites[0].id == valid_invite.id
