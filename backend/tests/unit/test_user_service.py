"""ABOUTME: Unit tests for user service layer operations
ABOUTME: Tests user creation, authentication, and invite validation with fake repositories"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer import user_service
from opendlp.service_layer.exceptions import InvalidCredentials, InvalidInvite, PasswordTooWeak, UserAlreadyExists
from opendlp.service_layer.security import hash_password
from tests.fakes import FakeUnitOfWork


class TestCreateUser:
    """Test user creation functionality."""

    def test_create_user_with_password_success(self):
        """Test successful user creation with password."""
        uow = FakeUnitOfWork()
        # Add a valid invite
        invite = UserInvite(
            code="TESTCODE",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        user = user_service.create_user(
            uow=uow, username="testuser", email="test@example.com", password="StrongPass123", invite_code="TESTCODE"
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.global_role == GlobalRole.USER
        assert user.password_hash is not None
        assert user.oauth_provider is None
        assert len(uow.users.list()) == 1
        assert uow.committed

    def test_create_user_with_oauth_success(self):
        """Test successful user creation with OAuth."""
        uow = FakeUnitOfWork()
        invite = UserInvite(
            code="TESTCODE",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        user = user_service.create_user(
            uow=uow,
            username="testuser",
            email="test@example.com",
            oauth_provider="google",
            oauth_id="google123",
            invite_code="TESTCODE",
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.global_role == GlobalRole.GLOBAL_ORGANISER
        assert user.password_hash is None
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"

    def test_create_user_username_already_exists(self):
        """Test user creation fails when username exists."""
        uow = FakeUnitOfWork()
        existing_user = User(
            username="testuser", email="other@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        uow.users.add(existing_user)

        with pytest.raises(UserAlreadyExists) as exc_info:
            user_service.create_user(uow=uow, username="testuser", email="test@example.com", password="StrongPass123")

        assert "testuser" in str(exc_info.value)

    def test_create_user_email_already_exists(self):
        """Test user creation fails when email exists."""
        uow = FakeUnitOfWork()
        existing_user = User(
            username="otheruser", email="test@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        uow.users.add(existing_user)

        with pytest.raises(UserAlreadyExists) as exc_info:
            user_service.create_user(uow=uow, username="testuser", email="test@example.com", password="StrongPass123")

        assert "test@example.com" in str(exc_info.value)

    def test_create_user_weak_password(self):
        """Test user creation fails with weak password."""
        uow = FakeUnitOfWork()

        with pytest.raises(PasswordTooWeak) as exc_info:
            user_service.create_user(uow=uow, username="testuser", email="test@example.com", password="weak")

        assert "Password must be at least 8 characters" in str(exc_info.value)

    def test_create_user_invalid_invite(self):
        """Test user creation fails with invalid invite."""
        uow = FakeUnitOfWork()

        with pytest.raises(InvalidInvite):
            user_service.create_user(
                uow=uow, username="testuser", email="test@example.com", password="StrongPass123", invite_code="INVALID"
            )


class TestAuthenticateUser:
    """Test user authentication functionality."""

    def test_authenticate_user_success_with_username(self):
        """Test successful authentication with username."""
        uow = FakeUnitOfWork()

        # Create user with known password hash
        password_hash = hash_password("correctpass")

        user = User(
            username="testuser", email="test@example.com", global_role=GlobalRole.USER, password_hash=password_hash
        )
        uow.users.add(user)

        result = user_service.authenticate_user(uow, "testuser", "correctpass")
        assert result == user

    def test_authenticate_user_success_with_email(self):
        """Test successful authentication with email."""
        uow = FakeUnitOfWork()

        password_hash = hash_password("correctpass")

        user = User(
            username="testuser", email="test@example.com", global_role=GlobalRole.USER, password_hash=password_hash
        )
        uow.users.add(user)

        result = user_service.authenticate_user(uow, "test@example.com", "correctpass")
        assert result == user

    def test_authenticate_user_not_found(self):
        """Test authentication fails when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(uow, "nonexistent", "password")

    def test_authenticate_user_wrong_password(self):
        """Test authentication fails with wrong password."""
        uow = FakeUnitOfWork()

        user = User(
            username="testuser",
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash=hash_password("correctpass"),
        )
        uow.users.add(user)

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(uow, "testuser", "wrongpass")

    def test_authenticate_user_inactive(self):
        """Test authentication fails for inactive user."""
        uow = FakeUnitOfWork()

        user = User(
            username="testuser",
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash=hash_password("password"),
            is_active=False,
        )
        uow.users.add(user)

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(uow, "testuser", "password")


