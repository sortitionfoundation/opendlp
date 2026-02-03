"""ABOUTME: End-to-end tests for admin invite management features
ABOUTME: Tests complete admin workflows for listing, creating, viewing, and revoking invites"""

from datetime import UTC, date, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.invite_service import generate_invite
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


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


class TestListInvitesPage:
    """Test admin invite list page."""

    def test_list_invites_page_accessible_to_admin(self, logged_in_admin: FlaskClient):
        """Test that admin can access invite list page."""
        response = logged_in_admin.get("/admin/invites")
        assert response.status_code == 200
        assert b"Invite Management" in response.data

    def test_list_invites_page_not_accessible_to_regular_user(self, client: FlaskClient, regular_user: User):
        """Test that regular users cannot access admin invite list."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.get("/admin/invites")
        assert response.status_code == 403  # Forbidden

    def test_list_invites_page_redirects_when_not_logged_in(self, client: FlaskClient):
        """Test that non-authenticated users are redirected to login."""
        response = client.get("/admin/invites")
        assert response.status_code == 302
        assert "login" in response.location

    def test_list_invites_shows_statistics(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test that invite list shows statistics cards."""
        login_as_admin(client, admin_user)

        # Create some test invites
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            generate_invite(uow, admin_user.id, GlobalRole.GLOBAL_ORGANISER, expires_in_hours=48)

        response = client.get("/admin/invites")
        assert response.status_code == 200

        # Should show statistics
        assert b"Total Invites" in response.data
        assert b"Active Invites" in response.data

    def test_list_invites_shows_invite_codes(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test that invite list displays invite codes."""
        login_as_admin(client, admin_user)

        # Create test invite
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_code = invite.code

        response = client.get("/admin/invites")
        assert response.status_code == 200
        assert invite_code.encode() in response.data

    def test_list_invites_shows_role_tags(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test that invite list displays role tags."""
        login_as_admin(client, admin_user)

        # Create invites with different roles
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            generate_invite(uow, admin_user.id, GlobalRole.ADMIN, expires_in_hours=24)
            generate_invite(uow, admin_user.id, GlobalRole.GLOBAL_ORGANISER, expires_in_hours=24)
            generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)

        response = client.get("/admin/invites")
        assert response.status_code == 200

        # Should show role badges
        assert b"Admin" in response.data and b"Global Organiser" in response.data and b"User" in response.data


