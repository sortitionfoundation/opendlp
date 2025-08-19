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
            uow=uow,
            email="test@example.com",
            password="StrongPass123",
            first_name="Test",
            last_name="User",
            invite_code="TESTCODE",
        )

        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
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
            email="test@example.com",
            first_name="OAuth",
            last_name="User",
            oauth_provider="google",
            oauth_id="google123",
            invite_code="TESTCODE",
        )

        assert user.email == "test@example.com"
        assert user.first_name == "OAuth"
        assert user.last_name == "User"
        assert user.global_role == GlobalRole.GLOBAL_ORGANISER
        assert user.password_hash is None
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"

    def test_create_user_email_already_exists(self):
        """Test user creation fails when email exists."""
        uow = FakeUnitOfWork()
        existing_user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(existing_user)

        with pytest.raises(UserAlreadyExists) as exc_info:
            user_service.create_user(
                uow=uow, email="test@example.com", password="StrongPass123", global_role=GlobalRole.USER
            )

        assert "test@example.com" in str(exc_info.value)

    @pytest.mark.parametrize(
        "password,msg",
        [
            ("weak", "must contain at least 9 characters"),
            ("123412341234", "password is entirely numeric"),
            ("test@example.com", "password is too similar to the email"),
            ("spongebob1", "password is too common"),
        ],
    )
    def test_create_user_weak_password(self, password, msg):
        """Test user creation fails with weak passwords."""
        uow = FakeUnitOfWork()

        with pytest.raises(PasswordTooWeak) as exc_info:
            user_service.create_user(uow=uow, email="test@example.com", password=password, global_role=GlobalRole.USER)

        assert msg in str(exc_info.value).lower()

    def test_create_user_invalid_invite(self):
        """Test user creation fails with invalid invite."""
        uow = FakeUnitOfWork()

        with pytest.raises(InvalidInvite):
            user_service.create_user(uow=uow, email="test@example.com", password="StrongPass123", invite_code="INVALID")


class TestAuthenticateUser:
    """Test user authentication functionality."""

    def test_authenticate_user_success_with_email(self):
        """Test successful authentication with email."""
        uow = FakeUnitOfWork()
        password_hash = hash_password("testpass")
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash=password_hash)
        uow.users.add(user)

        authenticated_user = user_service.authenticate_user(uow=uow, email="test@example.com", password="testpass")

        assert authenticated_user.email == "test@example.com"

    def test_authenticate_user_not_found(self):
        """Test authentication fails when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(uow=uow, email="nonexistent@example.com", password="testpass")

    def test_authenticate_user_wrong_password(self):
        """Test authentication fails with wrong password."""
        uow = FakeUnitOfWork()
        password_hash = hash_password("correctpass")
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash=password_hash)
        uow.users.add(user)

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(uow=uow, email="test@example.com", password="wrongpass")

    def test_authenticate_user_inactive(self):
        """Test authentication fails for inactive user."""
        uow = FakeUnitOfWork()
        password_hash = hash_password("testpass")
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash=password_hash, is_active=False)
        uow.users.add(user)

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(uow=uow, email="test@example.com", password="testpass")


class TestValidateAndUseInvite:
    """Test invite validation functionality."""

    def test_validate_invite_success(self):
        """Test successful invite validation."""
        uow = FakeUnitOfWork()
        invite = UserInvite(
            code="VALIDCODE",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        role = user_service.validate_and_use_invite(uow=uow, invite_code="VALIDCODE")

        assert role == GlobalRole.GLOBAL_ORGANISER

    def test_validate_invite_not_found(self):
        """Test invite validation fails when code not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.validate_and_use_invite(uow=uow, invite_code="NOTFOUND")

        assert "not found" in str(exc_info.value).lower()

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
            user_service.validate_and_use_invite(uow=uow, invite_code="EXPIRED")

        assert "expired" in str(exc_info.value).lower()

    def test_validate_invite_already_used(self):
        """Test invite validation fails when already used."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()
        invite = UserInvite(
            code="USED",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
            used_by=user_id,  # Already used
            used_at=datetime.now(UTC),
        )
        uow.user_invites.add(invite)

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.validate_and_use_invite(uow=uow, invite_code="USED")

        assert "already used" in str(exc_info.value).lower()


class TestFindOrCreateOAuthUser:
    """Test OAuth user find/create functionality."""

    def test_find_existing_oauth_user(self):
        """Test finding existing OAuth user."""
        uow = FakeUnitOfWork()
        existing_user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="google123",
            first_name="Existing",
            last_name="User",
        )
        uow.users.add(existing_user)

        user, created = user_service.find_or_create_oauth_user(
            uow=uow,
            provider="google",
            oauth_id="google123",
            email="test@example.com",
            first_name="Should",
            last_name="Ignore",
        )

        assert user == existing_user
        assert created is False

    def test_link_oauth_to_existing_email_user(self):
        """Test linking OAuth to existing email user."""
        uow = FakeUnitOfWork()
        existing_user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(existing_user)

        user, created = user_service.find_or_create_oauth_user(
            uow=uow,
            provider="google",
            oauth_id="google123",
            email="test@example.com",
            first_name="OAuth",
            last_name="User",
        )

        assert user == existing_user
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"
        assert created is False

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
            first_name="Test",
            last_name="User",
            invite_code="TESTCODE",
        )

        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"
        assert created is True


class TestGetUserAssemblies:
    """Test getting user assemblies."""

    def test_get_user_assemblies_admin(self):
        """Test admin user can see all active assemblies."""
        uow = FakeUnitOfWork()

        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin_user)

        # Add some assemblies
        assembly1 = Assembly(
            title="Assembly 1",
            question="Question 1",
            gsheet="sheet1",
            first_assembly_date=date.today() + timedelta(days=1),
        )
        assembly2 = Assembly(
            title="Assembly 2",
            question="Question 2",
            gsheet="sheet2",
            first_assembly_date=date.today() + timedelta(days=2),
        )
        uow.assemblies.add(assembly1)
        uow.assemblies.add(assembly2)

        assemblies = user_service.get_user_assemblies(uow=uow, user_id=admin_user.id)

        # Admin should see all active assemblies
        assert len(assemblies) == 2
        assert assembly1 in assemblies
        assert assembly2 in assemblies

    def test_get_user_assemblies_user_not_found(self):
        """Test error when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(ValueError, match="User .* not found"):
            user_service.get_user_assemblies(uow=uow, user_id=uuid.uuid4())


class TestAssignAssemblyRole:
    """Test assembly role assignment."""

    def test_assign_assembly_role_success(self):
        """Test successful role assignment."""
        uow = FakeUnitOfWork()

        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")
        assembly = Assembly(
            title="Test Assembly",
            question="Test Question",
            gsheet="sheet",
            first_assembly_date=date.today() + timedelta(days=1),
        )
        uow.users.add(user)
        uow.assemblies.add(assembly)

        role = user_service.assign_assembly_role(
            uow=uow,
            user_id=user.id,
            assembly_id=assembly.id,
            role=AssemblyRole.ASSEMBLY_MANAGER,
        )

        assert role.user_id == user.id
        assert role.assembly_id == assembly.id
        assert role.role == AssemblyRole.ASSEMBLY_MANAGER
        assert len(user.assembly_roles) == 1

    def test_assign_assembly_role_user_not_found(self):
        """Test role assignment fails when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(ValueError, match="User .* not found"):
            user_service.assign_assembly_role(
                uow=uow,
                user_id=uuid.uuid4(),
                assembly_id=uuid.uuid4(),
                role=AssemblyRole.ASSEMBLY_MANAGER,
            )
