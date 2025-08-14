"""ABOUTME: Integration tests for ORM mapping and database operations
ABOUTME: Tests that domain objects can be saved, retrieved, and relationships work correctly"""

import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from opendlp.adapters import database, orm
from opendlp.config import get_postgres_uri
from opendlp.domain.assembly import Assembly
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole


@pytest.fixture
def db_engine():
    """Create a test database engine using PostgreSQL."""
    # For integration tests, use PostgreSQL with a test database name
    test_database_uri = get_postgres_uri(default_db_name="opendlp")

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


class TestUserORM:
    def test_save_and_retrieve_user(self, db_session: Session):
        """Test that User objects can be saved and retrieved."""
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed_password",
            first_name="Test",
            last_name="User",
        )

        # Save user
        db_session.add(user)
        db_session.commit()

        # Retrieve user
        retrieved_user = db_session.query(User).filter_by(email="test@example.com").first()

        assert retrieved_user is not None
        assert retrieved_user.email == "test@example.com"
        assert retrieved_user.first_name == "Test"
        assert retrieved_user.last_name == "User"
        assert retrieved_user.global_role == GlobalRole.USER
        assert retrieved_user.password_hash == "hashed_password"
        assert retrieved_user.is_active is True
        assert isinstance(retrieved_user.id, uuid.UUID)
        assert isinstance(retrieved_user.created_at, datetime)

    def test_user_oauth_fields(self, db_session: Session):
        """Test that OAuth fields are properly stored and retrieved."""
        user = User(
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="12345",
            first_name="OAuth",
            last_name="User",
        )

        db_session.add(user)
        db_session.commit()

        retrieved_user = db_session.query(User).filter_by(email="oauth@example.com").first()

        assert retrieved_user.oauth_provider == "google"
        assert retrieved_user.oauth_id == "12345"
        assert retrieved_user.password_hash is None

    def test_user_unique_constraints(self, db_session: Session):
        """Test that email unique constraints work."""
        user1 = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash1")

        db_session.add(user1)
        db_session.commit()

        # Try to create user with same email
        user2 = User(
            email="test@example.com",  # Same email
            global_role=GlobalRole.USER,
            password_hash="hash2",
        )

        db_session.add(user2)

        with pytest.raises(IntegrityError):  # Should raise integrity error
            db_session.commit()


class TestAssemblyORM:
    def test_save_and_retrieve_assembly(self, db_session: Session):
        """Test that Assembly objects can be saved and retrieved."""
        future_date = date.today() + timedelta(days=30)

        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        # Save assembly
        db_session.add(assembly)
        db_session.commit()

        # Retrieve assembly
        retrieved_assembly = db_session.query(Assembly).filter_by(title="Test Assembly").first()

        assert retrieved_assembly is not None
        assert retrieved_assembly.title == "Test Assembly"
        assert retrieved_assembly.question == "Test question?"
        assert retrieved_assembly.gsheet == "test-sheet"
        assert retrieved_assembly.first_assembly_date == future_date
        assert retrieved_assembly.status == AssemblyStatus.ACTIVE
        assert isinstance(retrieved_assembly.id, uuid.UUID)
        assert isinstance(retrieved_assembly.created_at, datetime)
        assert isinstance(retrieved_assembly.updated_at, datetime)

    def test_assembly_json_config(self, db_session: Session):
        """Test that JSON config field works properly."""
        future_date = date.today() + timedelta(days=30)

        # Create assembly with custom ID to set config
        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        db_session.add(assembly)
        db_session.flush()  # Flush to get ID but don't commit yet

        # Set JSON config directly on the mapped object
        db_session.execute(
            orm.assemblies.update()
            .where(orm.assemblies.c.id == assembly.id)
            .values(config={"sheet_tabs": ["main", "backup"], "columns": {"name": "A", "email": "B"}})
        )
        db_session.commit()

        # Retrieve and check JSON config
        result = db_session.execute(orm.assemblies.select().where(orm.assemblies.c.id == assembly.id)).first()

        assert result.config is not None
        assert result.config["sheet_tabs"] == ["main", "backup"]
        assert result.config["columns"]["name"] == "A"


