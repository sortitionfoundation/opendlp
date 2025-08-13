"""ABOUTME: Integration tests for repository implementations
ABOUTME: Tests repository methods with actual database operations"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from opendlp.adapters import database, orm
from opendlp.adapters.sql_repository import (
    SqlAlchemyAssemblyRepository,
    SqlAlchemyUserAssemblyRoleRepository,
    SqlAlchemyUserInviteRepository,
    SqlAlchemyUserRepository,
)
from opendlp.config import get_postgres_uri
from opendlp.domain.assembly import Assembly
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole


@pytest.fixture
def db_engine():
    """Create a test database engine using PostgreSQL."""
    test_database_uri = get_postgres_uri(default_db_name="opendlp_test")

    # Create engine for test database
    engine = create_engine(test_database_uri, echo=False)

    # Create tables
    orm.metadata.create_all(engine)

    yield engine

    # Clean up - drop all tables
    orm.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Create a test database session."""
    # Start mappers
    database.start_mappers()

    # Create session
    Session = sessionmaker(bind=db_engine)
    session = Session()

    yield session

    session.rollback()
    session.close()


@pytest.fixture
def user_repo(db_session):
    """Create a UserRepository."""
    return SqlAlchemyUserRepository(db_session)


@pytest.fixture
def assembly_repo(db_session):
    """Create an AssemblyRepository."""
    return SqlAlchemyAssemblyRepository(db_session)


@pytest.fixture
def invite_repo(db_session):
    """Create a UserInviteRepository."""
    return SqlAlchemyUserInviteRepository(db_session)


@pytest.fixture
def role_repo(db_session):
    """Create a UserAssemblyRoleRepository."""
    return SqlAlchemyUserAssemblyRoleRepository(db_session)


