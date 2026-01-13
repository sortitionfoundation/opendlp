"""ABOUTME: Unit tests for User and UserAssemblyRole domain models
ABOUTME: Tests user creation, role checking, OAuth switching, and assembly access"""

import uuid
from datetime import UTC, datetime

import pytest

from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole


class TestUser:
    def test_create_user_with_password(self):
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed_password",
            first_name="Test",
            last_name="User",
        )

        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.global_role == GlobalRole.USER
        assert user.password_hash == "hashed_password"
        assert user.oauth_provider is None
        assert user.oauth_id is None
        assert user.is_active is True
        assert user.user_data_agreement_agreed_at is None
        assert isinstance(user.id, uuid.UUID)
        assert isinstance(user.created_at, datetime)

    def test_create_user_with_oauth(self):
        user = User(
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="12345",
            first_name="OAuth",
            last_name="User",
        )

        assert user.oauth_provider == "google"
        assert user.oauth_id == "12345"
        assert user.password_hash is None

    def test_create_user_requires_auth_method(self):
        with pytest.raises(ValueError, match="User must have either password_hash or OAuth credentials"):
            User(email="noauth@example.com", global_role=GlobalRole.USER)

    def test_display_name_property(self):
        # User with both first and last name
        user1 = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
            first_name="John",
            last_name="Doe",
        )
        assert user1.display_name == "John Doe"
        assert user1.full_name == "John Doe"

        # User with only first name
        user2 = User(email="test2@example.com", global_role=GlobalRole.USER, password_hash="hash", first_name="Jane")
        assert user2.display_name == "Jane"
        assert user2.full_name == "Jane"

        # User with no names - falls back to email prefix
        user3 = User(email="fallback@example.com", global_role=GlobalRole.USER, password_hash="hash")
        assert user3.display_name == "fallback"
        assert user3.full_name == ""

    def test_validate_email(self):
        # Valid email
        user = User(email="valid@example.com", global_role=GlobalRole.USER, password_hash="hash")
        assert user.email == "valid@example.com"

        # Invalid emails
        with pytest.raises(ValueError, match="Invalid email address"):
            User(email="invalid", global_role=GlobalRole.USER, password_hash="hash")

        with pytest.raises(ValueError, match="Invalid email address"):
            User(email="", global_role=GlobalRole.USER, password_hash="hash")

    def test_has_global_admin(self):
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")

        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assert admin_user.has_global_admin() is True
        assert regular_user.has_global_admin() is False

    def test_can_access_assembly_global_roles(self):
        assembly_id = uuid.uuid4()

        # Admin can access any assembly
        admin_user = User(email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
        assert admin_user.can_access_assembly(assembly_id) is True

        # Global organiser can access any assembly
        organiser_user = User(
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )
        assert organiser_user.can_access_assembly(assembly_id) is True

        # Regular user cannot access without specific role
        regular_user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")
        assert regular_user.can_access_assembly(assembly_id) is False

    def test_can_access_assembly_with_assembly_role(self):
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assembly1_id = uuid.uuid4()
        assembly2_id = uuid.uuid4()

        # Add assembly role
        user.assembly_roles.append(
            UserAssemblyRole(user_id=user.id, assembly_id=assembly1_id, role=AssemblyRole.ASSEMBLY_MANAGER)
        )

        assert user.can_access_assembly(assembly1_id) is True
        assert user.can_access_assembly(assembly2_id) is False

    def test_get_assembly_role(self):
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assembly_id = uuid.uuid4()
        user.assembly_roles.append(
            UserAssemblyRole(user_id=user.id, assembly_id=assembly_id, role=AssemblyRole.CONFIRMATION_CALLER)
        )

        assert user.get_assembly_role(assembly_id) == AssemblyRole.CONFIRMATION_CALLER
        assert user.get_assembly_role(uuid.uuid4()) is None

    def test_switch_to_oauth(self):
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="original_hash")

        user.switch_to_oauth("google", "oauth123")

        assert user.oauth_provider == "google"
        assert user.oauth_id == "oauth123"
        assert user.password_hash is None

    def test_switch_to_oauth_requires_provider_and_id(self):
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        with pytest.raises(ValueError, match="Provider and OAuth ID are required"):
            user.switch_to_oauth("", "oauth123")

        with pytest.raises(ValueError, match="Provider and OAuth ID are required"):
            user.switch_to_oauth("google", "")

    def test_mark_data_agreement_agreed(self):
        user = User(email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assert user.user_data_agreement_agreed_at is None

        before_time = datetime.now(UTC)
        user.mark_data_agreement_agreed()
        after_time = datetime.now(UTC)

        assert user.user_data_agreement_agreed_at is not None
        assert before_time <= user.user_data_agreement_agreed_at <= after_time

    def test_create_user_with_data_agreement_time(self):
        agreement_time = datetime.now(UTC)
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
            user_data_agreement_agreed_at=agreement_time,
        )

        assert user.user_data_agreement_agreed_at == agreement_time

    def test_user_equality_and_hash(self):
        user_id = uuid.uuid4()

        user1 = User(
            user_id=user_id,
            email="user1@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
            first_name="First",
            last_name="User",
        )

        user2 = User(
            user_id=user_id,
            email="user2@example.com",  # Different email but same ID
            global_role=GlobalRole.ADMIN,
            password_hash="hash2",
            first_name="Second",
            last_name="User",
        )

        user3 = User(email="user3@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assert user1 == user2  # Same ID
        assert user1 != user3  # Different ID
        assert hash(user1) == hash(user2)
        assert hash(user1) != hash(user3)

    def test_add_oauth_credentials(self):
        """Test adding OAuth credentials to user."""
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")

        user.add_oauth_credentials("google", "google123")

        assert user.oauth_provider == "google"
        assert user.oauth_id == "google123"
        assert user.password_hash == "hashed"  # pragma: allowlist secret

    def test_add_oauth_credentials_validation(self):
        """Test OAuth credentials validation."""
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")

        with pytest.raises(ValueError, match="Provider and OAuth ID are required"):
            user.add_oauth_credentials("", "id123")

        with pytest.raises(ValueError, match="Provider and OAuth ID are required"):
            user.add_oauth_credentials("google", "")

    def test_remove_password(self):
        """Test removing password with OAuth present."""
        user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed",  # pragma: allowlist secret
            oauth_provider="google",
            oauth_id="google123",
        )

        user.remove_password()

        assert user.password_hash is None
        assert user.oauth_provider == "google"

    def test_remove_password_fails_without_oauth(self):
        """Test cannot remove password without OAuth."""
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")

        with pytest.raises(ValueError, match="Cannot remove password: no OAuth authentication configured"):
            user.remove_password()

    def test_remove_oauth(self):
        """Test removing OAuth with password present."""
        user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed",  # pragma: allowlist secret
            oauth_provider="google",
            oauth_id="google123",
        )

        user.remove_oauth()

        assert user.oauth_provider is None
        assert user.oauth_id is None
        assert user.password_hash == "hashed"  # pragma: allowlist secret

    def test_remove_oauth_fails_without_password(self):
        """Test cannot remove OAuth without password."""
        user = User(
            email="user@example.com", global_role=GlobalRole.USER, oauth_provider="google", oauth_id="google123"
        )

        with pytest.raises(ValueError, match="Cannot remove OAuth: no password authentication configured"):
            user.remove_oauth()

    def test_has_multiple_auth_methods(self):
        """Test checking for multiple auth methods."""
        # Both password and OAuth
        user = User(
            email="user@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed",  # pragma: allowlist secret
            oauth_provider="google",
            oauth_id="google123",
        )
        assert user.has_multiple_auth_methods() is True

        # Only password
        user = User(email="user@example.com", global_role=GlobalRole.USER, password_hash="hashed")
        assert user.has_multiple_auth_methods() is False

        # Only OAuth
        user = User(
            email="user@example.com", global_role=GlobalRole.USER, oauth_provider="google", oauth_id="google123"
        )
        assert user.has_multiple_auth_methods() is False


