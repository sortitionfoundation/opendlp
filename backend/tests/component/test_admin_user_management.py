# ABOUTME: Component tests for admin user management routes over a FakeUnitOfWork
# ABOUTME: Drives the real admin Flask routes + services against a seeded fake store, no PostgreSQL

import re
import uuid

import pytest
from flask import Flask
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeEmailAdapter, FakeStore, FakeUnitOfWork


def _second_client(app: Flask, user: User | None = None) -> FlaskClient:
    """A client separate from the conftest one, optionally signed in.

    The `client` and `logged_in_*` fixtures hand back the same object, so a test
    that needs both an admin and a victim browsing at once has to make its own.
    """
    other = app.test_client()
    if user is not None:
        with other.session_transaction() as session:
            session["_user_id"] = user.get_id()
            session["_fresh"] = True
    return other


@pytest.fixture
def fake_email(monkeypatch: pytest.MonkeyPatch) -> FakeEmailAdapter:
    """Capture the emails the admin routes send instead of writing them to the console."""
    adapter = FakeEmailAdapter()
    monkeypatch.setattr("opendlp.entrypoints.blueprints.admin.get_email_adapter", lambda: adapter)
    return adapter


@pytest.fixture
def failing_email(monkeypatch: pytest.MonkeyPatch) -> FakeEmailAdapter:
    """An email adapter that reports failure, for the path where we cannot reach the user."""
    adapter = FakeEmailAdapter(succeed=False)
    monkeypatch.setattr("opendlp.entrypoints.blueprints.admin.get_email_adapter", lambda: adapter)
    return adapter


def _seed_user(
    fake_store: FakeStore,
    email: str,
    global_role: GlobalRole,
    first_name: str = "",
    last_name: str = "",
    is_active: bool = True,
) -> User:
    """Create a confirmed user in the shared store and return a detached copy."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email=email,
            password="SecurePass123!",  # pragma: allowlist secret
            global_role=global_role,
            first_name=first_name,
            last_name=last_name,
            is_active=is_active,
            accept_data_agreement=True,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        user_obj = uow.users.get(user.id)
        user_obj.confirm_email()
        uow.commit()
        return user_obj.create_detached_copy()


class TestAdminUserListPermissions:
    """Permission and auth branches for the admin user list."""

    def test_list_users_not_accessible_to_regular_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/admin/users")
        assert response.status_code == 403

    def test_list_users_redirects_when_not_logged_in(self, client: FlaskClient) -> None:
        response = client.get("/admin/users")
        assert response.status_code == 302
        assert "login" in response.location


class TestAdminUserView:
    """Admin view user details page."""

    def test_view_user_not_accessible_to_regular_user(self, logged_in_user: FlaskClient, regular_user: User) -> None:
        response = logged_in_user.get(f"/admin/users/{regular_user.id}")
        assert response.status_code == 403

    def test_view_user_shows_user_details(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "view@example.com", GlobalRole.USER, "View", "Target")

        response = logged_in_admin.get(f"/admin/users/{user.id}")
        assert response.status_code == 200
        assert user.email.encode() in response.data
        assert user.first_name.encode() in response.data
        assert user.last_name.encode() in response.data


class TestAdminUserEdit:
    """Admin edit user functionality."""

    def test_edit_user_page_accessible_to_admin(self, logged_in_admin: FlaskClient, regular_user: User) -> None:
        response = logged_in_admin.get(f"/admin/users/{regular_user.id}/edit")
        assert response.status_code == 200
        assert b"Edit User" in response.data or b"edit" in response.data.lower()

    def test_edit_user_not_accessible_to_regular_user(self, logged_in_user: FlaskClient, regular_user: User) -> None:
        response = logged_in_user.get(f"/admin/users/{regular_user.id}/edit")
        assert response.status_code == 403

    def test_edit_user_form_preselects_current_role(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "regular@example.com", GlobalRole.USER, "Reg", "User")

        response = logged_in_admin.get(f"/admin/users/{user.id}/edit")
        assert response.status_code == 200

        data = response.data.decode()
        assert re.search(r'value="USER"[^>]*?checked', data) is not None, "USER radio should be checked"
        assert re.search(r'value="ADMIN"[^>]*?checked', data) is None, "ADMIN radio should not be checked"

        organiser = _seed_user(fake_store, "organiser@example.com", GlobalRole.GLOBAL_ORGANISER, "Global", "Organiser")

        response = logged_in_admin.get(f"/admin/users/{organiser.id}/edit")
        assert response.status_code == 200

        data = response.data.decode()
        assert re.search(r'value="GLOBAL_ORGANISER"[^>]*?checked', data) is not None, (
            "GLOBAL_ORGANISER radio should be checked"
        )

    def test_edit_user_role_success(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "role@example.com", GlobalRole.USER, "Role", "Change")

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/edit",
            data={
                "first_name": user.first_name,
                "last_name": user.last_name,
                "global_role": GlobalRole.GLOBAL_ORGANISER.name,
                "is_active": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_editing_a_user_leaves_them_active(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """The edit form no longer carries the active flag - disabling has its own route."""
        user = _seed_user(fake_store, "edited@example.com", GlobalRole.USER, "Ed", "Ited")

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/edit",
            data={
                "first_name": "Renamed",
                "last_name": user.last_name,
                "global_role": user.global_role.name,
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).is_active is True

    def test_admin_cannot_change_own_role(self, logged_in_admin: FlaskClient, admin_user: User) -> None:
        response = logged_in_admin.post(
            f"/admin/users/{admin_user.id}/edit",
            data={
                "first_name": admin_user.first_name or "Admin",
                "last_name": admin_user.last_name or "User",
                "global_role": GlobalRole.USER.name,
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Cannot change your own" in response.data or b"error" in response.data.lower()

    def test_the_edit_form_has_no_active_checkbox(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Unticking a box mid-form is the wrong control for something this destructive."""
        user = _seed_user(fake_store, "noactive@example.com", GlobalRole.USER)

        response = logged_in_admin.get(f"/admin/users/{user.id}/edit")

        assert response.status_code == 200
        assert b'name="is_active"' not in response.data


