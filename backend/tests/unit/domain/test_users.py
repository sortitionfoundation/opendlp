"""ABOUTME: Unit tests for User and UserAssemblyRole domain models
ABOUTME: Tests user creation, role checking, OAuth switching, and assembly access"""

import uuid
from datetime import datetime

import pytest

from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, GlobalRole


class TestUser:
    def test_create_user_with_password(self):
        user = User(
            username="testuser", email="test@example.com", global_role=GlobalRole.USER, password_hash="hashed_password"
        )

        assert user.username == "testuser"
        assert user.email == "test@example.com"
        assert user.global_role == GlobalRole.USER
        assert user.password_hash == "hashed_password"
        assert user.oauth_provider is None
        assert user.oauth_id is None
        assert user.is_active is True
        assert isinstance(user.id, uuid.UUID)
        assert isinstance(user.created_at, datetime)

    def test_create_user_with_oauth(self):
        user = User(
            username="oauthuser",
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="12345",
        )

        assert user.oauth_provider == "google"
        assert user.oauth_id == "12345"
        assert user.password_hash is None

    def test_create_user_requires_auth_method(self):
        with pytest.raises(ValueError, match="User must have either password_hash or OAuth credentials"):
            User(username="noauth", email="noauth@example.com", global_role=GlobalRole.USER)

    def test_validate_username(self):
        # Valid username
        user = User(
            username="valid_user-123", email="test@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        assert user.username == "valid_user-123"

        # Invalid usernames
        with pytest.raises(ValueError, match="Username must be between 3 and 200 characters long"):
            User(username="ab", email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")

        with pytest.raises(ValueError, match="Username must contain only letters"):
            User(username="user@domain", email="test@example.com", global_role=GlobalRole.USER, password_hash="hash")

    def test_validate_email(self):
        # Valid email
        user = User(username="testuser", email="valid@example.com", global_role=GlobalRole.USER, password_hash="hash")
        assert user.email == "valid@example.com"

        # Invalid emails
        with pytest.raises(ValueError, match="Invalid email address"):
            User(username="testuser", email="invalid", global_role=GlobalRole.USER, password_hash="hash")

        with pytest.raises(ValueError, match="Invalid email address"):
            User(username="testuser", email="", global_role=GlobalRole.USER, password_hash="hash")

    def test_has_global_admin(self):
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )

        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )

        assert admin_user.has_global_admin() is True
        assert regular_user.has_global_admin() is False

    def test_can_access_assembly_global_roles(self):
        assembly_id = uuid.uuid4()

        # Admin can access any assembly
        admin_user = User(
            username="admin", email="admin@example.com", global_role=GlobalRole.ADMIN, password_hash="hash"
        )
        assert admin_user.can_access_assembly(assembly_id) is True

        # Global organiser can access any assembly
        organiser_user = User(
            username="organiser",
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password_hash="hash",
        )
        assert organiser_user.can_access_assembly(assembly_id) is True

        # Regular user cannot access without specific role
        regular_user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash"
        )
        assert regular_user.can_access_assembly(assembly_id) is False

    def test_can_access_assembly_with_assembly_role(self):
        user = User(username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assembly1_id = uuid.uuid4()
        assembly2_id = uuid.uuid4()

        # Add assembly role
        user.assembly_roles.append(
            UserAssemblyRole(user_id=user.id, assembly_id=assembly1_id, role=AssemblyRole.ASSEMBLY_MANAGER)
        )

        assert user.can_access_assembly(assembly1_id) is True
        assert user.can_access_assembly(assembly2_id) is False

    def test_get_assembly_role(self):
        user = User(username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assembly_id = uuid.uuid4()
        user.assembly_roles.append(
            UserAssemblyRole(user_id=user.id, assembly_id=assembly_id, role=AssemblyRole.CONFIRMATION_CALLER)
        )

        assert user.get_assembly_role(assembly_id) == AssemblyRole.CONFIRMATION_CALLER
        assert user.get_assembly_role(uuid.uuid4()) is None

    def test_switch_to_oauth(self):
        user = User(
            username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="original_hash"
        )

        user.switch_to_oauth("google", "oauth123")

        assert user.oauth_provider == "google"
        assert user.oauth_id == "oauth123"
        assert user.password_hash is None

    def test_switch_to_oauth_requires_provider_and_id(self):
        user = User(username="user", email="user@example.com", global_role=GlobalRole.USER, password_hash="hash")

        with pytest.raises(ValueError, match="Provider and OAuth ID are required"):
            user.switch_to_oauth("", "oauth123")

        with pytest.raises(ValueError, match="Provider and OAuth ID are required"):
            user.switch_to_oauth("google", "")

    def test_user_equality_and_hash(self):
        user_id = uuid.uuid4()

        user1 = User(
            user_id=user_id,
            username="user1",
            email="user1@example.com",
            global_role=GlobalRole.USER,
            password_hash="hash",
        )

        user2 = User(
            user_id=user_id,
            username="user2",  # Different username but same ID
            email="user2@example.com",
            global_role=GlobalRole.ADMIN,
            password_hash="hash2",
        )

        user3 = User(username="user3", email="user3@example.com", global_role=GlobalRole.USER, password_hash="hash")

        assert user1 == user2  # Same ID
        assert user1 != user3  # Different ID
        assert hash(user1) == hash(user2)
        assert hash(user1) != hash(user3)


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