class TestUserAssemblyRole:
    def test_create_user_assembly_role(self):
        user_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        role = UserAssemblyRole(user_id=user_id, assembly_id=assembly_id, role=AssemblyRole.ASSEMBLY_MANAGER)

        assert role.user_id == user_id
        assert role.assembly_id == assembly_id
        assert role.role == AssemblyRole.ASSEMBLY_MANAGER
        assert isinstance(role.id, uuid.UUID)
        assert isinstance(role.created_at, datetime)

    def test_user_assembly_role_equality_and_hash(self):
        role_id = uuid.uuid4()
        user_id = uuid.uuid4()
        assembly_id = uuid.uuid4()

        role1 = UserAssemblyRole(
            role_id=role_id, user_id=user_id, assembly_id=assembly_id, role=AssemblyRole.ASSEMBLY_MANAGER
        )

        role2 = UserAssemblyRole(
            role_id=role_id,
            user_id=uuid.uuid4(),  # Different user but same ID
            assembly_id=uuid.uuid4(),  # Different assembly but same ID
            role=AssemblyRole.CONFIRMATION_CALLER,
        )

        role3 = UserAssemblyRole(user_id=user_id, assembly_id=assembly_id, role=AssemblyRole.ASSEMBLY_MANAGER)

        assert role1 == role2  # Same ID
        assert role1 != role3  # Different ID
        assert hash(role1) == hash(role2)
        assert hash(role1) != hash(role3)
