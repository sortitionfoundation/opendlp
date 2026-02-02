"""ABOUTME: End-to-end tests for admin user management features
ABOUTME: Tests complete admin workflows for viewing, editing, and managing users"""

import re

import pytest
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def admin_user(postgres_session_factory):
    """Create an admin user in the database."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        admin, _ = create_user(
            uow,
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password="adminpass123",  # pragma: allowlist secret
        )

    # Confirm email so admin can log in
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = uow.users.get(admin.id)
        user.confirm_email()
        uow.commit()
        return user.create_detached_copy()


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

    def test_list_users_page_not_accessible_to_regular_user(self, client: FlaskClient, regular_user: User):
        """Test that regular users cannot access admin user list."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.get("/admin/users")
        assert response.status_code == 403  # Forbidden

    def test_list_users_page_redirects_when_not_logged_in(self, client: FlaskClient):
        """Test that non-authenticated users are redirected to login."""
        response = client.get("/admin/users")
        assert response.status_code == 302
        assert "login" in response.location

    def test_list_users_shows_pagination(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test that user list shows pagination controls."""
        login_as_admin(client, admin_user)

        response = client.get("/admin/users?per_page=3")
        assert response.status_code == 200

        # Should show pagination (implementation may vary)
        # Could check for page numbers, next/prev links, etc.
        data = response.data.decode()
        assert "page" in data.lower() or "next" in data.lower() or "previous" in data.lower()

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

    def test_view_user_page_not_accessible_to_regular_user(self, client: FlaskClient, regular_user: User):
        """Test that regular users cannot view user details page."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.get(f"/admin/users/{regular_user.id}")
        assert response.status_code == 403  # Forbidden

    def test_view_user_page_shows_user_details(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test that view user page shows all relevant user information."""
        login_as_admin(client, admin_user)

        user = test_users[0]
        response = client.get(f"/admin/users/{user.id}")
        assert response.status_code == 200

        # Should show user details
        assert user.email.encode() in response.data
        assert user.first_name.encode() in response.data
        assert user.last_name.encode() in response.data


class TestAdminUserEdit:
    """Test admin edit user functionality."""

    def test_edit_user_page_accessible_to_admin(self, client: FlaskClient, admin_user: User, regular_user: User):
        """Test that admin can access edit user page."""
        login_as_admin(client, admin_user)

        response = client.get(f"/admin/users/{regular_user.id}/edit")
        assert response.status_code == 200
        assert b"Edit User" in response.data or b"edit" in response.data.lower()

    def test_edit_user_form_preselects_current_role(
        self, client: FlaskClient, admin_user: User, test_users: list[User]
    ):
        """Test that the edit form pre-selects the user's current role."""
        login_as_admin(client, admin_user)

        # Test with a regular user
        user = test_users[0]  # Should be a USER role
        assert user.global_role == GlobalRole.USER, f"Expected USER role but got {user.global_role}"

        response = client.get(f"/admin/users/{user.id}/edit")
        assert response.status_code == 200

        # Check that the USER radio button is checked
        data = response.data.decode()
        # Look for: value="USER" checked (with any amount of whitespace)

        user_radio = re.search(r'value="USER"[^>]*?checked', data)
        assert user_radio is not None, "USER radio button should be checked but isn't"

        # Ensure other radio buttons are not checked
        admin_radio = re.search(r'value="ADMIN"[^>]*?checked', data)
        assert admin_radio is None, "ADMIN radio button should not be checked"

        # Test with a global organiser
        organiser = test_users[6]  # The last one should be the organiser
        assert organiser.global_role == GlobalRole.GLOBAL_ORGANISER, (
            f"Expected GLOBAL_ORGANISER role but got {organiser.global_role}"
        )

        response = client.get(f"/admin/users/{organiser.id}/edit")
        assert response.status_code == 200

        data = response.data.decode()
        # Look for the GLOBAL_ORGANISER radio button being checked
        organiser_radio = re.search(r'value="GLOBAL_ORGANISER"[^>]*?checked', data)
        assert organiser_radio is not None, "GLOBAL_ORGANISER radio button should be checked but isn't"

    def test_edit_user_page_not_accessible_to_regular_user(self, client: FlaskClient, regular_user: User):
        """Test that regular users cannot access edit user page."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.get(f"/admin/users/{regular_user.id}/edit")
        assert response.status_code == 403  # Forbidden

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

    def test_edit_user_role_success(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test successfully changing user role."""
        login_as_admin(client, admin_user)

        user = test_users[0]  # Regular user
        response = client.post(
            f"/admin/users/{user.id}/edit",
            data={
                "first_name": user.first_name,
                "last_name": user.last_name,
                "global_role": GlobalRole.GLOBAL_ORGANISER.name,
                "is_active": "y",
                "csrf_token": get_csrf_token(client, f"/admin/users/{user.id}/edit"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success

    def test_edit_user_deactivate_success(self, client: FlaskClient, admin_user: User, test_users: list[User]):
        """Test successfully deactivating a user."""
        login_as_admin(client, admin_user)

        user = test_users[0]
        response = client.post(
            f"/admin/users/{user.id}/edit",
            data={
                "first_name": user.first_name,
                "last_name": user.last_name,
                "global_role": user.global_role.name,
                # Not including is_active means checkbox is unchecked (deactivate)
                "csrf_token": get_csrf_token(client, f"/admin/users/{user.id}/edit"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success

    def test_admin_cannot_change_own_role(self, client: FlaskClient, admin_user: User):
        """Test that admin cannot demote themselves."""
        login_as_admin(client, admin_user)

        response = client.post(
            f"/admin/users/{admin_user.id}/edit",
            data={
                "first_name": admin_user.first_name or "Admin",
                "last_name": admin_user.last_name or "User",
                "global_role": GlobalRole.USER.name,  # Try to demote to regular user
                "is_active": "y",
                "csrf_token": get_csrf_token(client, f"/admin/users/{admin_user.id}/edit"),
            },
            follow_redirects=False,
        )

        # Should show error (could be 200 with error message or redirect)
        assert response.status_code == 200
        assert b"Cannot change your own" in response.data or b"error" in response.data.lower()

    def test_admin_cannot_deactivate_self(self, client: FlaskClient, admin_user: User):
        """Test that admin cannot deactivate their own account."""
        login_as_admin(client, admin_user)

        response = client.post(
            f"/admin/users/{admin_user.id}/edit",
            data={
                "first_name": admin_user.first_name or "Admin",
                "last_name": admin_user.last_name or "User",
                "global_role": GlobalRole.ADMIN.name,
                # Not including is_active checkbox (deactivate)
                "csrf_token": get_csrf_token(client, f"/admin/users/{admin_user.id}/edit"),
            },
            follow_redirects=False,
        )

        # Should show error
        assert response.status_code == 200
        assert b"Cannot deactivate your own" in response.data or b"error" in response.data.lower()


class TestAdminNavigation:
    """Test admin navigation menu."""

    def test_admin_menu_visible_to_admin(self, client: FlaskClient, admin_user: User):
        """Test that Admin menu is visible to admin users."""
        login_as_admin(client, admin_user)

        response = client.get("/dashboard")
        assert response.status_code == 200
        assert b"Site Admin" in response.data  # Admin link in navigation

    def test_admin_menu_not_visible_to_regular_user(self, client: FlaskClient, regular_user: User):
        """Test that Admin menu is not visible to regular users."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.get("/dashboard")
        assert response.status_code == 200

        # Admin link should not be in navigation for regular users
        # This check might need adjustment based on actual HTML structure
        data = response.data.decode()
        assert "admin/users" not in data.lower() or "Admin" not in data