class TestAdminDisableAccount:
    """Disabling has to leave no way back in until the account is enabled again."""

    def test_a_disabled_user_is_signed_out_on_their_next_request(
        self, logged_in_admin: FlaskClient, app: Flask, fake_store: FakeStore
    ) -> None:
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)
        victim_client = _second_client(app, victim)
        assert victim_client.get("/dashboard").status_code == 200

        logged_in_admin.post(f"/admin/users/{victim.id}/disable")

        response = victim_client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.location

    def test_the_cancelled_session_stays_cancelled_after_re_enabling(
        self, logged_in_admin: FlaskClient, app: Flask, fake_store: FakeStore, fake_email: FakeEmailAdapter
    ) -> None:
        """The whole point: an attacker's browser must not come back to life."""
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)
        victim_client = _second_client(app, victim)
        logged_in_admin.post(f"/admin/users/{victim.id}/disable")

        logged_in_admin.post(f"/admin/users/{victim.id}/enable")

        response = victim_client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.location

    def test_disabling_makes_the_password_unusable(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)

        logged_in_admin.post(f"/admin/users/{victim.id}/disable")

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(victim.id).has_usable_password() is False

    def test_a_disabled_user_cannot_sign_in_with_their_old_password(
        self, logged_in_admin: FlaskClient, app: Flask, fake_store: FakeStore
    ) -> None:
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)
        logged_in_admin.post(f"/admin/users/{victim.id}/disable")

        response = _second_client(app).post(
            "/auth/login",
            data={"email": "victim@example.com", "password": "SecurePass123!"},  # pragma: allowlist secret
            follow_redirects=True,
        )

        assert b"Invalid email or password" in response.data

    def test_the_old_password_still_fails_once_the_account_is_enabled_again(
        self, logged_in_admin: FlaskClient, app: Flask, fake_store: FakeStore, fake_email: FakeEmailAdapter
    ) -> None:
        """With the account active again, only the destroyed password stands between them."""
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)
        logged_in_admin.post(f"/admin/users/{victim.id}/disable")
        logged_in_admin.post(f"/admin/users/{victim.id}/enable")

        client = _second_client(app)
        response = client.post(
            "/auth/login",
            data={"email": "victim@example.com", "password": "SecurePass123!"},  # pragma: allowlist secret
            follow_redirects=True,
        )

        assert b"Invalid email or password" in response.data
        with client.session_transaction() as session:
            assert "_user_id" not in session

    def test_an_admin_cannot_disable_their_own_account(
        self, logged_in_admin: FlaskClient, admin_user: User, fake_store: FakeStore
    ) -> None:
        response = logged_in_admin.post(f"/admin/users/{admin_user.id}/disable", follow_redirects=True)

        assert b"cannot disable your own account" in response.data
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(admin_user.id).is_active is True

    def test_a_regular_user_cannot_disable_anyone(self, logged_in_user: FlaskClient, fake_store: FakeStore) -> None:
        victim = _seed_user(fake_store, "victim@example.com", GlobalRole.USER)

        response = logged_in_user.post(f"/admin/users/{victim.id}/disable")

        assert response.status_code == 403
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(victim.id).is_active is True

    def test_disabling_an_unknown_user_says_so(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(f"/admin/users/{uuid.uuid4()}/disable", follow_redirects=True)

        assert b"User not found" in response.data

    def test_the_user_page_offers_disable_for_an_active_user(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        user = _seed_user(fake_store, "active@example.com", GlobalRole.USER)

        response = logged_in_admin.get(f"/admin/users/{user.id}")

        assert f"/admin/users/{user.id}/disable".encode() in response.data
        assert f"/admin/users/{user.id}/enable".encode() not in response.data

    def test_the_user_page_offers_enable_for_a_disabled_user(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        user = _seed_user(fake_store, "inactive@example.com", GlobalRole.USER, is_active=False)

        response = logged_in_admin.get(f"/admin/users/{user.id}")

        assert f"/admin/users/{user.id}/enable".encode() in response.data
        assert f"/admin/users/{user.id}/disable".encode() not in response.data

    def test_the_confirmation_sits_on_the_button_where_the_handler_reads_it(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """document-actions.js reads e.target.dataset.confirm, and e.target is the button.

        On the <form> the attribute is silently ignored and the destructive POST
        goes through unconfirmed.
        """
        user = _seed_user(fake_store, "active@example.com", GlobalRole.USER)

        response = logged_in_admin.get(f"/admin/users/{user.id}")

        button_tags = re.findall(r"<button[^>]*>", response.data.decode())
        assert any("Are you sure you want to disable this account" in tag for tag in button_tags)

    def test_an_admin_is_not_offered_a_button_on_their_own_page(
        self, logged_in_admin: FlaskClient, admin_user: User
    ) -> None:
        response = logged_in_admin.get(f"/admin/users/{admin_user.id}")

        assert f"/admin/users/{admin_user.id}/disable".encode() not in response.data


class TestAdminEnableAccount:
    """Re-enabling has to tell the user how to get back in."""

    def test_enabling_sets_the_account_active(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER, is_active=False)

        logged_in_admin.post(f"/admin/users/{user.id}/enable")

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(user.id).is_active is True

    def test_enabling_emails_the_user_a_route_to_a_new_password(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, fake_email: FakeEmailAdapter
    ) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER)
        logged_in_admin.post(f"/admin/users/{user.id}/disable")

        logged_in_admin.post(f"/admin/users/{user.id}/enable")

        assert len(fake_email.sent) == 1
        sent = fake_email.sent[0]
        assert sent["to"] == ["back@example.com"]
        assert "Re-enabled" in sent["subject"]
        # No token in the email - it points at the page that mints one
        assert "/auth/forgot-password" in sent["text_body"]
        assert "/auth/forgot-password" in sent["html_body"]

    def test_a_user_whose_2fa_was_cleared_is_told_to_set_it_up_again(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, fake_email: FakeEmailAdapter
    ) -> None:
        user = _seed_user(fake_store, "twofactor@example.com", GlobalRole.USER)
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.users.get(user.id).enable_totp("encrypted-secret")
            uow.commit()
        logged_in_admin.post(f"/admin/users/{user.id}/disable")

        logged_in_admin.post(f"/admin/users/{user.id}/enable")

        sent = fake_email.sent[0]
        assert "Two-factor authentication was also switched off" in sent["text_body"]
        assert "Two-factor authentication was also switched off" in sent["html_body"]

    def test_a_user_who_never_had_2fa_is_not_told_about_it(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, fake_email: FakeEmailAdapter
    ) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER)
        logged_in_admin.post(f"/admin/users/{user.id}/disable")

        logged_in_admin.post(f"/admin/users/{user.id}/enable")

        assert "Two-factor authentication" not in fake_email.sent[0]["text_body"]

    def test_an_oauth_user_is_not_told_to_reset_a_password(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, fake_email: FakeEmailAdapter
    ) -> None:
        with FakeUnitOfWork(store=fake_store) as uow:
            oauth_user = User(
                email="oauth@example.com",
                global_role=GlobalRole.USER,
                oauth_provider="google",
                oauth_id="google123",
                is_active=False,
            )
            uow.users.add(oauth_user)
            uow.commit()
            user_id = oauth_user.id

        logged_in_admin.post(f"/admin/users/{user_id}/enable")

        assert "/auth/forgot-password" not in fake_email.sent[0]["text_body"]
        assert "/auth/login" in fake_email.sent[0]["text_body"]

    def test_the_admin_is_told_when_the_email_could_not_be_sent(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore, failing_email: FakeEmailAdapter
    ) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER, is_active=False)

        response = logged_in_admin.post(f"/admin/users/{user.id}/enable", follow_redirects=True)

        assert b"could not email the user" in response.data

    def test_a_regular_user_cannot_enable_anyone(self, logged_in_user: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "back@example.com", GlobalRole.USER, is_active=False)

        response = logged_in_user.post(f"/admin/users/{user.id}/enable")

        assert response.status_code == 403

    def test_enabling_an_unknown_user_says_so(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(f"/admin/users/{uuid.uuid4()}/enable", follow_redirects=True)

        assert b"User not found" in response.data


class TestAdminNavigation:
    """Admin navigation menu visibility by role."""

    def test_admin_menu_visible_to_admin(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get("/dashboard")
        assert response.status_code == 200
        assert b"Site Admin" in response.data

    def test_admin_menu_not_visible_to_regular_user(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 200

        data = response.data.decode()
        assert "admin/users" not in data.lower() or "Admin" not in data
