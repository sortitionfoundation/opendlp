# ABOUTME: Component tests for admin user management routes over a FakeUnitOfWork
# ABOUTME: Drives the real admin Flask routes + services against a seeded fake store, no PostgreSQL

import re

from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork


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

    def test_edit_user_deactivate_success(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        user = _seed_user(fake_store, "deactivate@example.com", GlobalRole.USER, "De", "Activate")

        response = logged_in_admin.post(
            f"/admin/users/{user.id}/edit",
            data={
                "first_name": user.first_name,
                "last_name": user.last_name,
                "global_role": user.global_role.name,
                # Omitting is_active leaves the checkbox unchecked (deactivate)
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_admin_cannot_change_own_role(self, logged_in_admin: FlaskClient, admin_user: User) -> None:
        response = logged_in_admin.post(
            f"/admin/users/{admin_user.id}/edit",
            data={
                "first_name": admin_user.first_name or "Admin",
                "last_name": admin_user.last_name or "User",
                "global_role": GlobalRole.USER.name,
                "is_active": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Cannot change your own" in response.data or b"error" in response.data.lower()

    def test_admin_cannot_deactivate_self(self, logged_in_admin: FlaskClient, admin_user: User) -> None:
        response = logged_in_admin.post(
            f"/admin/users/{admin_user.id}/edit",
            data={
                "first_name": admin_user.first_name or "Admin",
                "last_name": admin_user.last_name or "User",
                "global_role": GlobalRole.ADMIN.name,
                # Omitting is_active leaves the checkbox unchecked (deactivate)
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Cannot deactivate your own" in response.data or b"error" in response.data.lower()


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
