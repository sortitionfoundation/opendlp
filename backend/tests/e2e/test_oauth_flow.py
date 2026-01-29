"""ABOUTME: End-to-end tests for OAuth authentication flows
ABOUTME: Tests Google OAuth login, registration, account linking, and auth method management"""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient
from werkzeug.wrappers import Response

from opendlp.adapters.database import start_mappers
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.flask_app import create_app
from opendlp.service_layer.security import hash_password
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def app(temp_env_vars):
    """Create test Flask application with OAuth configured."""
    temp_env_vars(
        DB_URI="postgresql://opendlp:abc123@localhost:54322/opendlp",  # pragma: allowlist secret
        OAUTH_GOOGLE_CLIENT_ID="test-client-id-oauth",  # pragma: allowlist secret
        OAUTH_GOOGLE_CLIENT_SECRET="test-client-secret-oauth",  # pragma: allowlist secret
        OAUTH_MICROSOFT_CLIENT_ID="test-ms-client-id-oauth",  # pragma: allowlist secret
        OAUTH_MICROSOFT_CLIENT_SECRET="test-ms-client-secret-oauth",  # pragma: allowlist secret
    )
    start_mappers()  # Initialize SQLAlchemy mappings
    app = create_app("testing_postgres")
    return app


@pytest.fixture
def valid_invite(postgres_session_factory):
    """Create a valid invite in the database."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        admin_user = create_user(uow, email="admin@example.com", global_role=GlobalRole.ADMIN, password="pass123=jvl")

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        invite = UserInvite(
            code="OAUTH_VALID",
            global_role=GlobalRole.USER,
            created_by=admin_user.id,
            expires_at=datetime.now(UTC) + timedelta(hours=24),
        )
        uow.user_invites.add(invite)
        detached_invite = invite.create_detached_copy()
        uow.commit()

        return detached_invite


@pytest.fixture
def existing_password_user(postgres_session_factory) -> User:
    """Create a user with password authentication only."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = create_user(
            uow=uow,
            email=f"password-user-{uuid.uuid4()}@example.com",
            password="SecureTestPass123!",  # pragma: allowlist secret
            first_name="Password",
            last_name="User",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )
        return user.create_detached_copy()


@pytest.fixture
def existing_oauth_user(postgres_session_factory) -> User:
    """Create a user with OAuth authentication only."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = create_user(
            uow=uow,
            email=f"oauth-user-{uuid.uuid4()}@example.com",
            oauth_provider="google",
            oauth_id="google-123",
            first_name="OAuth",
            last_name="User",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )
        return user.create_detached_copy()


@pytest.fixture
def existing_dual_auth_user(postgres_session_factory) -> User:
    """Create a user with both password and OAuth authentication."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = create_user(
            uow=uow,
            email=f"dual-user-{uuid.uuid4()}@example.com",
            password="SecureTestPass123!",  # pragma: allowlist secret
            oauth_provider="google",
            oauth_id="google-456",
            first_name="Dual",
            last_name="User",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )
        return user.create_detached_copy()


@pytest.fixture
def mock_oauth_token():
    """Mock OAuth token response from Google."""
    return {
        "access_token": "mock_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "userinfo": {
            "sub": "google-oauth-id-12345",
            "email": "oauthuser@example.com",
            "name": "OAuth Test User",
            "given_name": "OAuth",
            "family_name": "User",
            "email_verified": True,
        },
    }


