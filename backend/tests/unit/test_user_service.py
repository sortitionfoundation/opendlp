"""ABOUTME: Unit tests for user service layer operations
ABOUTME: Tests user creation, authentication, and invite validation with fake repositories"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole
from opendlp.service_layer import user_service
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    CannotDisableSelf,
    CannotRemoveLastAuthMethod,
    InsufficientPermissions,
    InvalidCredentials,
    InvalidInvite,
    PasswordTooWeak,
    UserAlreadyExists,
    UserNotFoundError,
)
from opendlp.service_layer.security import hash_password, verify_password
from tests.fakes import FakeEmailAdapter, FakeTemplateRenderer, FakeURLGenerator


class TestCreateUser:
    """Test user creation functionality."""

    def test_create_user_with_password_success(self, uow):
        """Test successful user creation with password."""
        # Add a valid invite
        invite = UserInvite(
            code="TESTCODE",
            global_role=GlobalRole.USER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        user, token = user_service.create_user(
            uow=uow,
            email="test@example.com",
            password="StrongPass123",  # pragma: allowlist secret
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
        assert token is not None  # Password users should get a confirmation token
        assert len(uow.users.all()) == 1

    def test_create_user_with_oauth_success(self, uow):
        """Test successful user creation with OAuth."""
        invite = UserInvite(
            code="TESTCODE",
            global_role=GlobalRole.ORGANISER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        user, token = user_service.create_user(
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
        assert user.global_role == GlobalRole.ORGANISER
        assert user.password_hash is None
        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"
        assert token is None  # OAuth users should not get a confirmation token
        assert user.email_confirmed_at is not None  # OAuth users are auto-confirmed

    def test_create_user_email_already_exists(self, uow):
        """Test user creation fails when email exists."""
        existing_user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(existing_user)

        with pytest.raises(UserAlreadyExists) as exc_info:
            user_service.create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPass123",  # pragma: allowlist secret
                global_role=GlobalRole.USER,
            )

        assert "test@example.com" in str(exc_info.value)

    @pytest.mark.parametrize(
        ("password", "msg"),
        [
            ("weak", "must contain at least 10 characters"),
            ("123412341234", "password is entirely numeric"),
            ("test@example.com", "password is too similar to the email"),
            ("spongebob1", "password is too common"),
            ("a" * 258, "must not contain more than 256 characters"),
        ],
    )
    def test_create_user_weak_password(self, uow, password, msg):
        """Test user creation fails with weak passwords."""

        with pytest.raises(PasswordTooWeak) as exc_info:
            user_service.create_user(uow=uow, email="test@example.com", password=password, global_role=GlobalRole.USER)

        assert msg in str(exc_info.value).lower()

    def test_create_user_invalid_invite(self, uow):
        """Test user creation fails with invalid invite."""

        with pytest.raises(InvalidInvite):
            user_service.create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPass123",  # pragma: allowlist secret
                invite_code="INVALID",
            )


class TestAuthenticateUser:
    """Test user authentication functionality."""

    def test_authenticate_user_success_with_email(self, uow):
        """Test successful authentication with email."""
        password_hash = hash_password("testpass")
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash=password_hash,
            email_confirmed_at=datetime.now(UTC),
        )
        uow.users.add(user)

        authenticated_user = user_service.authenticate_user(uow=uow, email="test@example.com", password="testpass")

        assert authenticated_user.email == "test@example.com"

    def test_authenticate_user_not_found(self, uow):
        """Test authentication fails when user not found."""

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(
                uow=uow,
                email="nonexistent@example.com",
                password="testpass",  # pragma: allowlist secret
            )

    def test_authenticate_user_wrong_password(self, uow):
        """Test authentication fails with wrong password."""
        password_hash = hash_password("correctpass")
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash=password_hash)
        uow.users.add(user)

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(
                uow=uow,
                email="test@example.com",
                password="wrongpass",  # pragma: allowlist secret
            )

    def test_authenticate_user_inactive(self, uow):
        """Test authentication fails for inactive user."""
        password_hash = hash_password("testpass")
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash=password_hash, is_active=False)
        uow.users.add(user)

        with pytest.raises(InvalidCredentials):
            user_service.authenticate_user(
                uow=uow,
                email="test@example.com",
                password="testpass",  # pragma: allowlist secret
            )


class TestValidateInvite:
    """Test invite validation (without usage)."""

    def test_validate_invite_success(self, uow):
        """Test successful invite validation returns correct role."""

        invite = UserInvite(
            code="VALIDCODE",
            global_role=GlobalRole.ORGANISER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        role = user_service.validate_invite(uow=uow, invite_code="VALIDCODE")

        assert role == GlobalRole.ORGANISER
        # Verify invite is NOT marked as used
        assert invite.used_by is None
        assert invite.used_at is None

    def test_validate_invite_not_found(self, uow):
        """Test invite validation fails when code not found."""

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.validate_invite(uow=uow, invite_code="NOTFOUND")

        assert "not found" in str(exc_info.value).lower()


class TestUseInvite:
    """Test invite usage (marking as used)."""

    def test_use_invite_success(self, uow):
        """Test successfully marking invite as used."""
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

    def test_use_invite_not_found(self, uow):
        """Test using invite fails when code not found."""
        user_id = uuid.uuid4()

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.use_invite(uow=uow, invite_code="NOTFOUND", user_id=user_id)

        assert "not found" in str(exc_info.value).lower()

    def test_use_invite_already_used(self, uow):
        """Test using invite fails when already used."""
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

    def test_validate_invite_success(self, uow):
        """Test successful invite validation."""
        invite = UserInvite(
            code="VALIDCODE",
            global_role=GlobalRole.ORGANISER,
            created_by=uuid.uuid4(),
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)

        role = user_service.validate_and_use_invite(uow=uow, invite_code="VALIDCODE")

        assert role == GlobalRole.ORGANISER

    def test_validate_invite_not_found(self, uow):
        """Test invite validation fails when code not found."""

        with pytest.raises(InvalidInvite) as exc_info:
            user_service.validate_and_use_invite(uow=uow, invite_code="NOTFOUND")

        assert "not found" in str(exc_info.value).lower()

    def test_validate_invite_expired(self, uow):
        """Test invite validation fails when expired."""
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

    def test_validate_invite_already_used(self, uow):
        """Test invite validation fails when already used."""
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

    def test_find_existing_oauth_user(self, uow):
        """Test finding existing OAuth user."""
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

    def test_link_oauth_to_existing_email_user(self, uow):
        """Test linking OAuth to existing email user."""
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

    def test_create_new_oauth_user(self, uow):
        """Test creating new OAuth user."""

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

    def test_get_user_assemblies_admin(self, uow):
        """Test admin user can see all active assemblies."""

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

    def test_get_user_assemblies_organiser_sees_only_their_own(self, uow):
        """An organiser's dashboard lists what they hold a role on, not every assembly."""
        organiser = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(organiser)

        theirs = Assembly(title="Theirs", question="?")
        someone_elses = Assembly(title="Someone else's", question="?")
        uow.assemblies.add(theirs)
        uow.assemblies.add(someone_elses)
        organiser.assembly_roles.append(
            UserAssemblyRole(user_id=organiser.id, assembly_id=theirs.id, role=AssemblyRole.ASSEMBLY_MANAGER)
        )

        assemblies = user_service.get_user_assemblies(uow=uow, user_id=organiser.id)

        assert [a.title for a in assemblies] == ["Theirs"]

    def test_get_user_assemblies_organiser_with_no_roles_sees_nothing(self, uow):
        organiser = User(
            email="organiser@example.com",
            global_role=GlobalRole.ORGANISER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(organiser)
        uow.assemblies.add(Assembly(title="Someone else's", question="?"))

        assert user_service.get_user_assemblies(uow=uow, user_id=organiser.id) == []

    def test_get_user_assemblies_user_not_found(self, uow):
        """Test error when user not found."""

        with pytest.raises(UserNotFoundError, match=r"User .* not found"):
            user_service.get_user_assemblies(uow=uow, user_id=uuid.uuid4())


class TestAssignAssemblyRole:
    """Test assembly role assignment."""

    def test_assign_assembly_role_success(self, uow):
        """Test successful role assignment."""

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

    def test_assign_assembly_role_user_not_found(self, uow):
        """Test role assignment fails when user not found."""

        with pytest.raises(UserNotFoundError, match=r"User .* not found"):
            user_service.assign_assembly_role(
                uow=uow,
                user_id=uuid.uuid4(),
                assembly_id=uuid.uuid4(),
                role=AssemblyRole.ASSEMBLY_MANAGER,
            )


class TestListUsersPaginated:
    """Test paginated user listing."""

    def test_list_users_paginated_success(self, uow):
        """Test successful paginated user listing."""

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

    def test_list_users_paginated_with_filters(self, uow):
        """Test paginated listing with role and active filters."""

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
                global_role=GlobalRole.ORGANISER,
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

    def test_list_users_paginated_with_search(self, uow):
        """Test paginated listing with search term."""

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

    def test_list_users_paginated_non_admin(self, uow):
        """Test that non-admin users cannot list users."""

        # Create non-admin user
        regular_user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            user_service.list_users_paginated(uow=uow, admin_user_id=regular_user.id, page=1, per_page=10)


class TestGetUserById:
    """Test getting user by ID."""

    def test_get_user_by_id_success(self, uow):
        """Test successfully getting user by ID."""

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

    def test_get_user_by_id_not_found(self, uow):
        """Test getting non-existent user."""

        # Create admin user
        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin_user)

        with pytest.raises(UserNotFoundError, match="not found"):
            user_service.get_user_by_id(uow=uow, user_id=uuid.uuid4(), admin_user_id=admin_user.id)

    def test_get_user_by_id_non_admin(self, uow):
        """Test that non-admin users cannot get user details."""

        # Create non-admin user
        regular_user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            user_service.get_user_by_id(uow=uow, user_id=regular_user.id, admin_user_id=regular_user.id)


