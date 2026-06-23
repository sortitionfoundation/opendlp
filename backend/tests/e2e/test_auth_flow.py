"""ABOUTME: End-to-end authentication flow tests
ABOUTME: Smoke tests for register/login/logout/confirm-email plus real Redis rate-limiting and CSRF"""

from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def valid_invite(postgres_session_factory):
    """Create a valid invite in the database."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        admin_user, _ = create_user(
            uow,
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password="pass123=jvl",  # pragma: allowlist secret
        )

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        invite = UserInvite(
            code="VALID123",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)
        detached_invite = invite.create_detached_copy()
        uow.commit()

        return detached_invite


@pytest.fixture(autouse=True)
def clear_login_rate_limit_keys(test_redis_client):
    """Flush the per-worker Redis database before and after each test."""
    test_redis_client.flushdb()
    yield
    test_redis_client.flushdb()


class TestAuthenticationFlow:
    """Test complete authentication workflows."""

    def test_register_with_valid_invite_success(self, client: FlaskClient, valid_invite: UserInvite):
        """Test successful registration with valid invite."""
        # GET registration form
        response = client.get("/auth/register")
        assert response.status_code == 200
        assert b"Create an Account" in response.data
        assert b"Invite Code" in response.data

        # POST registration data
        response = client.post(
            "/auth/register",
            data={
                "invite_code": valid_invite.code,
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@example.com",
                "password": "securepassword123",
                "password_confirm": "securepassword123",
                "accept_data_agreement": "y",
                "csrf_token": get_csrf_token(client, "/auth/register"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        # After registration with password, user needs to confirm email before logging in
        assert response.headers["Location"] == "/auth/login"

        # Verify user is NOT logged in yet (email not confirmed)
        with client.session_transaction() as session:
            assert "_user_id" not in session
            # Should have a flash message about checking email
            assert any(
                "check your email" in f[1].lower() or "confirm" in f[1].lower() for f in session.get("_flashes", [])
            )

    def test_login_success(self, client: FlaskClient, regular_user: User):
        """Test successful login."""
        # GET login form
        response = client.get("/auth/login")
        assert response.status_code == 200
        assert b"Sign in" in response.data

        # POST login credentials
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        # Should redirect to dashboard after login
        assert response.headers["Location"] == "/dashboard"

        # Verify user is logged in
        with client.session_transaction() as sess:
            assert "_user_id" in sess

    def test_logout_success(self, client: FlaskClient, regular_user: User):
        """Test successful logout."""
        # First login
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        # Then logout
        response = client.get("/auth/logout", follow_redirects=True)
        assert response.status_code == 200

        # Verify user is logged out
        with client.session_transaction() as sess:
            assert "_user_id" not in sess


class TestAuthenticationEdgeCases:
    """Test rate-limiting and CSRF aspects backed by real Redis."""

    def test_login_rate_limiting_blocks_after_max_failures(self, client: FlaskClient, regular_user: User):
        """Test that login is rate limited after too many failed attempts."""
        # Make 5 failed login attempts (the default per-email limit)
        for _ in range(5):
            response = client.post(
                "/auth/login",
                data={
                    "email": regular_user.email,
                    "password": "wrongpassword",
                    "csrf_token": get_csrf_token(client, "/auth/login"),
                },
            )
            assert response.status_code == 200

        # The 6th attempt should be blocked by rate limiting
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "wrongpassword",
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )
        assert response.status_code == 200
        assert b"Invalid email or password" in response.data

    def test_login_rate_limiting_blocks_correct_credentials_too(self, client: FlaskClient, regular_user: User):
        """Test that even correct credentials are rejected when rate limited."""
        # Exhaust the rate limit with wrong passwords
        for _ in range(5):
            client.post(
                "/auth/login",
                data={
                    "email": regular_user.email,
                    "password": "wrongpassword",
                    "csrf_token": get_csrf_token(client, "/auth/login"),
                },
            )

        # Now try with the correct password — should still be blocked
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=False,
        )
        # Should NOT redirect to dashboard (i.e. login is blocked)
        assert response.status_code == 200
        assert b"Invalid email or password" in response.data

    def test_login_rate_limiting_does_not_block_different_email(self, client: FlaskClient, admin_user):
        """Test that rate limiting one email doesn't block another."""
        # Exhaust rate limit for regular_user email
        for _ in range(5):
            client.post(
                "/auth/login",
                data={
                    "email": "ratelimited@example.com",
                    "password": "wrongpassword",
                    "csrf_token": get_csrf_token(client, "/auth/login"),
                },
            )

        # A different user should still be able to log in
        response = client.post(
            "/auth/login",
            data={
                "email": admin_user.email,
                "password": "adminpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"

    def test_login_succeeds_under_rate_limit(self, client: FlaskClient, regular_user: User):
        """Test that login works fine with fewer failures than the limit."""
        # Make 4 failed attempts (under the limit of 5)
        for _ in range(4):
            client.post(
                "/auth/login",
                data={
                    "email": regular_user.email,
                    "password": "wrongpassword",
                    "csrf_token": get_csrf_token(client, "/auth/login"),
                },
            )

        # Correct password on 5th attempt should succeed
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"

    def test_csrf_protection_enabled(self, client: FlaskClient, regular_user: User):
        """Test that CSRF protection rejects a login POST without a valid token."""
        # The test config disables CSRF for convenience; turn it on for this test
        # so the real CSRFProtect enforcement is exercised.
        client.application.config["WTF_CSRF_ENABLED"] = True

        # Submit valid credentials but omit the CSRF token entirely.
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                # No CSRF token
            },
            follow_redirects=False,
        )

        # The request must be rejected by the CSRF error handler (400), not
        # redirected to the dashboard, and the user must not be logged in.
        assert response.status_code == 400
        assert response.headers.get("Location") != "/dashboard"
        with client.session_transaction() as sess:
            assert "_user_id" not in sess