class TestCreateInvite:
    """Test admin create invite functionality."""

    def test_create_invite_page_accessible_to_admin(self, client: FlaskClient, admin_user: User):
        """Test that admin can access create invite page."""
        login_as_admin(client, admin_user)

        response = client.get("/admin/invites/create")
        assert response.status_code == 200
        assert b"Create" in response.data or b"Invite" in response.data

    def test_create_invite_page_not_accessible_to_regular_user(
        self, client: FlaskClient, regular_user: User, postgres_session_factory
    ):
        """Test that regular users cannot access create invite page."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.get("/admin/invites/create")
        assert response.status_code == 403  # Forbidden

    @pytest.mark.time_machine(datetime(2025, 1, 1))
    def test_create_invite_success(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test successfully creating an invite."""
        login_as_admin(client, admin_user)

        response = client.post(
            "/admin/invites/create",
            data={
                "global_role": GlobalRole.USER.name,
                "expires_in_hours": 48,
                "csrf_token": get_csrf_token(client, "/admin/invites/create"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        assert "/admin/invites/" in response.location
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invites = list(uow.user_invites.all())
            assert len(invites) == 1
            assert invites[0].expires_at.date() == date(2025, 1, 3)
            assert invites[0].global_role == GlobalRole.USER

    @pytest.mark.time_machine(datetime(2025, 1, 1))
    def test_create_invite_with_admin_role(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test creating an invite with admin role."""
        login_as_admin(client, admin_user)

        response = client.post(
            "/admin/invites/create",
            data={
                "global_role": GlobalRole.ADMIN.name,
                "expires_in_hours": 24,
                "csrf_token": get_csrf_token(client, "/admin/invites/create"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invites = list(uow.user_invites.all())
            assert len(invites) == 1
            assert invites[0].expires_at.date() == date(2025, 1, 2)
            assert invites[0].global_role == GlobalRole.ADMIN

    @pytest.mark.time_machine(datetime(2025, 1, 1))
    def test_create_invite_with_default_expiry(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test creating an invite with default expiry."""
        login_as_admin(client, admin_user)

        response = client.post(
            "/admin/invites/create",
            data={
                "global_role": GlobalRole.USER.name,
                # No expires_in_hours, should use default
                "csrf_token": get_csrf_token(client, "/admin/invites/create"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invites = list(uow.user_invites.all())
            assert len(invites) == 1
            assert invites[0].expires_at.date() == date(2025, 1, 8)
            assert invites[0].global_role == GlobalRole.USER

    @pytest.mark.time_machine(datetime(2025, 1, 1))
    def test_create_invite_with_email(self, client: FlaskClient, admin_user: User, postgres_session_factory, caplog):
        """Test creating an invite with email sends invitation email."""
        login_as_admin(client, admin_user)

        response = client.post(
            "/admin/invites/create",
            data={
                "global_role": GlobalRole.USER.name,
                "email": "newuser@example.com",
                "expires_in_hours": 72,
                "csrf_token": get_csrf_token(client, "/admin/invites/create"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Should show success message for invite creation
        assert b"Invite created successfully" in response.data
        # Should show success message for email sending (in console mode)
        assert b"Invitation email sent" in response.data

        # Verify invite was created in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invites = list(uow.user_invites.all())
            assert len(invites) == 1
            assert invites[0].global_role == GlobalRole.USER

        # Verify email was logged (console adapter logs emails)
        assert "Invite email sent to newuser@example.com" in caplog.text


class TestViewInvite:
    """Test admin view invite details page."""

    def test_view_invite_page_accessible_to_admin(
        self, client: FlaskClient, admin_user: User, postgres_session_factory
    ):
        """Test that admin can view invite details."""
        login_as_admin(client, admin_user)

        # Create test invite
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        response = client.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 200
        assert b"Invite Details" in response.data

    def test_view_invite_page_not_accessible_to_regular_user(
        self, client: FlaskClient, regular_user: User, postgres_session_factory, admin_user: User
    ):
        """Test that regular users cannot view invite details page."""
        # Create test invite
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 403  # Forbidden

    def test_view_invite_shows_details(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test that view invite page shows all relevant information."""
        login_as_admin(client, admin_user)

        # Create test invite
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.GLOBAL_ORGANISER, expires_in_hours=24)
            invite_id = invite.id
            invite_code = invite.code

        response = client.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 200

        # Should show invite details
        assert invite_code.encode() in response.data
        assert b"Global Organiser" in response.data or b"GLOBAL_ORGANISER" in response.data

    def test_view_invite_shows_registration_url(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test that view invite page shows registration URL."""
        login_as_admin(client, admin_user)

        # Create test invite
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        response = client.get(f"/admin/invites/{invite_id}")
        assert response.status_code == 200

        # Should show registration URL
        assert b"Registration URL" in response.data and b"register" in response.data.lower()

    def test_view_invite_invalid_id_redirects(self, client: FlaskClient, admin_user: User):
        """Test that viewing invalid invite ID redirects to list."""
        login_as_admin(client, admin_user)

        # Use a random UUID
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/admin/invites/{fake_id}", follow_redirects=False)

        assert response.status_code == 302
        assert "/admin/invites" in response.location


class TestRevokeInvite:
    """Test admin revoke invite functionality."""

    def test_revoke_invite_success(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test successfully revoking an invite."""
        login_as_admin(client, admin_user)

        # Create active invite
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        response = client.post(
            f"/admin/invites/{invite_id}/revoke",
            data={
                "csrf_token": get_csrf_token(client, "/admin/invites"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        assert "/admin/invites" in response.location

        # Verify invite is no longer valid
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            revoked_invite = uow.user_invites.get(invite_id)
            assert not revoked_invite.is_valid()

    def test_revoke_invite_not_accessible_to_regular_user(
        self, client: FlaskClient, regular_user: User, postgres_session_factory, admin_user: User
    ):
        """Test that regular users cannot revoke invites."""
        # Create active invite
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            invite_id = invite.id

        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.post(
            f"/admin/invites/{invite_id}/revoke",
            data={
                "csrf_token": get_csrf_token(client, "/admin/invites"),
            },
        )

        assert response.status_code == 403  # Forbidden

    def test_revoke_invalid_invite_redirects(self, client: FlaskClient, admin_user: User):
        """Test that revoking invalid invite ID redirects to list."""
        login_as_admin(client, admin_user)

        # Use a random UUID
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.post(
            f"/admin/invites/{fake_id}/revoke",
            data={
                "csrf_token": get_csrf_token(client, "/admin/invites"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/admin/invites" in response.location


class TestCleanupInvites:
    """Test admin cleanup expired invites functionality."""

    def test_cleanup_invites_success(self, client: FlaskClient, admin_user: User, postgres_session_factory):
        """Test successfully cleaning up expired invites."""
        login_as_admin(client, admin_user)

        # Create expired invite by setting expiry in the past
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            expired_invite = UserInvite(
                code="EXPIREDCODE1",
                global_role=GlobalRole.USER,
                created_by=admin_user.id,
                expires_at=datetime.now(UTC) - timedelta(hours=1),  # Already expired
            )
            uow.user_invites.add(expired_invite)
            uow.commit()

        response = client.post(
            "/admin/invites/cleanup",
            data={
                "csrf_token": get_csrf_token(client, "/admin/invites"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302  # Redirect after success
        assert "/admin/invites" in response.location

    def test_cleanup_invites_no_expired_shows_message(self, client: FlaskClient, admin_user: User):
        """Test cleanup with no expired invites shows appropriate message."""
        login_as_admin(client, admin_user)

        response = client.post(
            "/admin/invites/cleanup",
            data={
                "csrf_token": get_csrf_token(client, "/admin/invites"),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Should show message about no expired invites
        assert b"No expired invites" in response.data or b"Cleaned up" in response.data

    def test_cleanup_invites_not_accessible_to_regular_user(self, client: FlaskClient, regular_user: User):
        """Test that regular users cannot cleanup invites."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        response = client.post(
            "/admin/invites/cleanup",
            data={
                "csrf_token": get_csrf_token(client, "/admin/invites"),
            },
        )

        assert response.status_code == 403  # Forbidden

    def test_cleanup_invites_preserves_active_invites(
        self, client: FlaskClient, admin_user: User, postgres_session_factory
    ):
        """Test that cleanup only removes expired invites, not active ones."""
        login_as_admin(client, admin_user)

        # Create both active and expired invites
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            active_invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
            expired_invite = UserInvite(
                code="EXPIREDCODE2",
                global_role=GlobalRole.USER,
                created_by=admin_user.id,
                expires_at=datetime.now(UTC) - timedelta(hours=1),  # Already expired
            )
            uow.user_invites.add(expired_invite)
            uow.commit()
            active_invite_id = active_invite.id

        response = client.post(
            "/admin/invites/cleanup",
            data={
                "csrf_token": get_csrf_token(client, "/admin/invites"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        # Verify active invite still exists
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            active = uow.user_invites.get(active_invite_id)
            assert active is not None
            assert active.is_valid()
