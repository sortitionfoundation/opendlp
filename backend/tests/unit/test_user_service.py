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
from opendlp.service_layer.exceptions import (
    CannotRemoveLastAuthMethod,
    InsufficientPermissions,
    InvalidCredentials,
    InvalidInvite,
    PasswordTooWeak,
    UserAlreadyExists,
    UserNotFoundError,
)
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
        assert len(uow.users.all()) == 1
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
        existing_user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
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


class TestValidateInvite:
    """Test invite validation (without usage)."""

    def test_validate_invite_success(self):
        """Test successful invite validation returns correct role."""
        uow = FakeUnitOfWork()

        invite = UserInvite(
            code="VALIDCODE",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        role = user_service.validate_invite(uow=uow, invite_code="VALIDCODE")

        assert role == GlobalRole.GLOBAL_ORGANISER
        # Verify invite is NOT marked as used
        assert invite.used_by is None
        assert invite.used_at is None

    def test_validate_invite_not_found(self):
        """Test invite validation fails when code not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.validate_invite(uow=uow, invite_code="NOTFOUND")

        assert "not found" in str(exc_info.value).lower()


class TestUseInvite:
    """Test invite usage (marking as used)."""

    def test_use_invite_success(self):
        """Test successfully marking invite as used."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()

        invite = UserInvite(
            code="VALIDCODE",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        # Initially not used
        assert invite.used_by is None
        assert invite.used_at is None

        user_service.use_invite(uow=uow, invite_code="VALIDCODE", user_id=user_id)

        # Now should be marked as used
        assert invite.used_by == user_id
        assert invite.used_at is not None

    def test_use_invite_not_found(self):
        """Test using invite fails when code not found."""
        uow = FakeUnitOfWork()
        user_id = uuid.uuid4()

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.use_invite(uow=uow, invite_code="NOTFOUND", user_id=user_id)

        assert "not found" in str(exc_info.value).lower()

    def test_use_invite_already_used(self):
        """Test using invite fails when already used."""
        uow = FakeUnitOfWork()
        first_user_id = uuid.uuid4()
        second_user_id = uuid.uuid4()

        invite = UserInvite(
            code="USEDCODE",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
            used_by=first_user_id,
            used_at=datetime.now(UTC),
        )
        uow.user_invites.add(invite)

        with pytest.raises(ValueError) as exc_info:
            user_service.use_invite(uow=uow, invite_code="USEDCODE", user_id=second_user_id)

        assert "already been used" in str(exc_info.value).lower()


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
        existing_user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
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

        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Add some assemblies
        assembly1 = Assembly(
            title="Assembly 1",
            question="Question 1",
            first_assembly_date=date.today() + timedelta(days=1),
        )
        assembly2 = Assembly(
            title="Assembly 2",
            question="Question 2",
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

        with pytest.raises(UserNotFoundError, match=r"User .* not found"):
            user_service.get_user_assemblies(uow=uow, user_id=uuid.uuid4())


class TestAssignAssemblyRole:
    """Test assembly role assignment."""

    def test_assign_assembly_role_success(self):
        """Test successful role assignment."""
        uow = FakeUnitOfWork()

        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        assembly = Assembly(
            title="Test Assembly",
            question="Test Question",
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

        with pytest.raises(UserNotFoundError, match=r"User .* not found"):
            user_service.assign_assembly_role(
                uow=uow,
                user_id=uuid.uuid4(),
                assembly_id=uuid.uuid4(),
                role=AssemblyRole.ASSEMBLY_MANAGER,
            )


class TestListUsersPaginated:
    """Test paginated user listing."""

    def test_list_users_paginated_success(self):
        """Test successful paginated user listing."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Create regular users
        for i in range(25):
            user = User(
                email=f"user{i}@example.com",
                global_role=GlobalRole.USER,
                first_name=f"First{i}",
                last_name=f"Last{i}",
                password_hash="hash",  # pragma: allowlist secret
            )
            uow.users.add(user)

        # Get first page
        users, total_count, total_pages = user_service.list_users_paginated(
            uow=uow, admin_user_id=admin_user.id, page=1, per_page=10
        )

        assert len(users) == 10
        assert total_count == 26  # 25 + admin
        assert total_pages == 3  # ceil(26 / 10)

    def test_list_users_paginated_with_filters(self):
        """Test paginated listing with role and active filters."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Create mix of users
        uow.users.add(
            User(
                email="user1@example.com",
                global_role=GlobalRole.USER,
                is_active=True,
                password_hash="hash",  # pragma: allowlist secret
            )
        )
        uow.users.add(
            User(
                email="user2@example.com",
                global_role=GlobalRole.USER,
                is_active=False,
                password_hash="hash",  # pragma: allowlist secret
            )
        )
        uow.users.add(
            User(
                email="org1@example.com",
                global_role=GlobalRole.GLOBAL_ORGANISER,
                is_active=True,
                password_hash="hash",  # pragma: allowlist secret
            )
        )

        # Filter by active users only
        users, total_count, _total_pages = user_service.list_users_paginated(
            uow=uow, admin_user_id=admin_user.id, page=1, per_page=10, active_filter=True
        )

        assert total_count == 3  # admin, user1, org1
        assert all(u.is_active for u in users)

    def test_list_users_paginated_with_search(self):
        """Test paginated listing with search term."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Create users with searchable names
        uow.users.add(
            User(
                email="user1@example.com",
                global_role=GlobalRole.USER,
                first_name="Alice",
                last_name="Smith",
                password_hash="hash",  # pragma: allowlist secret
            )
        )
        uow.users.add(
            User(
                email="user2@example.com",
                global_role=GlobalRole.USER,
                first_name="Bob",
                last_name="Jones",
                password_hash="hash",  # pragma: allowlist secret
            )
        )
        uow.users.add(
            User(
                email="user3@example.com",
                global_role=GlobalRole.USER,
                first_name="Alice",
                last_name="Brown",
                password_hash="hash",  # pragma: allowlist secret
            )
        )

        # Search for "Alice"
        users, total_count, _total_pages = user_service.list_users_paginated(
            uow=uow, admin_user_id=admin_user.id, page=1, per_page=10, search_term="Alice"
        )

        assert total_count == 2
        assert all(u.first_name == "Alice" for u in users)

    def test_list_users_paginated_non_admin(self):
        """Test that non-admin users cannot list users."""
        uow = FakeUnitOfWork()

        # Create non-admin user
        regular_user = User(
            email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )  # pragma: allowlist secret
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            user_service.list_users_paginated(uow=uow, admin_user_id=regular_user.id, page=1, per_page=10)


class TestGetUserById:
    """Test getting user by ID."""

    def test_get_user_by_id_success(self):
        """Test successfully getting user by ID."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Create target user
        target_user = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            first_name="Target",
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(target_user)

        # Get user by ID
        user = user_service.get_user_by_id(uow=uow, user_id=target_user.id, admin_user_id=admin_user.id)

        assert user.email == "target@example.com"
        assert user.first_name == "Target"

    def test_get_user_by_id_not_found(self):
        """Test getting non-existent user."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        with pytest.raises(UserNotFoundError, match="not found"):
            user_service.get_user_by_id(uow=uow, user_id=uuid.uuid4(), admin_user_id=admin_user.id)

    def test_get_user_by_id_non_admin(self):
        """Test that non-admin users cannot get user details."""
        uow = FakeUnitOfWork()

        # Create non-admin user
        regular_user = User(
            email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )  # pragma: allowlist secret
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            user_service.get_user_by_id(uow=uow, user_id=regular_user.id, admin_user_id=regular_user.id)


class TestUpdateUser:
    """Test user update functionality."""

    def test_update_user_success(self):
        """Test successfully updating user."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Create target user
        target_user = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            first_name="Old",
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(target_user)

        # Update user
        updated_user = user_service.update_user(
            uow=uow,
            user_id=target_user.id,
            admin_user_id=admin_user.id,
            first_name="New",
            last_name="Name",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            is_active=False,
        )

        assert updated_user.first_name == "New"
        assert updated_user.last_name == "Name"
        assert updated_user.global_role == GlobalRole.GLOBAL_ORGANISER
        assert updated_user.is_active is False

    def test_update_user_cannot_change_own_role(self):
        """Test admin cannot change their own role."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Try to change own role
        with pytest.raises(ValueError, match="Cannot change your own admin role"):
            user_service.update_user(
                uow=uow,
                user_id=admin_user.id,
                admin_user_id=admin_user.id,
                global_role=GlobalRole.USER,
            )

    def test_update_user_cannot_deactivate_self(self):
        """Test admin cannot deactivate their own account."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Try to deactivate self
        with pytest.raises(ValueError, match="Cannot deactivate your own account"):
            user_service.update_user(
                uow=uow,
                user_id=admin_user.id,
                admin_user_id=admin_user.id,
                is_active=False,
            )

    def test_update_user_non_admin(self):
        """Test that non-admin users cannot update users."""
        uow = FakeUnitOfWork()

        # Create non-admin user
        regular_user = User(
            email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )  # pragma: allowlist secret
        target_user = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(regular_user)
        uow.users.add(target_user)

        with pytest.raises(InsufficientPermissions):
            user_service.update_user(
                uow=uow,
                user_id=target_user.id,
                admin_user_id=regular_user.id,
                first_name="Hacked",
            )


class TestGetUserStats:
    """Test user statistics."""

    def test_get_user_stats_success(self):
        """Test successfully getting user statistics."""
        uow = FakeUnitOfWork()

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        # Create mix of users
        uow.users.add(
            User(
                email="user1@example.com",
                global_role=GlobalRole.USER,
                is_active=True,
                password_hash="hash",  # pragma: allowlist secret
            )
        )
        uow.users.add(
            User(
                email="user2@example.com",
                global_role=GlobalRole.USER,
                is_active=False,
                password_hash="hash",  # pragma: allowlist secret
            )
        )
        uow.users.add(
            User(
                email="org1@example.com",
                global_role=GlobalRole.GLOBAL_ORGANISER,
                is_active=True,
                password_hash="hash",  # pragma: allowlist secret
            )
        )
        uow.users.add(
            User(
                email="admin2@example.com",
                global_role=GlobalRole.ADMIN,
                is_active=True,
                password_hash="hash",  # pragma: allowlist secret
            )
        )

        # Get stats
        stats = user_service.get_user_stats(uow=uow, admin_user_id=admin_user.id)

        assert stats["total_users"] == 5
        assert stats["active_users"] == 4
        assert stats["inactive_users"] == 1
        assert stats["admin_users"] == 2
        assert stats["organiser_users"] == 1
        assert stats["regular_users"] == 2

    def test_get_user_stats_non_admin(self):
        """Test that non-admin users cannot get statistics."""
        uow = FakeUnitOfWork()

        # Create non-admin user
        regular_user = User(
            email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )  # pragma: allowlist secret
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            user_service.get_user_stats(uow=uow, admin_user_id=regular_user.id)


class TestUpdateOwnProfile:
    """Test user updating their own profile."""

    def test_update_own_profile_success(self):
        """Test successfully updating own profile."""
        uow = FakeUnitOfWork()

        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)

        updated_user = user_service.update_own_profile(uow=uow, user_id=user.id, first_name="Updated", last_name="Name")

        assert updated_user.first_name == "Updated"
        assert updated_user.last_name == "Name"
        assert uow.committed

    def test_update_own_profile_partial_update(self):
        """Test updating only some fields."""
        uow = FakeUnitOfWork()

        user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
            first_name="Original",
            last_name="Name",
        )
        uow.users.add(user)

        updated_user = user_service.update_own_profile(uow=uow, user_id=user.id, first_name="NewFirst")

        assert updated_user.first_name == "NewFirst"
        assert updated_user.last_name == "Name"

    def test_update_own_profile_user_not_found(self):
        """Test error when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(UserNotFoundError, match=r"User .* not found"):
            user_service.update_own_profile(uow=uow, user_id=uuid.uuid4(), first_name="Test")


class TestChangeOwnPassword:
    """Test user changing their own password."""

    def test_change_own_password_success(self):
        """Test successfully changing password."""
        uow = FakeUnitOfWork()

        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash=hash_password("OldPass123"))
        uow.users.add(user)

        user_service.change_own_password(
            uow=uow, user_id=user.id, current_password="OldPass123", new_password="NewPass456!"
        )

        assert uow.committed
        # Verify the password was actually changed
        stored_user = uow.users.get(user.id)
        assert stored_user is not None
        assert stored_user.password_hash != hash_password("OldPass123")

    def test_change_own_password_wrong_current_password(self):
        """Test that wrong current password is rejected."""
        uow = FakeUnitOfWork()

        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash=hash_password("OldPass123"))
        uow.users.add(user)

        with pytest.raises(InvalidCredentials, match="Current password is incorrect"):
            user_service.change_own_password(
                uow=uow, user_id=user.id, current_password="WrongPassword", new_password="NewPass456!"
            )

    def test_change_own_password_weak_new_password(self):
        """Test that weak new password is rejected."""
        uow = FakeUnitOfWork()

        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash=hash_password("OldPass123"))
        uow.users.add(user)

        with pytest.raises(PasswordTooWeak):
            user_service.change_own_password(
                uow=uow, user_id=user.id, current_password="OldPass123", new_password="weak"
            )

    def test_change_own_password_user_not_found(self):
        """Test error when user not found."""
        uow = FakeUnitOfWork()

        with pytest.raises(UserNotFoundError, match=r"User .* not found"):
            user_service.change_own_password(
                uow=uow, user_id=uuid.uuid4(), current_password="test", new_password="NewPass456!"
            )

    def test_change_own_password_no_password_hash(self):
        """Test error when user has no password (OAuth user)."""
        uow = FakeUnitOfWork()

        user = User(email="user@example.com", global_role=GlobalRole.USER, oauth_provider="google", oauth_id="123")
        uow.users.add(user)

        with pytest.raises(InvalidCredentials):
            user_service.change_own_password(
                uow=uow, user_id=user.id, current_password="test", new_password="NewPass456!"
            )


class TestOAuthUserOperations:
    """Test OAuth user operations."""

    def test_find_or_create_oauth_user_new_user_requires_invite(self):
        """Test OAuth registration requires invite code."""
        uow = FakeUnitOfWork()

        with pytest.raises(InvalidInvite, match="Invite code required"):
            user_service.find_or_create_oauth_user(
                uow=uow, provider="google", oauth_id="google123", email="newuser@example.com", invite_code=None
            )

    def test_find_or_create_oauth_user_creates_new_user_with_invite(self, patch_password_hashing):
        """Test OAuth user creation with valid invite."""
        uow = FakeUnitOfWork()
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
            email="newuser@example.com",
            first_name="New",
            last_name="User",
            invite_code="TESTCODE",
            accept_data_agreement=True,
        )

        assert created is True
        assert user.email == "newuser@example.com"
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"
        assert user.password_hash is None
        assert user.first_name == "New"
        assert user.last_name == "User"

    def test_find_or_create_oauth_user_returns_existing_oauth_user(self):
        """Test finding existing OAuth user."""
        uow = FakeUnitOfWork()
        existing = User(
            email="existing@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="google123",
        )
        uow.users.add(existing)

        user, created = user_service.find_or_create_oauth_user(
            uow=uow, provider="google", oauth_id="google123", email="existing@example.com"
        )

        assert created is False
        assert user.id == existing.id
        assert user.email == "existing@example.com"

    def test_find_or_create_oauth_user_links_to_existing_email(self):
        """Test auto-linking OAuth to existing email account."""
        uow = FakeUnitOfWork()
        existing = User(email="existing@example.com", global_role=GlobalRole.USER, password_hash="hashed_password")
        uow.users.add(existing)

        user, created = user_service.find_or_create_oauth_user(
            uow=uow, provider="google", oauth_id="google123", email="existing@example.com"
        )

        assert created is False
        assert user.id == existing.id
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"
        assert user.password_hash == "hashed_password"  # pragma: allowlist secret

    def test_link_oauth_to_user_success(self):
        """Test linking OAuth to user account."""
        uow = FakeUnitOfWork()
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")
        uow.users.add(user)

        updated = user_service.link_oauth_to_user(
            uow=uow, user_id=user.id, provider="google", oauth_id="google123", oauth_email="user@example.com"
        )

        assert updated.oauth_provider == "google"
        assert updated.oauth_id == "google123"

    def test_link_oauth_to_user_email_mismatch(self):
        """Test OAuth linking fails on email mismatch."""
        uow = FakeUnitOfWork()
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")
        uow.users.add(user)

        with pytest.raises(ValueError, match="email does not match"):
            user_service.link_oauth_to_user(
                uow=uow, user_id=user.id, provider="google", oauth_id="google123", oauth_email="different@example.com"
            )

    def test_link_oauth_to_user_already_linked_to_another(self):
        """Test OAuth linking fails when OAuth already linked to different account."""
        uow = FakeUnitOfWork()
        user1 = User(
            email="user1@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed",  # pragma: allowlist secret
            oauth_provider="google",
            oauth_id="google123",
        )
        user2 = User(email="user2@example.com", global_role=GlobalRole.USER, password_hash="hashed")
        uow.users.add(user1)
        uow.users.add(user2)

        with pytest.raises(ValueError, match="already linked to another user"):
            user_service.link_oauth_to_user(
                uow=uow, user_id=user2.id, provider="google", oauth_id="google123", oauth_email="user2@example.com"
            )

    def test_remove_password_auth_success(self):
        """Test removing password when OAuth exists."""
        uow = FakeUnitOfWork()
        user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed",  # pragma: allowlist secret
            oauth_provider="google",
            oauth_id="google123",
        )
        uow.users.add(user)

        updated = user_service.remove_password_auth(uow=uow, user_id=user.id)

        assert updated.password_hash is None
        assert updated.oauth_provider == "google"

    def test_remove_password_auth_fails_without_oauth(self):
        """Test cannot remove password without OAuth."""
        uow = FakeUnitOfWork()
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")
        uow.users.add(user)

        with pytest.raises(CannotRemoveLastAuthMethod):
            user_service.remove_password_auth(uow=uow, user_id=user.id)

    def test_remove_oauth_auth_success(self):
        """Test removing OAuth when password exists."""
        uow = FakeUnitOfWork()
        user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed",  # pragma: allowlist secret
            oauth_provider="google",
            oauth_id="google123",
        )
        uow.users.add(user)

        updated = user_service.remove_oauth_auth(uow=uow, user_id=user.id)

        assert updated.oauth_provider is None
        assert updated.oauth_id is None
        assert updated.password_hash == "hashed"  # pragma: allowlist secret

    def test_remove_oauth_auth_fails_without_password(self):
        """Test cannot remove OAuth without password."""
        uow = FakeUnitOfWork()
        user = User(
            email="user@example.com", global_role=GlobalRole.USER, oauth_provider="google", oauth_id="google123"
        )
        uow.users.add(user)

        with pytest.raises(CannotRemoveLastAuthMethod):
            user_service.remove_oauth_auth(uow=uow, user_id=user.id)