class TestEmailConfirmation:
    """Test two-step email confirmation flow (GET shows page, POST confirms)."""

    @pytest.fixture
    def unconfirmed_user_with_token(self, postgres_session_factory, valid_invite):
        """Create an unconfirmed user and return (user, token)."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user, token = create_user(
                uow=uow,
                email="unconfirmed@example.com",
                password="securepassword123",
                invite_code=valid_invite.code,
            )
        return user, token

    def test_confirm_email_post_confirms_and_redirects(
        self, client: FlaskClient, postgres_session_factory, unconfirmed_user_with_token
    ):
        """POST confirms email, logs user in, and redirects to dashboard."""
        user, token = unconfirmed_user_with_token
        response = client.post(
            f"/auth/confirm-email/{token.token}",
            data={"csrf_token": get_csrf_token(client, "/auth/login")},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"

        # Verify email is confirmed
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            fetched = uow.users.get(user.id)
            assert fetched.email_confirmed_at is not None

        # Verify user is logged in
        with client.session_transaction() as sess:
            assert "_user_id" in sess


class TestPasswordReset:
    """PG happy-path smokes for the forgot/reset password routes.

    Behavioural coverage (anti-enumeration, invalid/expired/used tokens, weak
    passwords, rate limiting) lives in tests/component/test_password_reset_routes.py.
    """

    def test_forgot_password_creates_token_and_redirects(
        self, client: FlaskClient, regular_user: User, postgres_session_factory
    ):
        """Requesting a reset for an active password user creates a token."""
        response = client.post(
            "/auth/forgot-password",
            data={
                "email": regular_user.email,
                "csrf_token": get_csrf_token(client, "/auth/forgot-password"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/auth/login" in response.location
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            tokens = list(uow.password_reset_tokens.get_active_tokens_for_user(regular_user.id))
            assert len(tokens) == 1

    def test_reset_password_with_valid_token_succeeds(
        self, client: FlaskClient, regular_user: User, postgres_session_factory
    ):
        """A valid token resets the password and the user can log in with it."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            token = PasswordResetToken(user_id=regular_user.id)
            token_str = token.token
            uow.password_reset_tokens.add(token)
            uow.commit()

        response = client.post(
            f"/auth/reset-password/{token_str}",
            data={
                "password": "FreshPassword789!",  # pragma: allowlist secret
                "password_confirm": "FreshPassword789!",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, f"/auth/reset-password/{token_str}"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/auth/login" in response.location
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assert uow.password_reset_tokens.get_by_token(token_str).is_used()

        login = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "FreshPassword789!",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=False,
        )
        assert login.status_code == 302
