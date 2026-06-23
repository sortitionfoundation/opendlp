# ABOUTME: Component tests for admin invite management routes over a FakeUnitOfWork
# ABOUTME: Drives the real admin Flask routes + invite service against a seeded fake store

from datetime import UTC, date, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.invite_service import generate_invite
from tests.fakes import FakeUnitOfWork


class TestListInvitesPage:
    """Test admin invite list page behaviour."""

    def test_list_invites_page_not_accessible_to_regular_user(self, logged_in_user: FlaskClient):
        """Regular users cannot access the admin invite list."""
        response = logged_in_user.get("/admin/invites")
        assert response.status_code == 403

    def test_list_invites_page_redirects_when_not_logged_in(self, client: FlaskClient):
        """Non-authenticated users are redirected to login."""
        response = client.get("/admin/invites")
        assert response.status_code == 302
        assert "login" in response.location

    def test_list_invites_shows_statistics(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """Invite list shows statistics cards."""
        with FakeUnitOfWork(store=fake_store) as uow:
            generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            generate_invite(uow, admin_user.id, GlobalRole.GLOBAL_ORGANISER, expires_in_hours=48)

        response = logged_in_admin.get("/admin/invites")
        assert response.status_code == 200
        assert b"Total Invites" in response.data
        assert b"Active Invites" in response.data

    def test_list_invites_shows_invite_codes(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """Invite list displays invite codes."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_code = invite.code

        response = logged_in_admin.get("/admin/invites")
        assert response.status_code == 200
        assert invite_code.encode() in response.data

    def test_list_invites_shows_email_column(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """Invite list shows the email address column."""
        with FakeUnitOfWork(store=fake_store) as uow:
            generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24, email="list@example.com")

        response = logged_in_admin.get("/admin/invites")
        assert response.status_code == 200
        assert b"Email" in response.data
        assert b"list@example.com" in response.data

    def test_list_invites_shows_role_tags(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """Invite list displays role tags."""
        with FakeUnitOfWork(store=fake_store) as uow:
            generate_invite(uow, admin_user.id, GlobalRole.ADMIN, expires_in_hours=24)
            generate_invite(uow, admin_user.id, GlobalRole.GLOBAL_ORGANISER, expires_in_hours=24)
            generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)

        response = logged_in_admin.get("/admin/invites")
        assert response.status_code == 200
        assert b"Admin" in response.data and b"Global Organiser" in response.data and b"User" in response.data


class TestCreateInvite:
    """Test admin create invite behaviour."""

    def test_create_invite_page_not_accessible_to_regular_user(self, logged_in_user: FlaskClient):
        """Regular users cannot access the create invite page."""
        response = logged_in_user.get("/admin/invites/create")
        assert response.status_code == 403

    @pytest.mark.time_machine(datetime(2025, 1, 1))
    def test_create_invite_with_admin_role(self, logged_in_admin: FlaskClient, fake_store):
        """Creating an invite with admin role uses the requested role and expiry."""
        response = logged_in_admin.post(
            "/admin/invites/create",
            data={"global_role": GlobalRole.ADMIN.name, "expires_in_hours": 24},
            follow_redirects=False,
        )

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            invites = list(uow.user_invites.all())
            assert len(invites) == 1
            assert invites[0].expires_at.date() == date(2025, 1, 2)
            assert invites[0].global_role == GlobalRole.ADMIN

    @pytest.mark.time_machine(datetime(2025, 1, 1))
    def test_create_invite_with_default_expiry(self, logged_in_admin: FlaskClient, fake_store):
        """Creating an invite without an expiry uses the default."""
        response = logged_in_admin.post(
            "/admin/invites/create",
            data={"global_role": GlobalRole.USER.name},
            follow_redirects=False,
        )

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            invites = list(uow.user_invites.all())
            assert len(invites) == 1
            assert invites[0].expires_at.date() == date(2025, 1, 8)
            assert invites[0].global_role == GlobalRole.USER


class TestViewInvite:
    """Test admin view invite details page."""

    def test_view_invite_page_not_accessible_to_regular_user(
        self, client: FlaskClient, logged_in_user: FlaskClient, fake_store, admin_user: User
    ):
        """Regular users cannot view invite details."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        response = logged_in_user.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 403

    def test_view_invite_shows_email(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """View invite page shows the email address."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24, email="view@example.com")
            invite_id = invite.id

        response = logged_in_admin.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 200
        assert b"view@example.com" in response.data
        assert b"Email" in response.data

    def test_view_invite_shows_details(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """View invite page shows all relevant information."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.GLOBAL_ORGANISER, expires_in_hours=24)
            invite_id = invite.id
            invite_code = invite.code

        response = logged_in_admin.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 200
        assert invite_code.encode() in response.data
        assert b"Global Organiser" in response.data or b"GLOBAL_ORGANISER" in response.data

    def test_view_invite_shows_registration_url(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """View invite page shows the registration URL."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        response = logged_in_admin.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 200
        assert b"Registration URL" in response.data and b"register" in response.data.lower()

    def test_view_invite_invalid_id_redirects(self, logged_in_admin: FlaskClient):
        """Viewing an invalid invite ID redirects to the list."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = logged_in_admin.get(f"/admin/invites/{fake_id}", follow_redirects=False)
        assert response.status_code == 302
        assert "/admin/invites" in response.location


class TestRevokeInvite:
    """Test admin revoke invite behaviour."""

    def test_revoke_invite_not_accessible_to_regular_user(
        self, logged_in_user: FlaskClient, fake_store, admin_user: User
    ):
        """Regular users cannot revoke invites."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        response = logged_in_user.post(f"/admin/invites/{invite_id}/revoke")
        assert response.status_code == 403

    def test_revoke_invalid_invite_redirects(self, logged_in_admin: FlaskClient):
        """Revoking an invalid invite ID redirects to the list."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = logged_in_admin.post(f"/admin/invites/{fake_id}/revoke", follow_redirects=False)
        assert response.status_code == 302
        assert "/admin/invites" in response.location


class TestCleanupInvites:
    """Test admin cleanup expired invites behaviour."""

    def test_cleanup_invites_no_expired_shows_message(self, logged_in_admin: FlaskClient):
        """Cleanup with no expired invites shows an appropriate message."""
        response = logged_in_admin.post("/admin/invites/cleanup", follow_redirects=True)
        assert response.status_code == 200
        assert b"No expired invites" in response.data or b"Cleaned up" in response.data

    def test_cleanup_invites_not_accessible_to_regular_user(self, logged_in_user: FlaskClient):
        """Regular users cannot cleanup invites."""
        response = logged_in_user.post("/admin/invites/cleanup")
        assert response.status_code == 403

    def test_cleanup_invites_preserves_active_invites(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """Cleanup only removes expired invites, not active ones."""
        with FakeUnitOfWork(store=fake_store) as uow:
            active_invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            expired_invite = UserInvite(
                code="EXPIREDCODE2",
                global_role=GlobalRole.USER,
                created_by=admin_user.id,
                expires_at=datetime.now(UTC) - timedelta(hours=1),
            )
            uow.user_invites.add(expired_invite)
            uow.commit()
            active_invite_id = active_invite.id

        response = logged_in_admin.post("/admin/invites/cleanup", follow_redirects=False)
        assert response.status_code == 302

        with FakeUnitOfWork(store=fake_store) as uow:
            active = uow.user_invites.get(active_invite_id)
            assert active is not None
            assert active.is_valid()