class TestUpdateUser:
    """Test user update functionality."""

    def test_update_user_success(self, uow):
        """Test successfully updating user."""

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
            global_role=GlobalRole.ORGANISER,
        )

        assert updated_user.first_name == "New"
        assert updated_user.last_name == "Name"
        assert updated_user.global_role == GlobalRole.ORGANISER

    def test_update_user_cannot_change_own_role(self, uow):
        """Test admin cannot change their own role."""

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

    def test_update_user_does_not_change_whether_the_account_is_active(self, uow):
        """Enabling and disabling is disable_user/enable_user's job, not this one's."""

        admin_user = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        target_user = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
            is_active=False,
        )
        uow.users.add(admin_user)
        uow.users.add(target_user)

        updated_user = user_service.update_user(
            uow=uow,
            user_id=target_user.id,
            admin_user_id=admin_user.id,
            first_name="New",
        )

        assert updated_user.is_active is False

    def test_update_user_non_admin(self, uow):
        """Test that non-admin users cannot update users."""

        # Create non-admin user
        regular_user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
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

    def test_get_user_stats_success(self, uow):
        """Test successfully getting user statistics."""

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
                global_role=GlobalRole.ORGANISER,
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

    def test_get_user_stats_non_admin(self, uow):
        """Test that non-admin users cannot get statistics."""

        # Create non-admin user
        regular_user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            user_service.get_user_stats(uow=uow, admin_user_id=regular_user.id)


