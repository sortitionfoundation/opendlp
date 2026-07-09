# ABOUTME: Component tests for authentication routes over a FakeUnitOfWork
# ABOUTME: Drives the real auth/dashboard/confirm-email routes + services against a seeded fake store, no PostgreSQL/Redis

from datetime import UTC, datetime, timedelta

import pytest
from flask import message_flashed
from flask.testing import FlaskClient
from markupsafe import Markup

from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.invite_service import generate_invite
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork


@pytest.fixture
def valid_invite(fake_store: FakeStore, admin_user: User) -> UserInvite:
    """A valid USER invite seeded in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        invite = generate_invite(uow, admin_user.id, GlobalRole.USER)
        return invite.create_detached_copy()


@pytest.fixture
def expired_invite(fake_store: FakeStore, admin_user: User) -> UserInvite:
    """An expired USER invite seeded in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        invite = generate_invite(uow, admin_user.id, GlobalRole.USER)
        fetched = uow.user_invites.get_by_code(invite.code)
        fetched.expires_at = datetime.now(UTC) - timedelta(hours=1)
        uow.commit()
        return fetched.create_detached_copy()


class TestRegistration:
    """Registration form validation and error branches."""

    def test_register_with_expired_invite_fails(self, client: FlaskClient, expired_invite: UserInvite) -> None:
        response = client.post(
            "/auth/register",
            data={
                "invite_code": expired_invite.code,
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@example.com",
                "password": "securepassword123",  # pragma: allowlist secret
                "password_confirm": "securepassword123",  # pragma: allowlist secret
                "accept_data_agreement": "y",
            },
        )
        assert response.status_code == 200
        assert b"Invalid invite code" in response.data

    def test_register_with_invalid_invite_fails(self, client: FlaskClient) -> None:
        response = client.post(
            "/auth/register",
            data={
                "invite_code": "INVALID123",
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@example.com",
                "password": "securepassword123",  # pragma: allowlist secret
                "password_confirm": "securepassword123",  # pragma: allowlist secret
                "accept_data_agreement": "y",
            },
        )
        assert response.status_code == 200

    def test_register_missing_fields_fails(self, client: FlaskClient, valid_invite: UserInvite) -> None:
        response = client.post(
            "/auth/register",
            data={
                "invite_code": valid_invite.code,
                "first_name": "New",
            },
        )
        assert response.status_code == 200

    def test_register_password_mismatch_fails(self, client: FlaskClient, valid_invite: UserInvite) -> None:
        response = client.post(
            "/auth/register",
            data={
                "invite_code": valid_invite.code,
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@example.com",
                "password": "securepassword123",  # pragma: allowlist secret
                "password_confirm": "differentpassword",  # pragma: allowlist secret
                "accept_data_agreement": "y",
            },
        )
        assert response.status_code == 200
        assert b"Passwords do not match" in response.data or b"error" in response.data

    def test_register_duplicate_email_fails(
        self, client: FlaskClient, regular_user: User, valid_invite: UserInvite
    ) -> None:
        response = client.post(
            "/auth/register",
            data={
                "invite_code": valid_invite.code,
                "first_name": "Another",
                "last_name": "User",
                "email": regular_user.email,
                "password": "securepassword123",  # pragma: allowlist secret
                "password_confirm": "securepassword123",  # pragma: allowlist secret
            },
        )
        assert response.status_code == 200

    def test_registration_with_invite_code_in_url(self, client: FlaskClient, valid_invite: UserInvite) -> None:
        """Registration form pre-fills the invite code from the URL."""
        response = client.get(f"/auth/register/{valid_invite.code}")
        assert response.status_code == 200
        assert valid_invite.code.encode() in response.data