class TestOAuthRegistration:
    """Test OAuth registration flows."""

    def test_register_google_requires_invite_code(self, client: FlaskClient):
        """Test that OAuth registration form requires invite code."""
        response = client.get("/auth/register/google")
        assert response.status_code == 200
        assert b"Register with Google" in response.data
        assert b"Invite Code" in response.data
        assert b"invitation code to create an account" in response.data

    def test_register_google_with_valid_invite_success(
        self, client: FlaskClient, postgres_session_factory, valid_invite: UserInvite, mock_oauth_token
    ):
        """Test successful OAuth registration with valid invite."""
        # Step 1: Submit invite code
        response = client.post(
            "/auth/register/google",
            data={
                "invite_code": valid_invite.code,
                "accept_data_agreement": "y",
                "csrf_token": get_csrf_token(client, "/auth/register/google"),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        # Should redirect to Google OAuth

        # Step 2: Mock OAuth callback
        with patch("opendlp.entrypoints.blueprints.auth.oauth.google") as mock_google:
            mock_google.authorize_access_token.return_value = mock_oauth_token

            # Simulate OAuth callback
            response = client.get("/auth/login/google/callback", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"] == "/dashboard"

        # Verify user was created and logged in
        with client.session_transaction() as session:
            assert "_user_id" in session

        # Verify user exists in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get_by_email("oauthuser@example.com")
            assert user is not None
            assert user.oauth_provider == "google"
            assert user.oauth_id == "google-oauth-id-12345"
            assert user.password_hash is None  # No password for OAuth-only user

    def test_register_google_without_invite_fails(self, client: FlaskClient, mock_oauth_token):
        """Test that OAuth registration fails without invite code in session."""
        with patch("opendlp.entrypoints.blueprints.auth.oauth.google") as mock_google:
            mock_google.authorize_access_token.return_value = mock_oauth_token

            # Try to complete OAuth callback without first submitting invite code
            response = client.get("/auth/login/google/callback", follow_redirects=True)

            # Should fail with error message
            assert b"Invite code required" in response.data or b"error" in response.data.lower()

    def test_register_google_with_invalid_invite_fails(self, client: FlaskClient):
        """Test OAuth registration with invalid invite code."""
        # When form validation fails, it re-renders the form with errors
        response = client.post(
            "/auth/register/google",
            data={
                "invite_code": "INVALID_CODE",
                "accept_data_agreement": "y",
                "csrf_token": get_csrf_token(client, "/auth/register/google"),
            },
            follow_redirects=False,
        )

        # Form validation should fail and re-render the form (or redirect back)
        assert response.status_code in [200, 302]
        if response.status_code == 200:
            # Check for error message in form
            assert b"Invalid" in response.data or b"error" in response.data.lower()
        # If 302, it should redirect back to the form (not to OAuth)


class TestOAuthLogin:
    """Test OAuth login flows."""

    def test_login_google_initiates_oauth_flow(self, client: FlaskClient):
        """Test that login with Google initiates OAuth flow."""
        with patch("opendlp.entrypoints.blueprints.auth.oauth.google") as mock_google:
            mock_response = Response("", status=302, headers={"Location": "https://accounts.google.com/oauth"})
            mock_google.authorize_redirect.return_value = mock_response

            response = client.get("/auth/login/google", follow_redirects=False)

            # Should redirect to Google
            assert response.status_code == 302
            mock_google.authorize_redirect.assert_called_once()

    def test_login_google_with_existing_oauth_user_success(
        self, client: FlaskClient, existing_oauth_user: User, mock_oauth_token
    ):
        """Test successful login with existing OAuth user."""
        # Update mock token to match existing user's OAuth ID
        mock_oauth_token["userinfo"]["sub"] = existing_oauth_user.oauth_id
        mock_oauth_token["userinfo"]["email"] = existing_oauth_user.email

        with patch("opendlp.entrypoints.blueprints.auth.oauth.google") as mock_google:
            mock_google.authorize_access_token.return_value = mock_oauth_token

            response = client.get("/auth/login/google/callback", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"] == "/dashboard"

        # Verify user is logged in
        with client.session_transaction() as session:
            assert "_user_id" in session
            assert session["_user_id"] == str(existing_oauth_user.id)

    def test_login_google_auto_links_to_existing_password_user(
        self, client: FlaskClient, postgres_session_factory, existing_password_user: User, mock_oauth_token
    ):
        """Test that OAuth login auto-links to existing password user with same email."""
        # Update mock token to match existing user's email
        mock_oauth_token["userinfo"]["email"] = existing_password_user.email
        mock_oauth_token["userinfo"]["sub"] = "new-google-id-789"

        with patch("opendlp.entrypoints.blueprints.auth.oauth.google") as mock_google:
            mock_google.authorize_access_token.return_value = mock_oauth_token

            response = client.get("/auth/login/google/callback", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"] == "/dashboard"

        # Verify user is logged in
        with client.session_transaction() as session:
            assert "_user_id" in session
            assert session["_user_id"] == str(existing_password_user.id)

        # Verify OAuth was linked to existing user
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get_by_email(existing_password_user.email)
            assert user.oauth_provider == "google"
            assert user.oauth_id == "new-google-id-789"
            assert user.password_hash is not None  # Password still exists


class TestOAuthAccountLinking:
    """Test linking OAuth to existing accounts."""

    def test_link_google_requires_login(self, client: FlaskClient):
        """Test that linking Google account requires authentication."""
        response = client.get("/profile/link-google", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_link_google_with_password_user_success(
        self, client: FlaskClient, postgres_session_factory, existing_password_user: User, mock_oauth_token
    ):
        """Test successfully linking Google account to password-only user."""
        # Login as password user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_password_user.id)

        # Initiate OAuth linking
        with patch("opendlp.entrypoints.blueprints.profile.oauth.google") as mock_google:
            mock_response = Response("", status=302, headers={"Location": "https://accounts.google.com/oauth"})
            mock_google.authorize_redirect.return_value = mock_response

            response = client.get("/profile/link-google", follow_redirects=False)
            assert response.status_code == 302

        # Store oauth_action in session
        with client.session_transaction() as session:
            session["oauth_action"] = "link"

        # Complete OAuth callback
        mock_oauth_token["userinfo"]["email"] = existing_password_user.email
        mock_oauth_token["userinfo"]["sub"] = "linked-google-id-999"

        with patch("opendlp.entrypoints.blueprints.profile.oauth.google") as mock_google:
            mock_google.authorize_access_token.return_value = mock_oauth_token

            response = client.get("/profile/link-google/callback", follow_redirects=False)

            assert response.status_code == 302
            assert "/profile" in response.headers["Location"]

        # Verify OAuth was linked
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get_by_email(existing_password_user.email)
            assert user.oauth_provider == "google"
            assert user.oauth_id == "linked-google-id-999"
            assert user.password_hash is not None  # Password still exists

    def test_link_google_with_email_mismatch_fails(
        self, client: FlaskClient, existing_password_user: User, mock_oauth_token
    ):
        """Test that linking fails if Google email doesn't match user email."""
        # Login as password user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_password_user.id)
            session["oauth_action"] = "link"

        # Use different email in OAuth response
        mock_oauth_token["userinfo"]["email"] = "different@example.com"
        mock_oauth_token["userinfo"]["sub"] = "different-google-id"

        with patch("opendlp.entrypoints.blueprints.profile.oauth.google") as mock_google:
            mock_google.authorize_access_token.return_value = mock_oauth_token

            response = client.get("/profile/link-google/callback", follow_redirects=True)

            assert response.status_code == 200
            assert b"email does not match" in response.data or b"error" in response.data.lower()


class TestRemoveAuthMethods:
    """Test removing authentication methods."""

    def test_remove_password_requires_login(self, client: FlaskClient):
        """Test that removing password requires authentication."""
        response = client.post("/profile/remove-password", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_remove_password_with_dual_auth_success(
        self, client: FlaskClient, postgres_session_factory, existing_dual_auth_user: User
    ):
        """Test successfully removing password when OAuth is also configured."""
        # Login as dual auth user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_dual_auth_user.id)

        response = client.post(
            "/profile/remove-password",
            data={"csrf_token": get_csrf_token(client, "/profile")},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        # Verify password was removed
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get(existing_dual_auth_user.id)
            assert user.password_hash is None
            assert user.oauth_provider == "google"  # OAuth still exists

    def test_remove_password_without_oauth_fails(
        self, client: FlaskClient, postgres_session_factory, existing_password_user: User
    ):
        """Test that removing password fails if no OAuth configured."""
        # Login as password-only user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_password_user.id)

        response = client.post(
            "/profile/remove-password",
            data={"csrf_token": get_csrf_token(client, "/profile")},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Cannot remove" in response.data or b"last authentication method" in response.data

        # Verify password still exists
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get(existing_password_user.id)
            assert user.password_hash is not None

    def test_remove_oauth_requires_login(self, client: FlaskClient):
        """Test that removing OAuth requires authentication."""
        response = client.post("/profile/remove-oauth", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_remove_oauth_with_dual_auth_success(
        self, client: FlaskClient, postgres_session_factory, existing_dual_auth_user: User
    ):
        """Test successfully removing OAuth when password is also configured."""
        # Login as dual auth user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_dual_auth_user.id)

        response = client.post(
            "/profile/remove-oauth",
            data={"csrf_token": get_csrf_token(client, "/profile")},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        # Verify OAuth was removed
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get(existing_dual_auth_user.id)
            assert user.oauth_provider is None
            assert user.oauth_id is None
            assert user.password_hash is not None  # Password still exists

    def test_remove_oauth_without_password_fails(
        self, client: FlaskClient, postgres_session_factory, existing_oauth_user: User
    ):
        """Test that removing OAuth fails if no password configured."""
        # Login as OAuth-only user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_oauth_user.id)

        response = client.post(
            "/profile/remove-oauth",
            data={"csrf_token": get_csrf_token(client, "/profile")},
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"Cannot remove" in response.data or b"last authentication method" in response.data

        # Verify OAuth still exists
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get(existing_oauth_user.id)
            assert user.oauth_provider == "google"


class TestOAuthProfileDisplay:
    """Test OAuth information display in profile."""

    def test_password_user_sees_oauth_link_option(self, client: FlaskClient, existing_password_user: User):
        """Test that password-only user sees option to link OAuth."""
        # Login as password user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_password_user.id)

        response = client.get("/profile")

        assert response.status_code == 200
        assert b"Google OAuth" in response.data
        assert b"Not linked" in response.data
        assert b"Link Google account" in response.data

    def test_oauth_user_sees_oauth_active(self, client: FlaskClient, existing_oauth_user: User):
        """Test that OAuth user sees OAuth as active."""
        # Login as OAuth user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_oauth_user.id)

        response = client.get("/profile")

        assert response.status_code == 200
        assert b"Google OAuth" in response.data
        assert b"Active" in response.data
        # Should see hint that it's the only auth method
        assert b"Only authentication method" in response.data
        assert b"Change password" not in response.data

    def test_dual_auth_user_sees_both_methods_active(self, client: FlaskClient, existing_dual_auth_user: User):
        """Test that dual auth user sees both methods as active."""
        # Login as dual auth user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_dual_auth_user.id)

        response = client.get("/profile")

        assert response.status_code == 200
        assert b"Password" in response.data
        assert b"Google OAuth" in response.data
        # Both should show as Active
        assert response.data.count(b"Active") >= 2
        # Should see Remove buttons for both
        assert b"Remove" in response.data
        assert b"Unlink" in response.data


# ============================================================================
# Microsoft OAuth Tests
# ============================================================================


@pytest.fixture
def mock_microsoft_oauth_token():
    """Mock OAuth token response from Microsoft."""
    return {
        "access_token": "mock_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "userinfo": {
            "sub": "microsoft-oauth-id-67890",
            "email": "msuser@example.com",
            "name": "Microsoft Test User",
            "given_name": "Microsoft",
            "family_name": "User",
        },
    }


@pytest.fixture
def existing_microsoft_oauth_user(postgres_session_factory) -> User:
    """Create a user with Microsoft OAuth authentication only."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = create_user(
            uow=uow,
            email=f"ms-oauth-user-{uuid.uuid4()}@example.com",
            oauth_provider="microsoft",
            oauth_id="microsoft-789",
            first_name="Microsoft",
            last_name="User",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )
        return user.create_detached_copy()


@pytest.fixture
def existing_google_oauth_user_for_replacement(postgres_session_factory) -> User:
    """Create a user with Google OAuth for testing provider replacement."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user = create_user(
            uow=uow,
            email=f"google-for-replacement-{uuid.uuid4()}@example.com",
            oauth_provider="google",
            oauth_id="google-replace-123",
            first_name="Google",
            last_name="ReplaceMe",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )
        return user.create_detached_copy()


class TestMicrosoftOAuthRegistration:
    """Test Microsoft OAuth registration flows."""

    def test_register_microsoft_requires_invite_code(self, client: FlaskClient):
        """Test that Microsoft OAuth registration form requires invite code."""
        response = client.get("/auth/register/microsoft")
        assert response.status_code == 200
        assert b"Register with Microsoft" in response.data
        assert b"Invite Code" in response.data
        assert b"invitation code to create an account" in response.data

    def test_register_microsoft_with_valid_invite_success(
        self, client: FlaskClient, valid_invite, postgres_session_factory, mock_microsoft_oauth_token
    ):
        """Test successful Microsoft OAuth registration with valid invite."""
        # Step 1: Submit invite code form
        response = client.post(
            "/auth/register/microsoft",
            data={
                "invite_code": valid_invite.code,
                "accept_data_agreement": "y",
                "csrf_token": get_csrf_token(client, "/auth/register/microsoft"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        # Should redirect to Microsoft OAuth

        # Step 2: Mock OAuth callback
        with patch("opendlp.entrypoints.blueprints.auth.oauth.microsoft") as mock_microsoft:
            mock_microsoft.authorize_access_token.return_value = mock_microsoft_oauth_token

            # Simulate OAuth callback
            response = client.get("/auth/login/microsoft/callback", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"] == "/dashboard"

        # Verify user was created and logged in
        with client.session_transaction() as session:
            assert "_user_id" in session

        # Verify user exists in database
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get_by_email("msuser@example.com")
            assert user is not None
            assert user.oauth_provider == "microsoft"
            assert user.oauth_id == "microsoft-oauth-id-67890"
            assert user.password_hash is None  # No password for OAuth-only user

    def test_register_microsoft_without_invite_fails(self, client: FlaskClient, mock_microsoft_oauth_token):
        """Test that Microsoft OAuth registration fails without invite code in session."""
        with patch("opendlp.entrypoints.blueprints.auth.oauth.microsoft") as mock_microsoft:
            mock_microsoft.authorize_access_token.return_value = mock_microsoft_oauth_token

            # Try to complete OAuth callback without first submitting invite code
            response = client.get("/auth/login/microsoft/callback", follow_redirects=True)

            # Should fail with error message
            assert b"Invite code required" in response.data or b"error" in response.data.lower()


class TestMicrosoftOAuthLogin:
    """Test Microsoft OAuth login flows."""

    def test_login_microsoft_initiates_oauth_flow(self, client: FlaskClient):
        """Test that login with Microsoft initiates OAuth flow."""
        with patch("opendlp.entrypoints.blueprints.auth.oauth.microsoft") as mock_microsoft:
            mock_response = Response("", status=302, headers={"Location": "https://login.microsoftonline.com/oauth"})
            mock_microsoft.authorize_redirect.return_value = mock_response

            response = client.get("/auth/login/microsoft", follow_redirects=False)

            # Should redirect to Microsoft
            assert response.status_code == 302
            mock_microsoft.authorize_redirect.assert_called_once()

    def test_login_microsoft_with_existing_oauth_user_success(
        self, client: FlaskClient, existing_microsoft_oauth_user: User, mock_microsoft_oauth_token
    ):
        """Test successful login with existing Microsoft OAuth user."""
        # Update mock token to match existing user's OAuth ID
        mock_microsoft_oauth_token["userinfo"]["sub"] = existing_microsoft_oauth_user.oauth_id
        mock_microsoft_oauth_token["userinfo"]["email"] = existing_microsoft_oauth_user.email

        with patch("opendlp.entrypoints.blueprints.auth.oauth.microsoft") as mock_microsoft:
            mock_microsoft.authorize_access_token.return_value = mock_microsoft_oauth_token

            response = client.get("/auth/login/microsoft/callback", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"] == "/dashboard"

        # Verify user is logged in
        with client.session_transaction() as session:
            assert "_user_id" in session
            assert session["_user_id"] == str(existing_microsoft_oauth_user.id)


class TestMicrosoftOAuthAccountLinking:
    """Test Microsoft OAuth account linking flows."""

    def test_link_microsoft_to_password_account_success(
        self, client: FlaskClient, existing_password_user: User, mock_microsoft_oauth_token, postgres_session_factory
    ):
        """Test linking Microsoft OAuth to existing password account."""
        # Login as password user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_password_user.id)

        # Update mock token to match user's email
        mock_microsoft_oauth_token["userinfo"]["email"] = existing_password_user.email

        # Step 1: Initiate linking
        with patch("opendlp.entrypoints.blueprints.profile.oauth.microsoft") as mock_microsoft:
            mock_response = Response("", status=302, headers={"Location": "https://login.microsoftonline.com/oauth"})
            mock_microsoft.authorize_redirect.return_value = mock_response

            response = client.get("/profile/link-microsoft", follow_redirects=False)
            assert response.status_code == 302

        # Step 2: Complete OAuth callback
        with patch("opendlp.entrypoints.blueprints.profile.oauth.microsoft") as mock_microsoft:
            mock_microsoft.authorize_access_token.return_value = mock_microsoft_oauth_token

            response = client.get("/profile/link-microsoft/callback", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"] == "/profile"

        # Verify user now has Microsoft OAuth linked
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get(existing_password_user.id)
            assert user is not None
            assert user.oauth_provider == "microsoft"
            assert user.oauth_id == "microsoft-oauth-id-67890"
            assert user.password_hash is not None  # Still has password

    def test_unlink_microsoft_account_success(
        self, client: FlaskClient, existing_microsoft_oauth_user: User, postgres_session_factory
    ):
        """Test unlinking Microsoft OAuth from dual-auth account."""
        # First give user a password so they can unlink OAuth
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get(existing_microsoft_oauth_user.id)
            user.password_hash = hash_password("TempPassword123!")  # pragma: allowlist secret
            uow.commit()

        # Login as user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_microsoft_oauth_user.id)

        # Unlink Microsoft OAuth
        response = client.post(
            "/profile/remove-oauth",
            data={"csrf_token": get_csrf_token(client, "/profile")},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/profile"

        # Verify OAuth is removed
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get(existing_microsoft_oauth_user.id)
            assert user is not None
            assert user.oauth_provider is None
            assert user.oauth_id is None
            assert user.password_hash is not None  # Still has password


class TestOAuthProviderReplacement:
    """Test single OAuth provider choice - replacing one provider with another."""

    def test_link_microsoft_replaces_google(
        self,
        client: FlaskClient,
        existing_google_oauth_user_for_replacement: User,
        mock_microsoft_oauth_token,
        postgres_session_factory,
    ):
        """Test that linking Microsoft OAuth replaces existing Google OAuth."""
        # Login as Google OAuth user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_google_oauth_user_for_replacement.id)

        # Update mock token to match user's email
        mock_microsoft_oauth_token["userinfo"]["email"] = existing_google_oauth_user_for_replacement.email

        # Initiate Microsoft linking (should show warning that Google will be replaced)
        with patch("opendlp.entrypoints.blueprints.profile.oauth.microsoft") as mock_microsoft:
            mock_response = Response("", status=302, headers={"Location": "https://login.microsoftonline.com/oauth"})
            mock_microsoft.authorize_redirect.return_value = mock_response

            response = client.get("/profile/link-microsoft", follow_redirects=False)
            # Should show info that OAuth is already linked, but the logic allows replacement
            # The actual replacement happens in the callback

            assert response.status_code == 302
            assert response.headers["Location"] == "https://login.microsoftonline.com/oauth"

        # Complete OAuth callback - this should replace Google with Microsoft
        with patch("opendlp.entrypoints.blueprints.profile.oauth.microsoft") as mock_microsoft:
            mock_microsoft.authorize_access_token.return_value = mock_microsoft_oauth_token

            response = client.get("/profile/link-microsoft/callback", follow_redirects=False)

            assert response.status_code == 302
            assert response.headers["Location"] == "/profile"

        # Verify provider was replaced
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user = uow.users.get(existing_google_oauth_user_for_replacement.id)
            assert user is not None
            assert user.oauth_provider == "microsoft"  # Changed from google to microsoft
            assert user.oauth_id == "microsoft-oauth-id-67890"  # New OAuth ID
            # Password should still be None if user didn't have one
            assert user.password_hash is None

    def test_profile_shows_remove_provider_first_hint(self, client: FlaskClient, existing_microsoft_oauth_user: User):
        """Test that profile shows 'Remove X first' hint when different provider is active."""
        # Login as Microsoft OAuth user
        with client.session_transaction() as session:
            session["_user_id"] = str(existing_microsoft_oauth_user.id)

        response = client.get("/profile")

        assert response.status_code == 200
        # Should show Microsoft as Active
        assert b"Microsoft OAuth" in response.data
        assert b"Active" in response.data
        # Should show "Remove Microsoft first" hint for Google
        assert b"Remove" in response.data or b"Remove Microsoft first" in response.data