class TestUpdateOwnProfile:
    """Test user updating their own profile."""

    def test_update_own_profile_success(self, uow):
        """Test successfully updating own profile."""

        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(user)

        updated_user = user_service.update_own_profile(uow=uow, user_id=user.id, first_name="Updated", last_name="Name")

        assert updated_user.first_name == "Updated"
        assert updated_user.last_name == "Name"

    def test_update_own_profile_partial_update(self, uow):
        """Test updating only some fields."""

        user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
            first_name="Original",
            last_name="Name",
        )
        uow.users.add(user)

        updated_user = user_service.update_own_profile(uow=uow, user_id=user.id, first_name="NewFirst")

        assert updated_user.first_name == "NewFirst"
        assert updated_user.last_name == "Name"

    def test_update_own_profile_user_not_found(self, uow):
        """Test error when user not found."""

        with pytest.raises(UserNotFoundError, match=r"User .* not found"):
            user_service.update_own_profile(uow=uow, user_id=uuid.uuid4(), first_name="Test")


class TestChangeOwnPassword:
    """Test user changing their own password."""

    def test_change_own_password_success(self, uow):
        """Test successfully changing password."""

        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash=hash_password("OldPass123"))
        uow.users.add(user)

        user_service.change_own_password(
            uow=uow, user_id=user.id, current_password="OldPass123", new_password="NewPass456!"
        )

        # Verify the password was actually changed
        stored_user = uow.users.get(user.id)
        assert stored_user is not None
        assert stored_user.password_hash != hash_password("OldPass123")

    def test_change_own_password_wrong_current_password(self, uow):
        """Test that wrong current password is rejected."""

        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash=hash_password("OldPass123"))
        uow.users.add(user)

        with pytest.raises(InvalidCredentials, match="Current password is incorrect"):
            user_service.change_own_password(
                uow=uow, user_id=user.id, current_password="WrongPassword", new_password="NewPass456!"
            )

    def test_change_own_password_weak_new_password(self, uow):
        """Test that weak new password is rejected."""

        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash=hash_password("OldPass123"))
        uow.users.add(user)

        with pytest.raises(PasswordTooWeak):
            user_service.change_own_password(
                uow=uow, user_id=user.id, current_password="OldPass123", new_password="weak"
            )

    def test_change_own_password_user_not_found(self, uow):
        """Test error when user not found."""

        with pytest.raises(UserNotFoundError, match=r"User .* not found"):
            user_service.change_own_password(
                uow=uow, user_id=uuid.uuid4(), current_password="test", new_password="NewPass456!"
            )

    def test_change_own_password_no_password_hash(self, uow):
        """Test error when user has no password (OAuth user)."""

        user = User(email="user@example.com", global_role=GlobalRole.USER, oauth_provider="google", oauth_id="123")
        uow.users.add(user)

        with pytest.raises(InvalidCredentials):
            user_service.change_own_password(
                uow=uow, user_id=user.id, current_password="test", new_password="NewPass456!"
            )