class TestUserAssemblyRoleORM:
    def test_save_and_retrieve_user_assembly_role(self, db_session: Session):
        """Test that UserAssemblyRole objects can be saved and retrieved."""
        # Create user and assembly first
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        db_session.add(user)
        db_session.add(assembly)
        db_session.flush()  # Get IDs

        # Create role assignment
        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)

        db_session.add(role)
        db_session.commit()

        # Retrieve role
        retrieved_role = db_session.query(UserAssemblyRole).filter_by(user_id=user.id, assembly_id=assembly.id).first()

        assert retrieved_role is not None
        assert retrieved_role.user_id == user.id
        assert retrieved_role.assembly_id == assembly.id
        assert retrieved_role.role == AssemblyRole.ASSEMBLY_MANAGER
        assert isinstance(retrieved_role.id, uuid.UUID)
        assert isinstance(retrieved_role.created_at, datetime)

    def test_foreign_key_constraints(self, db_session: Session):
        """Test that foreign key constraints work properly."""
        # Try to create role without valid user/assembly
        invalid_role = UserAssemblyRole(
            user_id=uuid.uuid4(),  # Non-existent user
            assembly_id=uuid.uuid4(),  # Non-existent assembly
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )

        db_session.add(invalid_role)

        with pytest.raises(IntegrityError):  # Should raise foreign key constraint error
            db_session.commit()


class TestUserInviteORM:
    def test_save_and_retrieve_user_invite(self, db_session: Session):
        """Test that UserInvite objects can be saved and retrieved."""
        # Create user first
        user = User(email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        db_session.add(user)
        db_session.flush()  # Get user ID

        # Create invite
        invite = UserInvite(global_role=GlobalRole.USER, created_by=user.id, expires_in_hours=168)

        db_session.add(invite)
        db_session.commit()

        # Retrieve invite
        retrieved_invite = db_session.query(UserInvite).filter_by(created_by=user.id).first()

        assert retrieved_invite is not None
        assert retrieved_invite.global_role == GlobalRole.USER
        assert retrieved_invite.created_by == user.id
        assert isinstance(retrieved_invite.id, uuid.UUID)
        assert isinstance(retrieved_invite.code, str)
        assert len(retrieved_invite.code) == 12
        assert isinstance(retrieved_invite.created_at, datetime)
        assert isinstance(retrieved_invite.expires_at, datetime)
        assert retrieved_invite.used_by is None
        assert retrieved_invite.used_at is None

    def test_invite_code_unique_constraint(self, db_session: Session):
        """Test that invite codes are unique."""
        user = User(email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        db_session.add(user)
        db_session.flush()

        # Create first invite
        invite1 = UserInvite(global_role=GlobalRole.USER, created_by=user.id, code="TESTCODE123")

        db_session.add(invite1)
        db_session.commit()

        # Try to create second invite with same code
        invite2 = UserInvite(
            global_role=GlobalRole.USER,
            created_by=user.id,
            code="TESTCODE123",  # Same code
        )

        db_session.add(invite2)

        with pytest.raises(IntegrityError):  # Should raise unique constraint error
            db_session.commit()

    def test_invite_usage(self, db_session: Session):
        """Test that invite usage is properly tracked."""
        # Create creator and user
        creator = User(email="creator@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        invitee = User(email="invitee@example.com", global_role=GlobalRole.USER, password_hash="hash")

        db_session.add(creator)
        db_session.add(invitee)
        db_session.flush()

        # Create invite
        invite = UserInvite(global_role=GlobalRole.USER, created_by=creator.id)

        db_session.add(invite)
        db_session.flush()

        # Use invite (simulate using domain method)
        invite.use(invitee.id)
        db_session.commit()

        # Retrieve and verify
        retrieved_invite = db_session.query(UserInvite).filter_by(id=invite.id).first()

        assert retrieved_invite.used_by == invitee.id
        assert isinstance(retrieved_invite.used_at, datetime)


class TestRelationships:
    def test_cascade_delete_user_roles(self, db_session: Session):
        """Test that deleting a user cascades to their roles."""
        # Create user and assembly
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")

        future_date = date.today() + timedelta(days=30)
        assembly = Assembly(
            title="Test Assembly", question="Test question?", gsheet="test-sheet", first_assembly_date=future_date
        )

        db_session.add(user)
        db_session.add(assembly)
        db_session.flush()

        # Create role
        role = UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER)

        db_session.add(role)
        db_session.commit()

        # Verify role exists
        assert db_session.query(UserAssemblyRole).filter_by(user_id=user.id).count() == 1

        # Delete user
        db_session.delete(user)
        db_session.commit()

        # Verify role was cascade deleted
        assert db_session.query(UserAssemblyRole).filter_by(user_id=user.id).count() == 0

    def test_cascade_delete_invites(self, db_session: Session):
        """Test that deleting a user cascades to invites they created."""
        # Create admin user
        admin = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        db_session.add(admin)
        db_session.flush()

        # Create invite
        invite = UserInvite(global_role=GlobalRole.USER, created_by=admin.id)

        db_session.add(invite)
        db_session.commit()

        # Verify invite exists
        assert db_session.query(UserInvite).filter_by(created_by=admin.id).count() == 1

        # Delete admin
        db_session.delete(admin)
        db_session.commit()

        # Verify invite was cascade deleted
        assert db_session.query(UserInvite).filter_by(created_by=admin.id).count() == 0