class TestValidateAndUseInvite:
    """Test invite validation and usage functionality."""

    def test_validate_invite_success(self):
        """Test successful invite validation."""
        uow = FakeUnitOfWork()
        invite = UserInvite(
            code="TESTCODE",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        role = user_service.validate_and_use_invite(uow, "TESTCODE")

        assert role == GlobalRole.GLOBAL_ORGANISER

    def test_validate_invite_not_found(self):
        """Test invite validation fails when code not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.validate_and_use_invite(uow, "NOTFOUND")

        assert "not found" in str(exc_info.value)

    def test_validate_invite_expired(self):
        """Test invite validation fails when expired."""
        uow = FakeUnitOfWork()
        invite = UserInvite(
            code="EXPIRED",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # Expired
        )
        uow.user_invites.add(invite)

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.validate_and_use_invite(uow, "EXPIRED")

        assert "expired" in str(exc_info.value)

    def test_validate_invite_already_used(self):
        """Test invite validation fails when already used."""
        uow = FakeUnitOfWork()
        invite = UserInvite(
            code="USED",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        invite.use(uuid.uuid4())  # Mark as used
        uow.user_invites.add(invite)

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.validate_and_use_invite(uow, "USED")

        assert "already used" in str(exc_info.value)


class TestFindOrCreateOAuthUser:
    """Test OAuth user creation and linking."""

    def test_find_existing_oauth_user(self):
        """Test finding existing OAuth user."""
        uow = FakeUnitOfWork()
        existing_user = User(
            username="testuser",
            email="test@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="google123",
        )
        uow.users.add(existing_user)

        user, created = user_service.find_or_create_oauth_user(
            uow=uow, provider="google", oauth_id="google123", email="test@example.com", name="Test User"
        )

        assert user == existing_user
        assert not created

    def test_link_oauth_to_existing_email_user(self):
        """Test linking OAuth to user with same email."""
        uow = FakeUnitOfWork()

        existing_user = User(
            username="testuser", email="test@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        uow.users.add(existing_user)

        user, created = user_service.find_or_create_oauth_user(
            uow=uow, provider="google", oauth_id="google123", email="test@example.com", name="Test User"
        )

        assert user == existing_user
        assert not created
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"
        assert uow.committed

    def test_create_new_oauth_user(self):
        """Test creating new OAuth user."""
        uow = FakeUnitOfWork()

        # Add valid invite
        invite = UserInvite(
            code="TESTCODE",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        user, created = user_service.find_or_create_oauth_user(
            uow=uow,
            provider="google",
            oauth_id="google123",
            email="test@example.com",
            name="Test User",
            invite_code="TESTCODE",
        )

        assert created
        assert user.username == "test_user"
        assert user.email == "test@example.com"
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"

    def test_create_oauth_user_username_conflict(self):
        """Test creating OAuth user when username conflicts."""
        uow = FakeUnitOfWork()

        # Add conflicting user
        existing_user = User(
            username="test_user", email="other@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        uow.users.add(existing_user)

        # Add valid invite
        invite = UserInvite(
            code="TESTCODE",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        user, created = user_service.find_or_create_oauth_user(
            uow=uow,
            provider="google",
            oauth_id="google123",
            email="test@example.com",
            name="Test User",
            invite_code="TESTCODE",
        )

        assert created
        assert user.username == "test_user_1"


class TestGetUserAssemblies:
    """Test getting user's accessible assemblies."""

    def test_get_user_assemblies_admin(self):
        """Test admin user can see all active assemblies."""
        uow = FakeUnitOfWork()

        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )
        uow.users.add(admin_user)

        # Add some assemblies
        future_date = date.today() + timedelta(days=30)

        assembly1 = Assembly(
            title="Assembly 1",
            question="Question 1",
            gsheet="sheet1",
            first_assembly_date=future_date,
        )
        assembly2 = Assembly(
            title="Assembly 2",
            question="Question 2",
            gsheet="sheet2",
            first_assembly_date=future_date + timedelta(days=1),
        )
        uow.assemblies.add(assembly1)
        uow.assemblies.add(assembly2)

        assemblies = user_service.get_user_assemblies(uow, admin_user.id)

        assert len(assemblies) == 2

    def test_get_user_assemblies_user_not_found(self):
        """Test error when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(ValueError) as exc_info:
            user_service.get_user_assemblies(uow, uuid.uuid4())

        assert "not found" in str(exc_info.value)


class TestAssignAssemblyRole:
    """Test assigning assembly roles to users."""

    def test_assign_assembly_role_success(self):
        """Test successful role assignment."""
        uow = FakeUnitOfWork()

        user = User(username="testuser", email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)

        future_date = date.today() + timedelta(days=30)

        assembly = Assembly(
            title="Test Assembly",
            question="Test Question",
            gsheet="sheet1",
            first_assembly_date=future_date,
        )
        uow.assemblies.add(assembly)

        role = user_service.assign_assembly_role(
            uow=uow, user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.ASSEMBLY_MANAGER
        )

        assert role.user_id == user.id
        assert role.assembly_id == assembly.id
        assert role.role == AssemblyRole.ASSEMBLY_MANAGER
        assert len(user.assembly_roles) == 1
        assert uow.committed

    def test_assign_assembly_role_user_not_found(self):
        """Test error when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(ValueError) as exc_info:
            user_service.assign_assembly_role(
                uow=uow, user_id=uuid.uuid4(), assembly_id=uuid.uuid4(), role=AssemblyRole.ASSEMBLY_MANAGER
            )

        assert "User" in str(exc_info.value)
        assert "not found" in str(exc_info.value)