class TestOAuthUserOperations:
    """Test OAuth user operations."""

    def test_find_or_create_oauth_user_new_user_requires_invite(self, uow):
        """Test OAuth registration requires invite code."""

        with pytest.raises(InvalidInvite, match="Invite code required"):
            user_service.find_or_create_oauth_user(
                uow=uow, provider="google", oauth_id="google123", email="newuser@example.com", invite_code=None
            )

    def test_find_or_create_oauth_user_creates_new_user_with_invite(self, uow, patch_password_hashing):
        """Test OAuth user creation with valid invite."""
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

    def test_find_or_create_oauth_user_returns_existing_oauth_user(self, uow):
        """Test finding existing OAuth user."""
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

    def test_find_or_create_oauth_user_links_to_existing_email(self, uow):
        """Test auto-linking OAuth to existing email account."""
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

    def test_link_oauth_to_user_success(self, uow):
        """Test linking OAuth to user account."""
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")
        uow.users.add(user)

        updated = user_service.link_oauth_to_user(
            uow=uow, user_id=user.id, provider="google", oauth_id="google123", oauth_email="user@example.com"
        )

        assert updated.oauth_provider == "google"
        assert updated.oauth_id == "google123"

    def test_link_oauth_to_user_email_mismatch(self, uow):
        """Test OAuth linking fails on email mismatch."""
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")
        uow.users.add(user)

        with pytest.raises(ValueError, match="email does not match"):
            user_service.link_oauth_to_user(
                uow=uow, user_id=user.id, provider="google", oauth_id="google123", oauth_email="different@example.com"
            )

    def test_link_oauth_to_user_already_linked_to_another(self, uow):
        """Test OAuth linking fails when OAuth already linked to different account."""
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

    def test_remove_password_auth_success(self, uow):
        """Test removing password when OAuth exists."""
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

    def test_remove_password_auth_fails_without_oauth(self, uow):
        """Test cannot remove password without OAuth."""
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")
        uow.users.add(user)

        with pytest.raises(CannotRemoveLastAuthMethod):
            user_service.remove_password_auth(uow=uow, user_id=user.id)

    def test_remove_oauth_auth_success(self, uow):
        """Test removing OAuth when password exists."""
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

    def test_remove_oauth_auth_fails_without_password(self, uow):
        """Test cannot remove OAuth without password."""
        user = User(
            email="user@example.com", global_role=GlobalRole.USER, oauth_provider="google", oauth_id="google123"
        )
        uow.users.add(user)

        with pytest.raises(CannotRemoveLastAuthMethod):
            user_service.remove_oauth_auth(uow=uow, user_id=user.id)

    def test_remove_oauth_auth_fails_with_only_a_password_the_lockout_destroyed(self, uow):
        """A hash they cannot sign in with is not the auth method that survives unlinking."""
        user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed",  # pragma: allowlist secret
            oauth_provider="google",
            oauth_id="google123",
        )
        user.set_unusable_password()
        uow.users.add(user)

        with pytest.raises(CannotRemoveLastAuthMethod):
            user_service.remove_oauth_auth(uow=uow, user_id=user.id)


