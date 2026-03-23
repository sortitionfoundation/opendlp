"""ABOUTME: End-to-end authentication flow tests
ABOUTME: Tests complete user authentication journeys including registration, login, logout, and session management"""

from datetime import UTC, datetime, timedelta

import pytest
from flask.testing import FlaskClient

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


@pytest.fixture
def expired_invite(postgres_session_factory):
    """Create an expired invite in the database."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        admin_user, _ = create_user(
            uow,
            email="admin@example.com",
            global_role=GlobalRole.ADMIN,
            password="pass123=jvl",  # pragma: allowlist secret
        )

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        invite = UserInvite(
            code="EXPIRED123",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) - timedelta(hours=1),  # Expired
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

    def test_register_with_expired_invite_fails(self, client: FlaskClient, expired_invite: UserInvite):
        """Test registration fails with expired invite."""
        response = client.post(
            "/auth/register",
            data={
                "invite_code": expired_invite.code,
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@example.com",
                "password": "securepassword123",
                "password_confirm": "securepassword123",
                "accept_data_agreement": "y",
                "csrf_token": get_csrf_token(client, "/auth/register"),
            },
        )

        assert response.status_code == 200  # Returns form with error
        assert b"Invalid invite code" in response.data

    def test_register_with_invalid_invite_fails(self, client: FlaskClient):
        """Test registration fails with non-existent invite."""
        response = client.post(
            "/auth/register",
            data={
                "invite_code": "INVALID123",
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@example.com",
                "password": "securepassword123",
                "password_confirm": "securepassword123",
                "accept_data_agreement": "y",
                "csrf_token": get_csrf_token(client, "/auth/register"),
            },
        )

        assert response.status_code == 200  # Returns form with error
        # Should show error message (actual message may vary)

    def test_register_missing_fields_fails(self, client: FlaskClient, valid_invite: UserInvite):
        """Test registration fails with missing required fields."""
        response = client.post(
            "/auth/register",
            data={
                "invite_code": valid_invite.code,
                "first_name": "New",
                # Missing required fields
                "csrf_token": get_csrf_token(client, "/auth/register"),
            },
        )

        assert response.status_code == 200  # Returns form with error

    def test_register_password_mismatch_fails(self, client: FlaskClient, valid_invite: UserInvite):
        """Test registration fails when passwords don't match."""
        response = client.post(
            "/auth/register",
            data={
                "invite_code": valid_invite.code,
                "first_name": "New",
                "last_name": "User",
                "email": "newuser@example.com",
                "password": "securepassword123",
                "password_confirm": "differentpassword",
                "accept_data_agreement": "y",
                "csrf_token": get_csrf_token(client, "/auth/register"),
            },
        )

        assert response.status_code == 200  # Returns form with error
        assert b"Passwords do not match" in response.data or b"error" in response.data

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

    def test_login_invalid_credentials_fails(self, client: FlaskClient, regular_user: User):
        """Test login fails with invalid credentials."""
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "wrongpassword",
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        assert response.status_code == 200  # Returns form with error
        assert b"Invalid email or password" in response.data or b"error" in response.data

    def test_login_nonexistent_user_fails(self, client: FlaskClient):
        """Test login fails with non-existent user."""
        response = client.post(
            "/auth/login",
            data={
                "email": "nonexistent@example.com",
                "password": "somepassword",
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        assert response.status_code == 200  # Returns form with error

    def test_login_remember_me_functionality(self, client: FlaskClient, regular_user: User):
        """Test remember me functionality."""
        response = client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "remember_me": True,
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        #
        # Check that remember me cookie is set (implementation may vary)
        cookie = client.get_cookie("remember_token")
        assert cookie is not None
        assert isinstance(cookie.expires, datetime)
        assert cookie.expires > datetime.now(UTC) + timedelta(days=5)

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

    def test_dashboard_view_access(self, client: FlaskClient, regular_user: User):
        """Test that dashboard view is accessible when logged in."""
        # Login first
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        # Access assemblies page
        response = client.get("/dashboard")
        assert response.status_code == 200
        assert b"Assemblies" in response.data or b"assemblies" in response.data

    def test_root_page_shows_text_when_not_logged_in(self, client: FlaskClient):
        """Test that the root page shows the landing page if you are not logged in."""
        response = client.get("/")
        assert response.status_code == 200
        assert "Ready to participate" in response.text

    def test_root_page_redirects_when_logged_in(self, client: FlaskClient, regular_user: User):
        """Test that the root page redirects to the dashboard when you are logged in."""
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )
        response = client.get("/")
        assert response.status_code == 302  # Redirect to login
        assert "dashboard" in response.location
        response = client.get("/", follow_redirects=True)
        assert "Your Assemblies" in response.text

    def test_protected_page_redirects_when_not_logged_in(self, client: FlaskClient):
        """Test that protected pages redirect to login."""
        response = client.get("/dashboard")
        assert response.status_code == 302  # Redirect to login
        assert "login" in response.location

    def test_protected_page_accessible_when_logged_in(self, client: FlaskClient, regular_user: User):
        """Test that protected pages are accessible when logged in."""
        # Login first
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        # Access protected page
        response = client.get("/dashboard")
        assert response.status_code == 200

    def test_session_persistence_across_requests(self, client: FlaskClient, regular_user: User):
        """Test that session persists across multiple requests."""
        # Login
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        # Make multiple requests
        for _ in range(3):
            response = client.get("/dashboard")
            assert response.status_code == 200

    def test_registration_with_invite_code_in_url(self, client: FlaskClient, valid_invite: UserInvite):
        """Test registration form pre-fills invite code from URL."""
        response = client.get(f"/auth/register/{valid_invite.code}")
        assert response.status_code == 200
        assert valid_invite.code.encode() in response.data


class TestAuthenticationEdgeCases:
    """Test edge cases and security aspects of authentication."""

    def test_register_duplicate_email_fails(self, client: FlaskClient, regular_user: User, valid_invite: UserInvite):
        """Test registration fails when email already exists."""
        response = client.post(
            "/auth/register",
            data={
                "invite_code": valid_invite.code,
                "first_name": "Another",
                "last_name": "User",
                "email": regular_user.email,  # Already exists
                "password": "securepassword123",
                "password_confirm": "securepassword123",
                "csrf_token": get_csrf_token(client, "/auth/register"),
            },
        )

        assert response.status_code == 200  # Returns form with error

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

    def test_csrf_protection_enabled(self, client: FlaskClient):
        """Test that CSRF protection is working."""
        # Try to submit form without CSRF token
        _ = client.post(
            "/auth/login",
            data={
                "email": "test@example.com",
                "password": "password",
                # No CSRF token
            },
        )

        # TODO: Should fail due to CSRF protection (actual behavior may vary)
        # There is no assert in this test right now


class TestCacheHeaders:
    """Test cache control headers for authenticated vs unauthenticated pages."""

    def test_public_page_allows_caching_when_logged_out(self, client: FlaskClient):
        """Test that public pages don't have no-cache headers when user is logged out."""
        # Test the login page (public page accessible when logged out)
        response = client.get("/auth/login")
        assert response.status_code == 200

        # Public pages should not have no-cache headers
        assert "Cache-Control" not in response.headers or "no-cache" not in response.headers.get("Cache-Control", "")
        assert "Pragma" not in response.headers or response.headers.get("Pragma") != "no-cache"
        assert "Expires" not in response.headers or response.headers.get("Expires") != "0"

    def test_dashboard_has_no_cache_headers_when_logged_in(self, client: FlaskClient, regular_user: User):
        """Test that protected pages have no-cache headers when user is logged in."""
        # First login
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
        )

        # Test protected page (dashboard) when logged in
        response = client.get("/dashboard")
        assert response.status_code == 200

        # Protected pages should have no-cache headers when user is logged in
        cache_control = response.headers.get("Cache-Control", "")
        assert "no-cache" in cache_control or "no-store" in cache_control

    def test_dashboard_redirects_when_logged_out(self, client: FlaskClient):
        """Test that protected pages redirect when logged out (baseline behavior)."""
        response = client.get("/dashboard")
        assert response.status_code == 302  # Redirect to login
        assert "login" in response.location

        # When redirected, no special cache headers should be present
        assert "Cache-Control" not in response.headers or "no-cache" not in response.headers.get("Cache-Control", "")


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

    def test_confirm_email_get_shows_confirmation_page(self, client: FlaskClient, unconfirmed_user_with_token):
        """GET /auth/confirm-email/<token> shows a confirmation page with a form."""
        _, token = unconfirmed_user_with_token
        response = client.get(f"/auth/confirm-email/{token.token}")
        assert response.status_code == 200
        assert b"Confirm your email" in response.data
        assert b'method="POST"' in response.data or b"method=POST" in response.data

    def test_confirm_email_get_does_not_confirm_email(
        self, client: FlaskClient, postgres_session_factory, unconfirmed_user_with_token
    ):
        """GET alone must NOT confirm the email (scanner resistance)."""
        user, token = unconfirmed_user_with_token
        client.get(f"/auth/confirm-email/{token.token}")

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            fetched = uow.users.get(user.id)
            assert fetched.email_confirmed_at is None

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

    def test_confirm_email_get_invalid_token_redirects(self, client: FlaskClient):
        """GET with bad token redirects to login with error flash."""
        response = client.get("/auth/confirm-email/invalid-token-abc", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_confirm_email_get_expired_token_redirects(
        self, client: FlaskClient, postgres_session_factory, unconfirmed_user_with_token
    ):
        """GET with expired token redirects to login."""
        _, token = unconfirmed_user_with_token

        # Expire the token
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            db_token = uow.email_confirmation_tokens.get_by_token(token.token)
            past = datetime.now(UTC) - timedelta(hours=25)
            db_token.created_at = past
            db_token.expires_at = past + timedelta(hours=24)
            uow.commit()

        response = client.get(f"/auth/confirm-email/{token.token}", follow_redirects=False)
        assert response.status_code == 302
        assert "login" in response.headers["Location"]

    def test_confirm_email_post_invalid_token_redirects(self, client: FlaskClient):
        """POST with bad token redirects to login."""
        response = client.post(
            "/auth/confirm-email/invalid-token-abc",
            data={"csrf_token": get_csrf_token(client, "/auth/login")},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "login" in response.headers["Location"]
