# ABOUTME: Component tests for admin invite management routes over a FakeUnitOfWork
# ABOUTME: Drives the real admin Flask routes + invite service against a seeded fake store

import re
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
            generate_invite(uow, admin_user.id, GlobalRole.ORGANISER, expires_in_hours=48)

        response = logged_in_admin.get("/admin/invites")
        assert response.status_code == 200
        assert b"Total invites" in response.data
        assert b"Active invites" in response.data

    def test_list_invites_is_on_the_backoffice_design_with_the_invites_tab(
        self, logged_in_admin: FlaskClient, fake_store, admin_user: User
    ):
        """The invites list is the Invites tab of Site Admin, with no GOV.UK markup."""
        with FakeUnitOfWork(store=fake_store) as uow:
            generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)

        body = logged_in_admin.get("/admin/invites").get_data(as_text=True)

        assert "govuk-" not in body
        assert re.search(r'id="admin-tabs-tab-invites"[^>]*aria-selected="true"', body)
        assert 'id="admin-tabs-panel-invites"' in body

    def test_revoke_and_cleanup_ask_for_confirmation_on_their_forms(
        self, logged_in_admin: FlaskClient, fake_store, admin_user: User
    ):
        """An active invite's row offers Revoke, and both destructive forms carry a confirmation."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        body = logged_in_admin.get("/admin/invites").get_data(as_text=True)

        assert re.search(
            rf'<form method="post"\s+action="/admin/invites/{invite_id}/revoke"\s+data-confirm="Are you sure', body
        )
        assert re.search(r'<form method="post"\s+action="/admin/invites/cleanup"\s+data-confirm="This will', body)
        assert f'data-row-url="/admin/invites/{invite_id}"' in body

    def test_invite_actions_share_a_line_with_the_count(
        self, logged_in_admin: FlaskClient, fake_store, admin_user: User
    ):
        """The count comes first on the line, then Create invite and Clean up, pushed to the right."""
        with FakeUnitOfWork(store=fake_store) as uow:
            generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)

        body = logged_in_admin.get("/admin/invites").get_data(as_text=True)

        row = re.search(
            r"Showing 1 invites \(including expired\)\s*</p>\s*<div[^>]*ml-auto[^>]*>(.*?)</form>", body, re.DOTALL
        )
        assert row is not None
        assert "Create invite" in row.group(1)
        assert "Clean up expired invites" in row.group(1)

    def test_invite_actions_stay_on_the_right_with_no_invites(self, logged_in_admin: FlaskClient):
        """With no invites there is no count, and the actions keep their place."""
        body = logged_in_admin.get("/admin/invites").get_data(as_text=True)

        assert "Showing" not in body
        assert re.search(
            r'<div class="flex flex-wrap items-center gap-3 ml-auto">\s*<a href="/admin/invites/create"', body
        )

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
            generate_invite(uow, admin_user.id, GlobalRole.ORGANISER, expires_in_hours=24)
            generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)

        response = logged_in_admin.get("/admin/invites")
        assert response.status_code == 200
        assert b"Admin" in response.data and b"Organiser" in response.data and b"User" in response.data


class TestCreateInvite:
    """Test admin create invite behaviour."""

    def test_create_invite_page_not_accessible_to_regular_user(self, logged_in_user: FlaskClient):
        """Regular users cannot access the create invite page."""
        response = logged_in_user.get("/admin/invites/create")
        assert response.status_code == 403

    def test_create_invite_page_starts_with_the_user_role_chosen(self, logged_in_admin: FlaskClient):
        """The form opens with the least powerful role already selected."""
        body = logged_in_admin.get("/admin/invites/create").get_data(as_text=True)

        assert re.search(r'value="USER"\s+checked', body)
        assert not re.search(r'value="ADMIN"\s+checked', body)
        assert "govuk-" not in body

    def test_create_invite_shows_an_error_beside_the_field(self, logged_in_admin: FlaskClient):
        """A refused email is reported next to its input, with the other values kept."""
        response = logged_in_admin.post(
            "/admin/invites/create",
            data={"global_role": GlobalRole.ORGANISER.name, "email": "not-an-email", "expires_in_hours": "12"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'id="email-error"' in body or 'aria-invalid="true"' in body
        assert re.search(r'value="ORGANISER"\s+checked', body)
        assert 'value="12"' in body

    @pytest.mark.time_machine(datetime(2025, 1, 1, tzinfo=UTC))
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

    @pytest.mark.time_machine(datetime(2025, 1, 1, tzinfo=UTC))
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
            invite = generate_invite(uow, admin_user.id, GlobalRole.ORGANISER, expires_in_hours=24)
            invite_id = invite.id
            invite_code = invite.code

        response = logged_in_admin.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 200
        assert invite_code.encode() in response.data
        assert b"Organiser" in response.data or b"ORGANISER" in response.data

    def test_view_invite_shows_registration_url(self, logged_in_admin: FlaskClient, fake_store, admin_user: User):
        """View invite page shows the registration URL."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        response = logged_in_admin.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 200
        assert b"Registration URL" in response.data and b"register" in response.data.lower()

    def test_view_invite_offers_copy_buttons_and_revoke(
        self, logged_in_admin: FlaskClient, fake_store, admin_user: User
    ):
        """The code and URL each have a copy button, and an active invite can be revoked."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id
            invite_code = invite.code

        body = logged_in_admin.get(f"/admin/invites/{invite_id}").get_data(as_text=True)

        assert f'data-copy-text="{invite_code}"' in body
        assert re.search(rf'data-copy-text="http://[^"]+/auth/register/{invite_code}"', body)
        assert re.search(rf'action="/admin/invites/{invite_id}/revoke"\s+data-confirm=', body)
        assert re.search(r'<a href="/admin/invites"[^>]*aria-label="Back to Invites"', body, re.DOTALL)
        assert "govuk-" not in body

    def test_view_used_invite_links_to_the_user_and_cannot_be_revoked(
        self, logged_in_admin: FlaskClient, fake_store, admin_user: User, regular_user: User
    ):
        """A used invite names who used it, with a link to their page, and offers no revoke."""
        with FakeUnitOfWork(store=fake_store) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id
            uow.user_invites.get(invite_id).use(regular_user.id)
            uow.commit()

        body = logged_in_admin.get(f"/admin/invites/{invite_id}").get_data(as_text=True)

        assert f'href="/admin/users/{regular_user.id}"' in body
        assert "/revoke" not in body

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