class TestDisableUser:
    """Locking a user out has to take away every route back in at once."""

    @pytest.fixture
    def admin_user(self, uow):
        admin = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin)
        return admin

    @pytest.fixture
    def target_user(self, uow):
        target = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            password_hash=hash_password("OriginalPassw0rd!"),
        )
        uow.users.add(target)
        return target

    def test_disabling_clears_the_active_flag(self, uow, admin_user, target_user):
        disabled = user_service.disable_user(uow, target_user.id, admin_user.id)

        assert disabled.is_active is False

    def test_disabling_ends_every_existing_session(self, uow, admin_user, target_user):
        old_session_id = target_user.get_id()

        disabled = user_service.disable_user(uow, target_user.id, admin_user.id)

        assert disabled.sessions_invalidated_at is not None
        assert disabled.get_id() != old_session_id

    def test_disabling_makes_the_password_unusable(self, uow, admin_user, target_user):
        disabled = user_service.disable_user(uow, target_user.id, admin_user.id)

        assert disabled.has_usable_password() is False
        assert verify_password("OriginalPassw0rd!", disabled.password_hash) is False

    def test_disabling_invalidates_outstanding_reset_and_confirmation_tokens(self, uow, admin_user, target_user):
        reset_token = PasswordResetToken(user_id=target_user.id)
        confirmation_token = EmailConfirmationToken(user_id=target_user.id)
        uow.password_reset_tokens.add(reset_token)
        uow.email_confirmation_tokens.add(confirmation_token)

        user_service.disable_user(uow, target_user.id, admin_user.id)

        assert reset_token.is_valid() is False
        assert confirmation_token.is_valid() is False

    def test_disabling_clears_2fa(self, uow, admin_user, target_user):
        target_user.enable_totp("encrypted-secret")

        disabled = user_service.disable_user(uow, target_user.id, admin_user.id)

        assert disabled.totp_enabled is False
        assert disabled.totp_secret_encrypted is None

    def test_disabling_a_user_without_2fa_does_not_raise(self, uow, admin_user, target_user):
        # clear_2fa_for_lockout is a no-op when there is no enrolment to clear
        disabled = user_service.disable_user(uow, target_user.id, admin_user.id)

        assert disabled.totp_enabled is False

    def test_disabling_an_oauth_user_does_not_raise(self, uow, admin_user):
        oauth_user = User(
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="google123",
        )
        uow.users.add(oauth_user)

        disabled = user_service.disable_user(uow, oauth_user.id, admin_user.id)

        assert disabled.is_active is False
        assert disabled.oauth_provider == "google"

    def test_disabling_clears_2fa_for_an_oauth_user_too(self, uow, admin_user):
        """requires_2fa ignores TOTP once OAuth is linked, so the secret would sit there
        dormant until someone unlinked OAuth and woke the attacker's authenticator up."""
        # Only reachable in this order: enable_totp refuses an account that already
        # has OAuth, but linking OAuth to a 2FA account is not guarded.
        user = User(
            email="both@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        user.enable_totp("encrypted-secret")
        user.add_oauth_credentials("google", "google123")
        uow.users.add(user)

        disabled = user_service.disable_user(uow, user.id, admin_user.id)

        assert disabled.totp_enabled is False
        assert disabled.totp_secret_encrypted is None

    def test_an_admin_cannot_disable_themselves(self, uow, admin_user):
        with pytest.raises(CannotDisableSelf):
            user_service.disable_user(uow, admin_user.id, admin_user.id)

        assert admin_user.is_active is True

    def test_disabling_an_already_disabled_user_changes_nothing(self, uow, admin_user, target_user):
        first = user_service.disable_user(uow, target_user.id, admin_user.id)

        second = user_service.disable_user(uow, target_user.id, admin_user.id)

        assert second.sessions_invalidated_at == first.sessions_invalidated_at
        assert second.password_hash == first.password_hash

    def test_a_non_admin_cannot_disable_anyone(self, uow, target_user):
        regular_user = User(
            email="regular@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            user_service.disable_user(uow, target_user.id, regular_user.id)

    def test_disabling_an_unknown_user_raises(self, uow, admin_user):
        with pytest.raises(UserNotFoundError):
            user_service.disable_user(uow, uuid.uuid4(), admin_user.id)

    def test_the_lockout_is_logged_for_a_sysadmin_to_find(self, uow, admin_user, target_user, caplog):
        user_service.disable_user(uow, target_user.id, admin_user.id)

        assert "user.disabled" in caplog.text
        assert str(target_user.id) in caplog.text
        assert str(admin_user.id) in caplog.text
        # censor_pii redacts any field whose name contains "password", so the
        # field naming has to avoid it or the log says nothing useful
        assert "credentials_reset" in caplog.text
        assert "[REDACTED]" not in caplog.text
        # Never the email address - see docs/personal-data.md
        assert "target@example.com" not in caplog.text

    def test_usable_invites_the_user_created_are_logged(self, uow, admin_user, target_user, caplog):
        uow.user_invites.add(
            UserInvite(
                code="STILLGOOD",
                global_role=GlobalRole.USER,
                created_by=target_user.id,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
        )

        user_service.disable_user(uow, target_user.id, admin_user.id)

        assert "user.disabled.outstanding_invites" in caplog.text
        # The code is a credential and must never reach the logs
        assert "STILLGOOD" not in caplog.text

    def test_expired_invites_the_user_created_are_not_logged(self, uow, admin_user, target_user, caplog):
        uow.user_invites.add(
            UserInvite(
                code="EXPIRED",
                global_role=GlobalRole.USER,
                created_by=target_user.id,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )

        user_service.disable_user(uow, target_user.id, admin_user.id)

        assert "user.disabled.outstanding_invites" not in caplog.text


class TestEnableUser:
    """Re-enabling gets the user back in, but must not resurrect the old sessions."""

    @pytest.fixture
    def admin_user(self, uow):
        admin = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin)
        return admin

    @pytest.fixture
    def disabled_user(self, uow, admin_user):
        target = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            password_hash=hash_password("OriginalPassw0rd!"),
        )
        uow.users.add(target)
        user_service.disable_user(uow, target.id, admin_user.id)
        return target

    def test_enabling_sets_the_active_flag(self, uow, admin_user, disabled_user):
        enabled = user_service.enable_user(uow, disabled_user.id, admin_user.id)

        assert enabled.is_active is True

    def test_enabling_leaves_the_cancelled_sessions_cancelled(self, uow, admin_user, disabled_user):
        session_id_while_disabled = disabled_user.get_id()

        enabled = user_service.enable_user(uow, disabled_user.id, admin_user.id)

        assert enabled.get_id() == session_id_while_disabled

    def test_enabling_does_not_restore_the_password(self, uow, admin_user, disabled_user):
        enabled = user_service.enable_user(uow, disabled_user.id, admin_user.id)

        assert enabled.has_usable_password() is False

    def test_enabling_an_active_user_changes_nothing(self, uow, admin_user, disabled_user):
        user_service.enable_user(uow, disabled_user.id, admin_user.id)

        enabled_again = user_service.enable_user(uow, disabled_user.id, admin_user.id)

        assert enabled_again.is_active is True

    def test_a_non_admin_cannot_enable_anyone(self, uow, disabled_user):
        regular_user = User(
            email="regular@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(regular_user)

        with pytest.raises(InsufficientPermissions):
            user_service.enable_user(uow, disabled_user.id, regular_user.id)

    def test_enabling_an_unknown_user_raises(self, uow, admin_user):
        with pytest.raises(UserNotFoundError):
            user_service.enable_user(uow, uuid.uuid4(), admin_user.id)


class TestTotpClearedByLockout:
    """The re-enable email needs to know whether it should mention 2FA."""

    @pytest.fixture
    def admin_user(self, uow):
        admin = User(
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(admin)
        return admin

    def test_true_when_the_lockout_cleared_2fa(self, uow, admin_user):
        target = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        target.enable_totp("encrypted-secret")
        uow.users.add(target)
        user_service.disable_user(uow, target.id, admin_user.id)

        assert user_service.totp_cleared_by_lockout(uow, target) is True

    def test_false_when_the_user_never_had_2fa(self, uow, admin_user):
        target = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(target)
        user_service.disable_user(uow, target.id, admin_user.id)

        assert user_service.totp_cleared_by_lockout(uow, target) is False

    def test_false_when_the_user_has_never_been_locked_out(self, uow):
        target = User(
            email="target@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(target)

        assert user_service.totp_cleared_by_lockout(uow, target) is False


class TestSendAccountReenabledEmail:
    """Telling the user their account is back, and how they get in."""

    @pytest.fixture
    def email_adapter(self):
        return FakeEmailAdapter()

    def _send(self, email_adapter, user, totp_cleared=False):
        return user_service.send_account_reenabled_email(
            email_adapter=email_adapter,
            template_renderer=FakeTemplateRenderer(),
            url_generator=FakeURLGenerator(),
            user=user,
            totp_cleared=totp_cleared,
        )

    def test_a_user_with_an_address_is_emailed(self, email_adapter):
        user = User(
            email="back@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )

        assert self._send(email_adapter, user) is True
        assert email_adapter.sent[0]["to"] == ["back@example.com"]

    def test_an_erased_user_has_no_address_to_write_to(self, email_adapter, caplog):
        """A GDPR erasure blanks the email but keeps the row - see docs/personal-data.md."""
        user = User(
            email="erased@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        user.email = ""

        assert self._send(email_adapter, user) is False
        assert email_adapter.sent == []
        assert "user.reenabled_email_skipped_no_address" in caplog.text

    def test_a_failing_adapter_is_reported_not_raised(self):
        user = User(
            email="back@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )

        assert self._send(FakeEmailAdapter(succeed=False), user) is False


class TestSearchAssemblyCandidateUsers:
    """Who may search for members to add, and how much of the user table they see.

    Admins keep partial search over email and name. An assembly manager matches
    on a full email address only, so the endpoint cannot be used to enumerate
    accounts - see docs/personal-data.md.
    """

    def _setup(self, uow, searcher_role, assembly_role=None):
        assembly = Assembly(title="Members", question="?")
        uow.assemblies.add(assembly)
        searcher = User(
            email="searcher@example.com",
            global_role=searcher_role,
            password_hash="hash",  # pragma: allowlist secret
        )
        if assembly_role:
            searcher.assembly_roles.append(
                UserAssemblyRole(user_id=searcher.id, assembly_id=assembly.id, role=assembly_role)
            )
        candidate = User(
            email="colleague@example.com",
            first_name="Casey",
            last_name="Colleague",
            global_role=GlobalRole.USER,
            password_hash="hash",  # pragma: allowlist secret
        )
        uow.users.add(searcher)
        uow.users.add(candidate)
        return assembly, searcher, candidate

    def test_admin_gets_partial_matches(self, uow):
        assembly, admin, candidate = self._setup(uow, GlobalRole.ADMIN)

        results = user_service.search_assembly_candidate_users(uow, assembly.id, "colle", admin)

        assert [u.id for u in results] == [candidate.id]

    def test_admin_can_match_on_a_name(self, uow):
        assembly, admin, candidate = self._setup(uow, GlobalRole.ADMIN)

        results = user_service.search_assembly_candidate_users(uow, assembly.id, "Casey", admin)

        assert [u.id for u in results] == [candidate.id]

    def test_assembly_manager_gets_an_exact_email_match(self, uow):
        assembly, manager, candidate = self._setup(uow, GlobalRole.USER, AssemblyRole.ASSEMBLY_MANAGER)

        results = user_service.search_assembly_candidate_users(uow, assembly.id, "colleague@example.com", manager)

        assert [u.id for u in results] == [candidate.id]

    def test_assembly_manager_gets_nothing_from_a_fragment(self, uow):
        """The privacy-relevant case: no fishing for accounts with a partial address."""
        assembly, manager, _ = self._setup(uow, GlobalRole.USER, AssemblyRole.ASSEMBLY_MANAGER)

        assert user_service.search_assembly_candidate_users(uow, assembly.id, "colle", manager) == []

    def test_assembly_manager_gets_nothing_from_a_name(self, uow):
        assembly, manager, _ = self._setup(uow, GlobalRole.USER, AssemblyRole.ASSEMBLY_MANAGER)

        assert user_service.search_assembly_candidate_users(uow, assembly.id, "Casey", manager) == []

    def test_an_organiser_managing_the_assembly_may_search(self, uow):
        """An organiser can add colleagues to the assemblies they created."""
        assembly, organiser, candidate = self._setup(uow, GlobalRole.ORGANISER, AssemblyRole.ASSEMBLY_MANAGER)

        results = user_service.search_assembly_candidate_users(uow, assembly.id, "colleague@example.com", organiser)

        assert [u.id for u in results] == [candidate.id]

    def test_an_organiser_with_no_role_on_the_assembly_is_refused(self, uow):
        assembly, organiser, _ = self._setup(uow, GlobalRole.ORGANISER)

        with pytest.raises(InsufficientPermissions):
            user_service.search_assembly_candidate_users(uow, assembly.id, "colleague@example.com", organiser)

    def test_a_confirmation_caller_is_refused(self, uow):
        """Managing members is the assembly manager's job, not every member's."""
        assembly, caller, _ = self._setup(uow, GlobalRole.USER, AssemblyRole.CONFIRMATION_CALLER)

        with pytest.raises(InsufficientPermissions):
            user_service.search_assembly_candidate_users(uow, assembly.id, "colleague@example.com", caller)

    def test_a_blank_search_term_returns_nothing(self, uow):
        assembly, admin, _ = self._setup(uow, GlobalRole.ADMIN)

        assert user_service.search_assembly_candidate_users(uow, assembly.id, "", admin) == []

    def test_an_unknown_assembly_is_not_found(self, uow):
        admin = User(email="a@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        uow.users.add(admin)

        with pytest.raises(AssemblyNotFoundError):
            user_service.search_assembly_candidate_users(uow, uuid.uuid4(), "anything", admin)
