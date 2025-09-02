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


@pytest.fixture
def valid_invite(postgres_session_factory):
    """Create a valid invite in the database."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        admin_user = create_user(uow, email="admin@example.com", global_role=GlobalRole.ADMIN, password="pass123=jvl")

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
        admin_user = create_user(uow, email="admin@example.com", global_role=GlobalRole.ADMIN, password="pass123=jvl")

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


class TestAuthenticationFlow:
    """Test complete authentication workflows."""

    def test_register_with_valid_invite_success(self, client: FlaskClient, valid_invite: UserInvite):
        """Test successful registration with valid invite."""
        # GET registration form
        response = client.get("/auth/register")
        assert response.status_code == 200
        assert b"Register" in response.data
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
                "csrf_token": self._get_csrf_token(client, "/auth/register"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"

        # Verify user is logged in (check session)
        with client.session_transaction() as session:
            assert "_user_id" in session
            assert any("Registration successful" in f[1] for f in session["_flashes"])

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
                "csrf_token": self._get_csrf_token(client, "/auth/register"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/register"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/register"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/register"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/login"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/login"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/login"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/login"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/login"),
            },
        )

        # Then logout
        response = client.get("/auth/logout", follow_redirects=True)
        assert response.status_code == 200

        # Verify user is logged out
        with client.session_transaction() as sess:
            assert "_user_id" not in sess

    def test_assemblies_view_access(self, client: FlaskClient, regular_user: User):
        """Test that assemblies view is accessible when logged in."""
        # Login first
        client.post(
            "/auth/login",
            data={
                "email": regular_user.email,
                "password": "userpass123",  # pragma: allowlist secret
                "csrf_token": self._get_csrf_token(client, "/auth/login"),
            },
        )

        # Access assemblies page
        response = client.get("/assemblies")
        assert response.status_code == 200
        assert b"Assemblies" in response.data or b"assemblies" in response.data

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
                "csrf_token": self._get_csrf_token(client, "/auth/login"),
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
                "csrf_token": self._get_csrf_token(client, "/auth/login"),
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

    def _get_csrf_token(self, client: FlaskClient, endpoint: str) -> str:
        """Helper to extract CSRF token from form."""
        _ = client.get(endpoint)
        # This is a simplified approach - actual implementation would parse HTML
        # and extract the CSRF token from the form
        # TODO: actually implement this properly - and make it shared between classes
        return "csrf_token_placeholder"  # Placeholder for now


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
                "csrf_token": self._get_csrf_token(client, "/auth/register"),
            },
        )

        assert response.status_code == 200  # Returns form with error

    def test_login_rate_limiting_basic(self, client: FlaskClient, regular_user: User):
        """Basic test for login rate limiting (if implemented)."""
        # This test assumes rate limiting might be implemented
        # Make multiple failed login attempts
        for _ in range(5):
            client.post(
                "/auth/login",
                data={
                    "email": regular_user.email,
                    "password": "wrongpassword",
                    "csrf_token": self._get_csrf_token(client, "/auth/login"),
                },
            )

        # TODO: This test would check for rate limiting behavior - there is no assert right now
        # The actual implementation may vary

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

    def _get_csrf_token(self, client: FlaskClient, endpoint: str) -> str:
        """Helper to extract CSRF token from form."""
        return "csrf_token_placeholder"  # Placeholder for now
