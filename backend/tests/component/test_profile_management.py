# ABOUTME: Component tests for profile management routes over a FakeUnitOfWork
# ABOUTME: Drives the real profile Flask routes + services against a seeded fake store, no PostgreSQL

import re
import uuid

import pytest
from flask import Flask, url_for
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
        assert b"A Project Manager can add you to one" in response.data

    def test_an_organiser_is_told_what_their_role_means(self, logged_in_organiser: FlaskClient) -> None:
        response = logged_in_organiser.get("/profile")
        assert response.status_code == 200
        assert b"Organiser" in response.data
        assert b"You can create projects" in response.data

    def test_an_admin_is_told_what_their_role_means(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/profile")
        assert response.status_code == 200
        assert b"You can see and manage every project" in response.data

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


class TestProfilePagesOnTheBackofficeDesign:
    """The view and edit pages left GOV.UK Frontend for the backoffice layout (sc-869)."""

    @pytest.mark.parametrize("url", ["/profile", "/profile/edit"])
    def test_page_has_no_govuk_markup(self, logged_in_user: FlaskClient, url: str) -> None:
        """A migrated page never mixes in GOV.UK classes or the GOV.UK stylesheet."""
        response = logged_in_user.get(url)

        assert response.status_code == 200
        assert b"govuk-" not in response.data
        assert b"css/application.css" not in response.data

    @pytest.mark.parametrize("url", ["/profile", "/profile/edit"])
    def test_page_uses_the_backoffice_layout(self, logged_in_user: FlaskClient, url: str) -> None:
        """The backoffice chrome is there: the account menu in the top bar and the flash container."""
        response = logged_in_user.get(url)

        assert b"backoffice/dist/main.css" in response.data
        assert b'id="account-menu-toggle"' in response.data
        assert b'id="floating-alerts"' in response.data

    def test_my_account_menu_item_opens_in_the_same_tab(self, logged_in_user: FlaskClient) -> None:
        """It used to open a separate tab because the page was on the old design."""
        response = logged_in_user.get("/profile")

        my_account_link = re.search(rb'<a href="/profile"\s[^>]*>', response.data)
        assert my_account_link is not None
        assert b"target=" not in my_account_link.group(0)

    def test_view_links_back_to_the_projects_list(self, app: Flask, logged_in_user: FlaskClient) -> None:
        """The old page linked to main.dashboard, which 404s unless the old dashboard is enabled."""
        with app.test_request_context():
            projects_url = url_for("backoffice.dashboard")
        response = logged_in_user.get("/profile")

        back_link = re.search(rb'<a href="([^"]+)"[^>]*aria-label="Back to Your projects"', response.data)
        assert back_link is not None
        assert back_link.group(1).decode() == projects_url

    def test_edit_form_keeps_its_fields(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/profile/edit")

        assert b'name="first_name"' in response.data
        assert b'name="last_name"' in response.data
        assert b'autocomplete="given-name"' in response.data
        assert b'autocomplete="family-name"' in response.data
        assert b'type="submit"' in response.data

    def test_edit_shows_the_field_error_beside_the_field(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post("/profile/edit", data={"first_name": "x" * 101, "last_name": "Name"})

        assert response.status_code == 200
        assert b"Field cannot be longer than 100 characters" in response.data
        assert b'aria-invalid="true"' in response.data

    def test_successful_edit_flashes_on_the_profile_page(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.post(
            "/profile/edit", data={"first_name": "Updated", "last_name": "Name"}, follow_redirects=True
        )

        assert response.status_code == 200
        assert b"Profile updated successfully" in response.data
        assert b"Updated" in response.data


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