class TestLogin:
    """Login failure branches and Flask-Login cookie behaviour."""

    @pytest.fixture(autouse=True)
    def _no_redis_rate_limit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Rate limiting is Redis-backed and stays in the e2e tier; no-op it here."""
        monkeypatch.setattr("opendlp.entrypoints.blueprints.auth.check_login_rate_limit", lambda **kwargs: None)
        monkeypatch.setattr("opendlp.entrypoints.blueprints.auth.record_failed_login", lambda **kwargs: None)

    def test_login_invalid_credentials_fails(self, client: FlaskClient, regular_user: User) -> None:
        response = client.post(
            "/auth/login",
            data={"email": regular_user.email, "password": "wrongpassword"},  # pragma: allowlist secret
        )
        assert response.status_code == 200
        assert b"Invalid email or password" in response.data or b"error" in response.data

    def test_login_nonexistent_user_fails(self, client: FlaskClient) -> None:
        response = client.post(
            "/auth/login",
            data={"email": "nonexistent@example.com", "password": "somepassword"},  # pragma: allowlist secret
        )
        assert response.status_code == 200

    def test_login_unconfirmed_email_renders_resend_link_not_markup_flash(
        self, client: FlaskClient, fake_store: FakeStore, valid_invite: UserInvite
    ) -> None:
        """Unconfirmed login renders a real resend link and flashes only plain text.

        flask-session serialises flashes with msgspec, which rejects Markup, so the
        resend link is rendered by the template rather than flashed as Markup.
        """
        with FakeUnitOfWork(store=fake_store) as uow:
            create_user(
                uow=uow,
                email="pending@example.com",
                password="securepassword123",  # pragma: allowlist secret
                invite_code=valid_invite.code,
            )

        flashed: list[object] = []

        def _record(sender: object, message: object, category: str) -> None:
            flashed.append(message)

        with message_flashed.connected_to(_record):
            response = client.post(
                "/auth/login",
                data={"email": "pending@example.com", "password": "securepassword123"},  # pragma: allowlist secret
            )

        assert response.status_code == 200
        # No flashed message may be Markup, or flask-session's msgspec serialiser fails.
        assert flashed
        assert not any(isinstance(msg, Markup) for msg in flashed)
        assert any("Please confirm your email address before logging in" in str(msg) for msg in flashed)
        # The resend link is rendered by the template as real, styled HTML.
        body = response.data.decode()
        assert "Resend confirmation" in body
        assert "/auth/resend-confirmation" in body

    @pytest.mark.filterwarnings("ignore:datetime.datetime.utcnow:DeprecationWarning")
    def test_login_remember_me_functionality(self, client: FlaskClient, regular_user: User) -> None:
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "remember_me": True,
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        cookie = client.get_cookie("remember_token")
        assert cookie is not None
        assert isinstance(cookie.expires, datetime)
        assert cookie.expires > datetime.now(UTC) + timedelta(days=5)


class TestProtectedPagesAndSession:
    """Auth-decorator, render branches, root redirect and session persistence."""

    def test_dashboard_view_access(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 200
        assert b"Assemblies" in response.data or b"assemblies" in response.data

    def test_root_page_shows_text_when_not_logged_in(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert "Ready to participate" in response.text

    def test_root_page_redirects_when_logged_in(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/")
        assert response.status_code == 302
        assert "dashboard" in response.location
        response = logged_in_user.get("/", follow_redirects=True)
        assert "Your Assemblies" in response.text

    def test_protected_page_redirects_when_not_logged_in(self, client: FlaskClient) -> None:
        response = client.get("/dashboard")
        assert response.status_code == 302
        assert "login" in response.location

    def test_protected_page_accessible_when_logged_in(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 200

    def test_session_persistence_across_requests(self, logged_in_user: FlaskClient) -> None:
        for _ in range(3):
            response = logged_in_user.get("/dashboard")
            assert response.status_code == 200


class TestCacheHeaders:
    """Cache-Control middleware on authenticated vs unauthenticated pages."""

    def test_public_page_allows_caching_when_logged_out(self, client: FlaskClient) -> None:
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert "Cache-Control" not in response.headers or "no-cache" not in response.headers.get("Cache-Control", "")
        assert "Pragma" not in response.headers or response.headers.get("Pragma") != "no-cache"
        assert "Expires" not in response.headers or response.headers.get("Expires") != "0"

    def test_dashboard_has_no_cache_headers_when_logged_in(self, logged_in_user: FlaskClient) -> None:
        response = logged_in_user.get("/dashboard")
        assert response.status_code == 200
        cache_control = response.headers.get("Cache-Control", "")
        assert "no-cache" in cache_control or "no-store" in cache_control

    def test_dashboard_redirects_when_logged_out(self, client: FlaskClient) -> None:
        response = client.get("/dashboard")
        assert response.status_code == 302
        assert "login" in response.location
        assert "Cache-Control" not in response.headers or "no-cache" not in response.headers.get("Cache-Control", "")


class TestEmailConfirmation:
    """Two-step email confirmation GET/invalid/expired branches."""

    @pytest.fixture
    def unconfirmed_user_with_token(self, fake_store: FakeStore, valid_invite: UserInvite):
        """Create an unconfirmed user and return (user, token)."""
        with FakeUnitOfWork(store=fake_store) as uow:
            user, token = create_user(
                uow=uow,
                email="unconfirmed@example.com",
                password="securepassword123",  # pragma: allowlist secret
                invite_code=valid_invite.code,
            )
        return user.create_detached_copy(), token

    def test_confirm_email_get_shows_confirmation_page(self, client: FlaskClient, unconfirmed_user_with_token) -> None:
        """GET /auth/confirm-email/<token> shows a confirmation page with a form."""
        _, token = unconfirmed_user_with_token
        response = client.get(f"/auth/confirm-email/{token.token}")
        assert response.status_code == 200
        assert b"Confirm your email" in response.data
        assert b'method="POST"' in response.data or b"method=POST" in response.data

    def test_confirm_email_get_does_not_confirm_email(
        self, client: FlaskClient, fake_store: FakeStore, unconfirmed_user_with_token
    ) -> None:
        """GET alone must NOT confirm the email (scanner resistance)."""
        user, token = unconfirmed_user_with_token
        client.get(f"/auth/confirm-email/{token.token}")

        with FakeUnitOfWork(store=fake_store) as uow:
            fetched = uow.users.get(user.id)
            assert fetched.email_confirmed_at is None

    def test_confirm_email_get_invalid_token_redirects(self, client: FlaskClient) -> None:
        """GET with bad token redirects to login with error flash."""
        response = client.get("/auth/confirm-email/invalid-token-abc", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_confirm_email_get_expired_token_redirects(
        self, client: FlaskClient, fake_store: FakeStore, unconfirmed_user_with_token
    ) -> None:
        """GET with expired token redirects to login."""
        _, token = unconfirmed_user_with_token

        with FakeUnitOfWork(store=fake_store) as uow:
            db_token = uow.email_confirmation_tokens.get_by_token(token.token)
            past = datetime.now(UTC) - timedelta(hours=25)
            db_token.created_at = past
            db_token.expires_at = past + timedelta(hours=24)
            uow.commit()

        response = client.get(f"/auth/confirm-email/{token.token}", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_confirm_email_post_invalid_token_redirects(self, client: FlaskClient) -> None:
        """POST with bad token redirects to login."""
        response = client.post("/auth/confirm-email/invalid-token-abc", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]
