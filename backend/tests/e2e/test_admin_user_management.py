"""ABOUTME: End-to-end PostgreSQL tests for admin user management
ABOUTME: Smokes plus db_semantics filter/search/pagination tests; behavioural coverage lives in tests/component/"""

import base64
import secrets

import pyotp
import pytest
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import two_factor_service
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def test_users(postgres_session_factory, admin_user):
    """Create multiple test users for pagination and filtering tests."""
    users = []

    # Create regular users
    for i in range(5):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user, _ = create_user(
                uow,
                email=f"user{i}@example.com",
                global_role=GlobalRole.USER,
                password="SecurePass123!",  # pragma: allowlist secret
                first_name=f"User{i}",
                last_name=f"Test{i}",
            )
            uow.commit()
            users.append(user)

    # Create an inactive user
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        inactive_user, _ = create_user(
            uow,
            email="inactive@example.com",
            global_role=GlobalRole.USER,
            password="SecurePass123!",  # pragma: allowlist secret
            first_name="Inactive",
            last_name="User",
            is_active=False,
        )
        uow.commit()
        users.append(inactive_user)

    # Create a global organiser
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        organiser, _ = create_user(
            uow,
            email="organiser@example.com",
            global_role=GlobalRole.GLOBAL_ORGANISER,
            password="SecurePass123!",  # pragma: allowlist secret
            first_name="Global",
            last_name="Organiser",
        )
        uow.commit()
        users.append(organiser)

    return users


def login_as_admin(client: FlaskClient, admin_user: User) -> None:
    """Helper function to login as admin."""
    client.post(
        "/auth/login",
        data={
            "email": admin_user.email,
            "password": "adminpass123",  # pragma: allowlist secret
            "csrf_token": get_csrf_token(client, "/auth/login"),
        },
    )


class TestAdminUserList:
    """Test admin user list page."""

    def test_list_users_page_accessible_to_admin(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test that admin can access user list page."""
        login_as_admin(client, admin_user)

        response = client.get("/admin/users")
        assert response.status_code == 200
        assert b"User Management" in response.data or b"Users" in response.data

        # Should show user emails
        assert b"user0@example.com" in response.data
        assert b"inactive@example.com" in response.data
        assert b"organiser@example.com" in response.data

    @pytest.mark.db_semantics
    def test_list_users_shows_pagination(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test that user list shows pagination controls."""
        login_as_admin(client, admin_user)

        response = client.get("/admin/users?per_page=3")
        assert response.status_code == 200

        # Should show pagination (implementation may vary)
        # Could check for page numbers, next/prev links, etc.
        data = response.data.decode()
        assert "page" in data.lower() or "next" in data.lower() or "previous" in data.lower()

    @pytest.mark.db_semantics
    def test_list_users_filter_by_role(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test filtering users by role."""
        login_as_admin(client, admin_user)

        # Filter for users with "user" role
        response = client.get("/admin/users?role=user")
        assert response.status_code == 200

        # Should show regular users
        assert b"user0@example.com" in response.data

        # Should not show organiser
        assert b"organiser@example.com" not in response.data or b"Global Organiser" not in response.data

    @pytest.mark.db_semantics
    def test_list_users_filter_by_active_status(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test filtering users by active status."""
        login_as_admin(client, admin_user)

        # Filter for active users only
        response = client.get("/admin/users?active=true")
        assert response.status_code == 200

        # Should show active users
        assert b"user0@example.com" in response.data
        # Inactive user might not be shown or might be shown with inactive badge
        assert b"inactive@example.com" not in response.data

    @pytest.mark.db_semantics
    def test_list_users_search_by_name(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test searching users by name."""
        login_as_admin(client, admin_user)

        # Search for "Inactive"
        response = client.get("/admin/users?search=Inactive")
        assert response.status_code == 200

        # Should show inactive user
        assert b"inactive@example.com" in response.data

        # Should not show other users
        assert b"user0@example.com" not in response.data


class TestAdminUserView:
    """Test admin view user details page."""

    def test_view_user_page_accessible_to_admin(self, client: FlaskClient, admin_user: User, regular_user: User):
        """Test that admin can view user details."""
        login_as_admin(client, admin_user)

        response = client.get(f"/admin/users/{regular_user.id}")
        assert response.status_code == 200
        assert regular_user.email.encode() in response.data
        assert regular_user.first_name.encode() in response.data if regular_user.first_name else True


class TestAdminUserEdit:
    """Test admin edit user functionality."""

    def test_edit_user_name_success(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test successfully editing user name."""
        login_as_admin(client, admin_user)

        user = test_users[0]
        response = client.post(
            f"/admin/users/{user.id}/edit",
            data={
                "first_name": "NewFirst",
                "last_name": "NewLast",
                "global_role": user.global_role.name,
                "is_active": "y",
                "csrf_token": get_csrf_token(client, f"/admin/users/{user.id}/edit"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        assert f"/admin/users/{user.id}" in response.location

        # Verify changes by viewing user
        view_response = client.get(f"/admin/users/{user.id}")
        assert b"NewFirst" in view_response.data
        assert b"NewLast" in view_response.data


@pytest.fixture
def user_with_2fa(postgres_session_factory, temp_env_vars) -> User:
    """Create a confirmed user with 2FA enabled."""
    raw_key = secrets.token_bytes(32)
    temp_env_vars(TOTP_ENCRYPTION_KEY=base64.b64encode(raw_key).decode())

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user, _ = create_user(
            uow,
            email="twofa-target@example.com",
            global_role=GlobalRole.USER,
            password="SecurePass123!",  # pragma: allowlist secret
            first_name="Two",
            last_name="Factor",
        )
        user_id = user.id

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, user_id)
        valid_code = pyotp.TOTP(totp_secret).now()
        two_factor_service.enable_2fa(uow, user_id, totp_secret, valid_code, backup_codes)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        return uow.users.get(user_id).create_detached_copy()


class TestAdmin2FA:
    """PG happy-path smokes for the admin 2FA management routes."""

    def test_disable_user_2fa_success(
        self, client: FlaskClient, admin_user: User, user_with_2fa: User, postgres_session_factory
    ):
        """Admin can disable a user's 2FA."""
        login_as_admin(client, admin_user)

        response = client.post(
            f"/admin/users/{user_with_2fa.id}/2fa/disable",
            data={"csrf_token": get_csrf_token(client, f"/admin/users/{user_with_2fa.id}")},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert f"/admin/users/{user_with_2fa.id}" in response.location
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.users.get(user_with_2fa.id).totp_enabled is False

    def test_view_user_2fa_audit_log_success(self, client: FlaskClient, admin_user: User, user_with_2fa: User):
        """Admin can view a user's 2FA audit log."""
        login_as_admin(client, admin_user)

        response = client.get(f"/admin/users/{user_with_2fa.id}/2fa/audit-log")

        assert response.status_code == 200
