"""ABOUTME: End-to-end PostgreSQL happy-path smokes for admin invite management
ABOUTME: Behavioural coverage (permission/render/expiry branches) lives in tests/component/"""

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


def test_list_invites_page_accessible_to_admin(logged_in_admin: FlaskClient):
    """Admin can access the invite list page."""
    response = logged_in_admin.get("/admin/invites")
    assert response.status_code == 200
    assert b"Invite Management" in response.data


@pytest.mark.time_machine(datetime(2025, 1, 1))
def test_create_invite_success(client: FlaskClient, admin_user: User, postgres_session_factory):
    """Successfully creating an invite persists it to the database."""
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

    assert response.status_code == 302
    assert "/admin/invites/" in response.location
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        invites = list(uow.user_invites.all())
        assert len(invites) == 1
        assert invites[0].expires_at.date() == date(2025, 1, 3)
        assert invites[0].global_role == GlobalRole.USER


@pytest.mark.time_machine(datetime(2025, 1, 1))
def test_create_invite_with_email(
    client: FlaskClient, admin_user: User, postgres_session_factory, capture_json_handler
):
    """Creating an invite with email sends an invitation email and saves it."""
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
    assert b"Invite created successfully" in response.data
    assert b"Invitation email sent" in response.data

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        invites = list(uow.user_invites.all())
        assert len(invites) == 1
        assert invites[0].global_role == GlobalRole.USER
        assert invites[0].email == "newuser@example.com"

    # Verify the send was logged, without the recipient email (PII redaction / audit)
    log_output = capture_json_handler.getvalue()
    assert "Invite email sent" in log_output
    assert "newuser@example.com" not in log_output


def test_view_invite_page_accessible_to_admin(client: FlaskClient, admin_user: User, postgres_session_factory):
    """Admin can view invite details."""
    login_as_admin(client, admin_user)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
        invite_id = invite.id

    response = client.get(f"/admin/invites/{invite_id}")
    assert response.status_code == 200
    assert b"Invite Details" in response.data


def test_revoke_invite_success(client: FlaskClient, admin_user: User, postgres_session_factory):
    """Successfully revoking an invite persists so it is no longer valid."""
    login_as_admin(client, admin_user)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        invite = generate_invite(uow, admin_user.id, GlobalRole.USER, expires_in_hours=24)
        invite_id = invite.id

    response = client.post(
        f"/admin/invites/{invite_id}/revoke",
        data={"csrf_token": get_csrf_token(client, "/admin/invites")},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/invites" in response.location

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        revoked_invite = uow.user_invites.get(invite_id)
        assert not revoked_invite.is_valid()


def test_cleanup_invites_success(client: FlaskClient, admin_user: User, postgres_session_factory):
    """Successfully cleaning up expired invites redirects back to the list."""
    login_as_admin(client, admin_user)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        expired_invite = UserInvite(
            code="EXPIREDCODE1",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        uow.user_invites.add(expired_invite)
        uow.commit()

    response = client.post(
        "/admin/invites/cleanup",
        data={"csrf_token": get_csrf_token(client, "/admin/invites")},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert "/admin/invites" in response.location