class TestUserRepository:
    def test_add_and_get_user(self, user_repo: SqlAlchemyUserRepository, db_session: Session):
        """Test adding and retrieving a user."""
        user = User(
            username="testuser",
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash123",
        )

        user_repo.add(user)
        db_session.commit()

        # Test get by ID
        retrieved = user_repo.get(user.id)
        assert retrieved is not None
        assert retrieved.username == "testuser"
        assert retrieved.email == "test@example.com"

    def test_get_by_username(self, user_repo: SqlAlchemyUserRepository, db_session: Session):
        """Test retrieving user by username."""
        user = User(
            username="testuser",
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash123",
        )

        user_repo.add(user)
        db_session.commit()

        retrieved = user_repo.get_by_username("testuser")
        assert retrieved is not None
        assert retrieved.id == user.id

        # Test non-existent username
        assert user_repo.get_by_username("nonexistent") is None

    def test_get_by_email(self, user_repo: SqlAlchemyUserRepository, db_session: Session):
        """Test retrieving user by email."""
        user = User(
            username="testuser",
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash123",
        )

        user_repo.add(user)
        db_session.commit()

        retrieved = user_repo.get_by_email("test@example.com")
        assert retrieved is not None
        assert retrieved.id == user.id

        # Test non-existent email
        assert user_repo.get_by_email("nonexistent@example.com") is None

    def test_get_by_oauth_credentials(self, user_repo: SqlAlchemyUserRepository, db_session: Session):
        """Test retrieving user by OAuth credentials."""
        user = User(
            username="oauthuser",
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="12345",
        )

        user_repo.add(user)
        db_session.commit()

        retrieved = user_repo.get_by_oauth_credentials("google", "12345")
        assert retrieved is not None
        assert retrieved.id == user.id

        # Test non-existent credentials
        assert user_repo.get_by_oauth_credentials("google", "nonexistent") is None

    def test_list_users(self, user_repo: SqlAlchemyUserRepository, db_session: Session):
        """Test listing all users."""
        user1 = User(username="user1", email="user1@example.com", global_role=GlobalRole.USER, password_hash="hash1")
        user2 = User(username="user2", email="user2@example.com", global_role=GlobalRole.ADMIN, password_hash="hash2")

        user_repo.add(user1)
        user_repo.add(user2)
        db_session.commit()

        users = user_repo.list()
        assert len(users) == 2
        usernames = [u.username for u in users]
        assert "user1" in usernames
        assert "user2" in usernames

    def test_get_users_for_assembly(
        self,
        user_repo: SqlAlchemyUserRepository,
        assembly_repo: SqlAlchemyAssemblyRepository,
        role_repo: SqlAlchemyUserAssemblyRoleRepository,
        db_session: Session,
    ):
        """Test getting users who have roles in an assembly."""
        # Create users and assembly
        user1 = User(username="user1", email="user1@example.com", global_role=GlobalRole.USER, password_hash="hash1")
        user2 = User(username="user2", email="user2@example.com", global_role=GlobalRole.USER, password_hash="hash2")
        user3 = User(username="user3", email="user3@example.com", global_role=GlobalRole.USER, password_hash="hash3")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        user_repo.add(user1)
        user_repo.add(user2)
        user_repo.add(user3)
        assembly_repo.add(assembly)
        db_session.flush()

        # Assign roles to user1 and user2 only
        role1 = UserAssemblyRole(user_id=user1.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        role2 = UserAssemblyRole(user_id=user2.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)

        role_repo.add(role1)
        role_repo.add(role2)
        db_session.commit()

        # Get users for assembly
        users = user_repo.get_users_for_assembly(assembly.id)
        assert len(users) == 2
        usernames = [u.username for u in users]
        assert "user1" in usernames
        assert "user2" in usernames
        assert "user3" not in usernames

    def test_get_active_users(self, user_repo: SqlAlchemyUserRepository, db_session: Session):
        """Test getting only active users."""
        active_user = User(
            username="active",
            email="active@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
            is_active=True,
        )
        inactive_user = User(
            username="inactive",
            email="inactive@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
            is_active=False,
        )

        user_repo.add(active_user)
        user_repo.add(inactive_user)
        db_session.commit()

        active_users = user_repo.get_active_users()
        assert len(active_users) == 1
        assert active_users[0].username == "active"

    def test_get_admins(self, user_repo: SqlAlchemyUserRepository, db_session: Session):
        """Test getting users with admin privileges."""
        regular_user = User(
            username="regular", email="regular@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )
        organiser_user = User(
            username="organiser",
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )

        user_repo.add(regular_user)
        user_repo.add(admin_user)
        user_repo.add(organiser_user)
        db_session.commit()

        admins = user_repo.get_admins()
        assert len(admins) == 2
        usernames = [u.username for u in admins]
        assert "admin" in usernames
        assert "organiser" in usernames
        assert "regular" not in usernames


class TestAssemblyRepository:
    def test_add_and_get_assembly(self, assembly_repo: SqlAlchemyAssemblyRepository, db_session: Session):
        """Test adding and retrieving an assembly."""
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        assembly_repo.add(assembly)
        db_session.commit()

        retrieved = assembly_repo.get(assembly.id)
        assert retrieved is not None
        assert retrieved.title == "Test Assembly"

    def test_get_active_assemblies(self, assembly_repo: SqlAlchemyAssemblyRepository, db_session: Session):
        """Test getting active assemblies."""
        future_date = date.today() + timedelta(days=30)

        active_assembly = Assembly(
            title="Active Assembly",
            question="Active question?",
            gsheet="active-sheet",
            first_assembly_date=future_date,
            status=AssemblyStatus.ACTIVE,
        )
        archived_assembly = Assembly(
            title="Archived Assembly",
            question="Archived question?",
            gsheet="archived-sheet",
            first_assembly_date=future_date,
            status=AssemblyStatus.ARCHIVED,
        )

        assembly_repo.add(active_assembly)
        assembly_repo.add(archived_assembly)
        db_session.commit()

        active_assemblies = assembly_repo.get_active_assemblies()
        assert len(active_assemblies) == 1
        assert active_assemblies[0].title == "Active Assembly"

    def test_get_assemblies_for_user_global_role(
        self,
        assembly_repo: SqlAlchemyAssemblyRepository,
        user_repo: SqlAlchemyUserRepository,
        db_session: Session,
    ):
        """Test getting assemblies for a user with global role."""
        future_date = date.today() + timedelta(days=30)

        # Create admin user
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )

        # Create assemblies
        assembly1 = Assembly(
            title="Assembly 1", question="Question 1?", gsheet="sheet1", first_assembly_date=future_date
        )
        assembly2 = Assembly(
            title="Assembly 2", question="Question 2?", gsheet="sheet2", first_assembly_date=future_date
        )

        user_repo.add(admin_user)
        assembly_repo.add(assembly1)
        assembly_repo.add(assembly2)
        db_session.commit()

        # Admin should see all active assemblies
        assemblies = assembly_repo.get_assemblies_for_user(admin_user.id)
        assert len(assemblies) == 2

    def test_get_assemblies_for_user_specific_role(
        self,
        assembly_repo: SqlAlchemyAssemblyRepository,
        user_repo: SqlAlchemyUserRepository,
        role_repo: SqlAlchemyUserAssemblyRoleRepository,
        db_session: Session,
    ):
        """Test getting assemblies for a user with specific assembly roles."""
        future_date = date.today() + timedelta(days=30)

        # Create regular user
        user = User(username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        # Create assemblies
        assembly1 = Assembly(
            title="Assembly 1", question="Question 1?", gsheet="sheet1", first_assembly_date=future_date
        )
        assembly2 = Assembly(
            title="Assembly 2", question="Question 2?", gsheet="sheet2", first_assembly_date=future_date
        )

        user_repo.add(user)
        assembly_repo.add(assembly1)
        assembly_repo.add(assembly2)
        db_session.flush()

        # Give user role in assembly1 only
        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly1.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        role_repo.add(role)
        db_session.commit()

        # User should only see assembly1
        assemblies = assembly_repo.get_assemblies_for_user(user.id)
        assert len(assemblies) == 1
        assert assemblies[0].title == "Assembly 1"

    def test_search_by_title(self, assembly_repo: SqlAlchemyAssemblyRepository, db_session: Session):
        """Test searching assemblies by title."""
        future_date = date.today() + timedelta(days=30)

        assembly1 = Assembly(
            title="Climate Change Assembly",
            question="Climate question?",
            gsheet="sheet1",
            first_assembly_date=future_date,
        )
        assembly2 = Assembly(
            title="Healthcare Assembly",
            question="Healthcare question?",
            gsheet="sheet2",
            first_assembly_date=future_date,
        )
        assembly3 = Assembly(
            title="Education Policy Assembly",
            question="Education question?",
            gsheet="sheet3",
            first_assembly_date=future_date,
        )

        assembly_repo.add(assembly1)
        assembly_repo.add(assembly2)
        assembly_repo.add(assembly3)
        db_session.commit()

        # Search for "climate"
        results = assembly_repo.search_by_title("climate")
        assert len(results) == 1
        assert results[0].title == "Climate Change Assembly"

        # Search for "assembly" (should match all)
        results = assembly_repo.search_by_title("assembly")
        assert len(results) == 3

        # Case insensitive search
        results = assembly_repo.search_by_title("HEALTHCARE")
        assert len(results) == 1
        assert results[0].title == "Healthcare Assembly"


class TestUserInviteRepository:
    def test_add_and_get_invite(
        self, invite_repo: SqlAlchemyUserInviteRepository, user_repo: SqlAlchemyUserRepository, db_session: Session
    ):
        """Test adding and retrieving an invite."""
        # Create user first
        user = User(username="creator", email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        user_repo.add(user)
        db_session.flush()

        invite = UserInvite(global_role=GlobalRole.USER, created_by=user.id)
        invite_repo.add(invite)
        db_session.commit()

        retrieved = invite_repo.get(invite.id)
        assert retrieved is not None
        assert retrieved.global_role == GlobalRole.USER

    def test_get_by_code(
        self, invite_repo: SqlAlchemyUserInviteRepository, user_repo: SqlAlchemyUserRepository, db_session: Session
    ):
        """Test retrieving invite by code."""
        user = User(username="creator", email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        user_repo.add(user)
        db_session.flush()

        invite = UserInvite(global_role=GlobalRole.USER, created_by=user.id, code="TESTCODE123")
        invite_repo.add(invite)
        db_session.commit()

        retrieved = invite_repo.get_by_code("TESTCODE123")
        assert retrieved is not None
        assert retrieved.id == invite.id

        assert invite_repo.get_by_code("NONEXISTENT") is None

    def test_get_valid_invites(
        self, invite_repo: SqlAlchemyUserInviteRepository, user_repo: SqlAlchemyUserRepository, db_session: Session
    ):
        """Test getting valid invites."""
        user = User(username="creator", email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        user_repo.add(user)
        db_session.flush()

        # Create valid invite
        valid_invite = UserInvite(global_role=GlobalRole.USER, created_by=user.id, expires_in_hours=24)

        # Create expired invite
        past_time = datetime.now(UTC) - timedelta(hours=2)
        expired_invite = UserInvite(
            global_role=GlobalRole.USER,
            created_by=user.id,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),
        )

        # Create used invite
        used_invite = UserInvite(global_role=GlobalRole.USER, created_by=user.id, used_by=user.id)

        invite_repo.add(valid_invite)
        invite_repo.add(expired_invite)
        invite_repo.add(used_invite)
        db_session.commit()

        valid_invites = invite_repo.get_valid_invites()
        assert len(valid_invites) == 1
        assert valid_invites[0].id == valid_invite.id

    def test_get_expired_invites(
        self, invite_repo: SqlAlchemyUserInviteRepository, user_repo: SqlAlchemyUserRepository, db_session: Session
    ):
        """Test getting expired invites."""
        user = User(username="creator", email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        user_repo.add(user)
        db_session.flush()

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
        db_session.commit()

        expired_invites = invite_repo.get_expired_invites()
        assert len(expired_invites) == 1
        assert expired_invites[0].id == expired_invite.id

    def test_cleanup_expired_invites(
        self, invite_repo: SqlAlchemyUserInviteRepository, user_repo: SqlAlchemyUserRepository, db_session: Session
    ):
        """Test cleanup of expired invites."""
        user = User(username="creator", email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        user_repo.add(user)
        db_session.flush()

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
        db_session.commit()

        # Cleanup expired invites
        deleted_count = invite_repo.cleanup_expired_invites()
        assert deleted_count == 1
        db_session.commit()

        # Check that only valid invite remains
        remaining_invites = invite_repo.list()
        assert len(remaining_invites) == 1
        assert remaining_invites[0].id == valid_invite.id


class TestUserAssemblyRoleRepository:
    def test_add_and_get_role(
        self,
        role_repo: SqlAlchemyUserAssemblyRoleRepository,
        user_repo: SqlAlchemyUserRepository,
        assembly_repo: SqlAlchemyAssemblyRepository,
        db_session: Session,
    ):
        """Test adding and retrieving a role."""
        # Create user and assembly
        user = User(username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        user_repo.add(user)
        assembly_repo.add(assembly)
        db_session.flush()

        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        role_repo.add(role)
        db_session.commit()

        retrieved = role_repo.get(role.id)
        assert retrieved is not None
        assert retrieved.role == AssemblyRole.ASSEMBLY_MANAGER

    def test_get_by_user_and_assembly(
        self,
        role_repo: SqlAlchemyUserAssemblyRoleRepository,
        user_repo: SqlAlchemyUserRepository,
        assembly_repo: SqlAlchemyAssemblyRepository,
        db_session: Session,
    ):
        """Test getting role by user and assembly."""
        user = User(username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        user_repo.add(user)
        assembly_repo.add(assembly)
        db_session.flush()

        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        role_repo.add(role)
        db_session.commit()

        retrieved = role_repo.get_by_user_and_assembly(user.id, assembly.id)
        assert retrieved is not None
        assert retrieved.id == role.id

        # Test non-existent combination
        assert role_repo.get_by_user_and_assembly(uuid.uuid4(), assembly.id) is None

    def test_remove_role(
        self,
        role_repo: SqlAlchemyUserAssemblyRoleRepository,
        user_repo: SqlAlchemyUserRepository,
        assembly_repo: SqlAlchemyAssemblyRepository,
        db_session: Session,
    ):
        """Test removing a role."""
        user = User(username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        user_repo.add(user)
        assembly_repo.add(assembly)
        db_session.flush()

        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        role_repo.add(role)
        db_session.commit()

        # Remove role
        success = role_repo.remove_role(user.id, assembly.id)
        assert success is True
        db_session.commit()

        # Verify role is gone
        assert role_repo.get_by_user_and_assembly(user.id, assembly.id) is None

        # Try to remove non-existent role
        success = role_repo.remove_role(user.id, assembly.id)
        assert success is False
