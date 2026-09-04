# ABOUTME: Component tests for profile management routes over a FakeUnitOfWork
# ABOUTME: Drives the real profile Flask routes + services against a seeded fake store, no PostgreSQL

import uuid

import pytest
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork


@pytest.fixture
def oauth_user(fake_store: FakeStore) -> User:
    """A confirmed OAuth-only user (no password) in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email=f"oauth-{uuid.uuid4()}@example.com",
            first_name="OAuth",
            last_name="User",
            oauth_provider="google",
            oauth_id="google-oauth-id-123",
            global_role=GlobalRole.USER,
        )
        return user.create_detached_copy()


def _login_session(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = user.get_id()


class TestProfileViewing:
    def test_view_profile_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_a_user_is_told_what_their_role_means(self, logged_in_user: FlaskClient) -> None:
        """The page used to render the raw enum value, which explained nothing."""
        response = logged_in_user.get("/profile")
        assert response.status_code == 200
        assert b"An organiser can add you to one" in response.data

    def test_an_organiser_is_told_what_their_role_means(self, logged_in_organiser: FlaskClient) -> None:
        response = logged_in_organiser.get("/profile")
        assert response.status_code == 200
        assert b"Organiser" in response.data
        assert b"You can create assemblies" in response.data

    def test_an_admin_is_told_what_their_role_means(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/profile")
        assert response.status_code == 200
        assert b"You can see and manage every assembly" in response.data

    def test_the_raw_enum_value_is_not_shown(self, logged_in_organiser: FlaskClient) -> None:
        response = logged_in_organiser.get("/profile")
        assert b">organiser<" not in response.data


class TestProfileEditing:
    def test_edit_profile_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile/edit")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_edit_profile_get(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/edit")
        assert response.status_code == 200
        assert b"Edit Profile" in response.data
        assert b"First Name" in response.data
        assert b"Last Name" in response.data


class TestPasswordChange:
    def test_change_password_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile/change-password")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_oauth_user_redirected_from_change_password(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = client.get("/profile/change-password", follow_redirects=True)
        assert response.status_code == 200
        assert b"Set Password" in response.data
        assert b"You need to set a password first" in response.data

    def test_change_password_get(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/change-password")
        assert response.status_code == 200
        assert b"Change Password" in response.data
        assert b"Current Password" in response.data
        assert b"New Password" in response.data

    def test_change_password_with_wrong_current_password(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post(
            "/profile/change-password",
            data={
                "current_password": "WrongPassword123!",  # pragma: allowlist secret
                "new_password": "NewPassword123!",  # pragma: allowlist secret
                "new_password_confirm": "NewPassword123!",  # pragma: allowlist secret
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Current password is incorrect" in response.data

    def test_change_password_with_weak_new_password(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post(
            "/profile/change-password",
            data={
                "current_password": "userpass123",  # pragma: allowlist secret
                "new_password": "weak",  # pragma: allowlist secret
                "new_password_confirm": "weak",  # pragma: allowlist secret
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Field must be at least 8 characters long" in response.data


class TestSetPassword:
    def test_set_password_requires_login(self, client: FlaskClient) -> None:
        response = client.get("/profile/set-password")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_set_password_redirects_user_with_existing_password(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/set-password", follow_redirects=True)
        assert response.status_code == 200
        assert b"You already have a password" in response.data

    def test_set_password_validates_strength(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = client.post(
            "/profile/set-password",
            data={
                "new_password": "weak",  # pragma: allowlist secret
                "new_password_confirm": "weak",  # pragma: allowlist secret
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Field must be at least 8 characters long" in response.data

    def test_set_password_requires_confirmation_match(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        response = client.post(
            "/profile/set-password",
            data={
                "new_password": "NewSecurePass123!",  # pragma: allowlist secret
                "new_password_confirm": "DifferentPass456!",  # pragma: allowlist secret
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Passwords must match" in response.data

    def test_after_setting_password_user_can_remove_oauth(self, client: FlaskClient, oauth_user: User) -> None:
        _login_session(client, oauth_user)

        client.post(
            "/profile/set-password",
            data={
                "new_password": "NewSecurePass123!",  # pragma: allowlist secret
                "new_password_confirm": "NewSecurePass123!",  # pragma: allowlist secret
            },
        )

        response = client.post("/profile/remove-oauth", follow_redirects=True)

        assert response.status_code == 200
        assert b"OAuth authentication removed successfully" in response.data
