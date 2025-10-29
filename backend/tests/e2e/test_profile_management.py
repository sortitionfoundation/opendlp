"""ABOUTME: End-to-end tests for profile management functionality
ABOUTME: Tests view profile, edit profile, and change password features"""

import uuid

import pytest
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def oauth_user(postgres_session_factory) -> User:
    """Create a test user with OAuth authentication."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = create_user(
            uow=uow,
            email=f"oauth-{uuid.uuid4()}@example.com",
            first_name="OAuth",
            last_name="User",
            oauth_provider="google",
            oauth_id="google-oauth-id-123",
            global_role=GlobalRole.USER,
        )
        return user


class TestProfileViewing:
    """Tests for viewing user profile."""

    def test_view_profile_requires_login(self, client: FlaskClient) -> None:
        """Test that viewing profile requires authentication."""
        response = client.get("/profile")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_view_own_profile(self, logged_in_user: FlaskClient, regular_user: User) -> None:
        """Test viewing own profile shows correct information."""
        response = logged_in_user.get("/profile")
        assert response.status_code == 200
        assert regular_user.email.encode() in response.data
        assert b"My Account" in response.data
        assert b"Edit profile" in response.data

    def test_oauth_user_sees_no_change_password_button(self, client: FlaskClient, oauth_user: User) -> None:
        """Test that OAuth users don't see change password option."""
        # Login manually by creating session
        with client.session_transaction() as session:
            session["_user_id"] = str(oauth_user.id)

        response = client.get("/profile")
        assert response.status_code == 200
        assert b"Change password" not in response.data
        assert oauth_user.oauth_provider.encode() in response.data


class TestProfileEditing:
    """Tests for editing user profile."""

    def test_edit_profile_requires_login(self, client: FlaskClient) -> None:
        """Test that editing profile requires authentication."""
        response = client.get("/profile/edit")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_edit_profile_get(self, logged_in_user: FlaskClient) -> None:
        """Test GET request to edit profile page."""
        response = logged_in_user.get("/profile/edit")
        assert response.status_code == 200
        assert b"Edit Profile" in response.data
        assert b"First Name" in response.data
        assert b"Last Name" in response.data

    def test_edit_profile_post_success(self, logged_in_user: FlaskClient) -> None:
        """Test successfully updating profile information."""
        response = logged_in_user.post(
            "/profile/edit",
            data={
                "first_name": "Updated",
                "last_name": "Name",
                "csrf_token": get_csrf_token(logged_in_user, "/profile/edit"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Profile updated successfully" in response.data
        assert b"Updated" in response.data
        assert b"Name" in response.data


class TestPasswordChange:
    """Tests for changing user password."""

    def test_change_password_requires_login(self, client: FlaskClient) -> None:
        """Test that changing password requires authentication."""
        response = client.get("/profile/change-password")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_oauth_user_redirected_from_change_password(self, client: FlaskClient, oauth_user: User) -> None:
        """Test that OAuth users are redirected away from change password page."""
        # Login manually by creating session
        with client.session_transaction() as session:
            session["_user_id"] = str(oauth_user.id)

        response = client.get("/profile/change-password", follow_redirects=True)
        assert response.status_code == 200
        assert b"You cannot change your password" in response.data

    def test_change_password_get(self, logged_in_user: FlaskClient) -> None:
        """Test GET request to change password page."""
        response = logged_in_user.get("/profile/change-password")
        assert response.status_code == 200
        assert b"Change Password" in response.data
        assert b"Current Password" in response.data
        assert b"New Password" in response.data

    def test_change_password_with_wrong_current_password(self, logged_in_user: FlaskClient) -> None:
        """Test that wrong current password is rejected."""
        response = logged_in_user.post(
            "/profile/change-password",
            data={
                "current_password": "WrongPassword123!",  # pragma: allowlist secret
                "new_password": "NewPassword123!",  # pragma: allowlist secret
                "new_password_confirm": "NewPassword123!",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(logged_in_user, "/profile/change-password"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Current password is incorrect" in response.data

    def test_change_password_with_weak_new_password(self, logged_in_user: FlaskClient) -> None:
        """Test that weak new password is rejected."""
        response = logged_in_user.post(
            "/profile/change-password",
            data={
                "current_password": "userpass123",  # pragma: allowlist secret
                "new_password": "weak",  # pragma: allowlist secret
                "new_password_confirm": "weak",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(logged_in_user, "/profile/change-password"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Form validation rejects password that's too short
        assert b"Field must be at least 8 characters long" in response.data

    def test_change_password_success(self, client: FlaskClient, regular_user: User) -> None:
        """Test successfully changing password."""
        # Login as regular user
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.post(
            "/profile/change-password",
            data={
                "current_password": "userpass123",  # pragma: allowlist secret
                "new_password": "NewPassword456!",  # pragma: allowlist secret
                "new_password_confirm": "NewPassword456!",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/profile/change-password"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Password changed successfully" in response.data

        # Verify can login with new password
        client.get("/auth/logout")
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "NewPassword456!",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
