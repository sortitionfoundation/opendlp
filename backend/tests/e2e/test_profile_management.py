"""ABOUTME: End-to-end PostgreSQL happy-path smokes for profile management
ABOUTME: Behavioural coverage (validation, redirects, set-password branches) lives in tests/component/"""

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
        user, _ = create_user(
            uow=uow,
            email=f"oauth-{uuid.uuid4()}@example.com",
            first_name="OAuth",
            last_name="User",
            oauth_provider="google",
            oauth_id="google-oauth-id-123",
            global_role=GlobalRole.USER,
        )
        return user


def test_view_own_profile(logged_in_user: FlaskClient, regular_user: User) -> None:
    """Viewing own profile shows correct information."""
    response = logged_in_user.get("/profile")
    assert response.status_code == 200
    assert regular_user.email.encode() in response.data
    assert b"My Account" in response.data
    assert b"Edit profile" in response.data


def test_edit_profile_post_success(logged_in_user: FlaskClient) -> None:
    """Successfully updating profile information persists to the database."""
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


def test_change_password_success(client: FlaskClient, regular_user: User) -> None:
    """Successfully changing password persists so the user can log in with it."""
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


def test_oauth_user_can_set_password(client: FlaskClient, oauth_user: User) -> None:
    """OAuth user can set a password and end up with both auth methods active."""
    with client.session_transaction() as session:
        session["_user_id"] = str(oauth_user.id)

    response = client.get("/profile/set-password")
    assert response.status_code == 200
    assert b"Set Password" in response.data

    response = client.post(
        "/profile/set-password",
        data={
            "new_password": "NewSecurePass123!",  # pragma: allowlist secret
            "new_password_confirm": "NewSecurePass123!",  # pragma: allowlist secret
            "csrf_token": get_csrf_token(client, "/profile/set-password"),
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Password set successfully" in response.data
    assert b"Active" in response.data  # Both auth methods now active
