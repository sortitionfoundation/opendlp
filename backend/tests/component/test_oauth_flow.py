# ABOUTME: Component tests for OAuth-adjacent profile/register routes over a FakeUnitOfWork
# ABOUTME: Drives the real Flask routes + services against a seeded fake store, no provider call, no PostgreSQL

import uuid

import pytest
from flask.testing import FlaskClient

from opendlp.adapters import database
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.entrypoints.flask_app import create_app
from opendlp.service_layer.user_service import create_user
from tests.fakes import FakeStore, FakeUnitOfWork


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """Remove-auth services call SQLAlchemy flag_modified, which needs mapped classes."""
    database.start_mappers()


@pytest.fixture
def app(fake_store, monkeypatch):
    """OAuth-enabled component app so link/register routes behave."""
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_ID", "test-client-id-oauth")  # pragma: allowlist secret
    monkeypatch.setenv("OAUTH_GOOGLE_CLIENT_SECRET", "test-client-secret-oauth")  # pragma: allowlist secret
    monkeypatch.setenv("OAUTH_MICROSOFT_CLIENT_ID", "test-ms-client-id-oauth")  # pragma: allowlist secret
    monkeypatch.setenv("OAUTH_MICROSOFT_CLIENT_SECRET", "test-ms-client-secret-oauth")  # pragma: allowlist secret
    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def existing_password_user(fake_store: FakeStore) -> User:
    """A confirmed password-only user in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
            uow=uow,
            email=f"password-user-{uuid.uuid4()}@example.com",
            password="SecureTestPass123!",  # pragma: allowlist secret
            first_name="Password",
            last_name="User",
            global_role=GlobalRole.USER,
            accept_data_agreement=True,
        )

    with FakeUnitOfWork(store=fake_store) as uow:
        user_obj = uow.users.get(user.id)
        user_obj.confirm_email()
        uow.commit()
        return user_obj.create_detached_copy()


@pytest.fixture
def existing_oauth_user(fake_store: FakeStore) -> User:
    """An OAuth-only (Google) user in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
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
def existing_dual_auth_user(fake_store: FakeStore) -> User:
    """A user with both password and OAuth in the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        user, _ = create_user(
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


def _login(client: FlaskClient, user: User) -> None:
    with client.session_transaction() as session:
        session["_user_id"] = str(user.id)


class TestOAuthRegistrationForms:
    """OAuth registration GET forms and invalid-invite validation."""

    def test_register_google_requires_invite_code(self, client: FlaskClient):
        """OAuth registration form requires invite code."""
        response = client.get("/auth/register/google")
        assert response.status_code == 200
        assert b"Create an Account with Google" in response.data
        assert b"Invite Code" in response.data
        assert b"invitation code to create an account" in response.data

    def test_register_microsoft_requires_invite_code(self, client: FlaskClient):
        """Microsoft OAuth registration form requires invite code."""
        response = client.get("/auth/register/microsoft")
        assert response.status_code == 200
        assert b"Create an Account with Microsoft" in response.data
        assert b"Invite Code" in response.data
        assert b"invitation code to create an account" in response.data

    def test_register_google_with_invalid_invite_fails(self, client: FlaskClient):
        """Invalid invite re-renders the form without reaching OAuth."""
        response = client.post(
            "/auth/register/google",
            data={"invite_code": "INVALID_CODE", "accept_data_agreement": "y"},
            follow_redirects=False,
        )

        assert response.status_code in [200, 302]
        if response.status_code == 200:
            assert b"Invalid" in response.data or b"error" in response.data.lower()


class TestOAuthLoginRequired:
    """Login-required redirects for OAuth/profile auth routes."""

    def test_link_google_requires_login(self, client: FlaskClient):
        """Linking Google requires authentication."""
        response = client.get("/profile/link-google", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_remove_password_requires_login(self, client: FlaskClient):
        """Removing password requires authentication."""
        response = client.post("/profile/remove-password", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]

    def test_remove_oauth_requires_login(self, client: FlaskClient):
        """Removing OAuth requires authentication."""
        response = client.post("/profile/remove-oauth", follow_redirects=False)
        assert response.status_code == 302
        assert "/auth/login" in response.headers["Location"]


class TestRemoveAuthMethods:
    """Removing authentication methods (no provider call)."""

    def test_remove_password_with_dual_auth_success(
        self, client: FlaskClient, fake_store: FakeStore, existing_dual_auth_user: User
    ):
        """Removing password succeeds when OAuth is also configured."""
        _login(client, existing_dual_auth_user)

        response = client.post("/profile/remove-password", follow_redirects=False)

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        with FakeUnitOfWork(store=fake_store) as uow:
            user = uow.users.get(existing_dual_auth_user.id)
            assert user.password_hash is None
            assert user.oauth_provider == "google"

    def test_remove_password_without_oauth_fails(
        self, client: FlaskClient, fake_store: FakeStore, existing_password_user: User
    ):
        """Removing password fails if no OAuth configured."""
        _login(client, existing_password_user)

        response = client.post("/profile/remove-password", follow_redirects=True)

        assert response.status_code == 200
        assert b"Cannot remove" in response.data or b"last authentication method" in response.data

        with FakeUnitOfWork(store=fake_store) as uow:
            user = uow.users.get(existing_password_user.id)
            assert user.password_hash is not None

    def test_remove_oauth_with_dual_auth_success(
        self, client: FlaskClient, fake_store: FakeStore, existing_dual_auth_user: User
    ):
        """Removing OAuth succeeds when password is also configured."""
        _login(client, existing_dual_auth_user)

        response = client.post("/profile/remove-oauth", follow_redirects=False)

        assert response.status_code == 302
        assert "/profile" in response.headers["Location"]

        with FakeUnitOfWork(store=fake_store) as uow:
            user = uow.users.get(existing_dual_auth_user.id)
            assert user.oauth_provider is None
            assert user.oauth_id is None
            assert user.password_hash is not None

    def test_remove_oauth_without_password_fails(
        self, client: FlaskClient, fake_store: FakeStore, existing_oauth_user: User
    ):
        """Removing OAuth fails if no password configured."""
        _login(client, existing_oauth_user)

        response = client.post("/profile/remove-oauth", follow_redirects=True)

        assert response.status_code == 200
        assert b"Cannot remove" in response.data or b"last authentication method" in response.data

        with FakeUnitOfWork(store=fake_store) as uow:
            user = uow.users.get(existing_oauth_user.id)
            assert user.oauth_provider == "google"

    def test_unlink_microsoft_account_success(self, client: FlaskClient, fake_store: FakeStore):
        """Unlinking Microsoft OAuth from a dual-auth account succeeds."""
        with FakeUnitOfWork(store=fake_store) as uow:
            user, _ = create_user(
                uow=uow,
                email=f"ms-oauth-user-{uuid.uuid4()}@example.com",
                password="TempPassword123!",  # pragma: allowlist secret
                oauth_provider="microsoft",
                oauth_id="microsoft-789",
                first_name="Microsoft",
                last_name="User",
                global_role=GlobalRole.USER,
                accept_data_agreement=True,
            )
            ms_user = user.create_detached_copy()

        _login(client, ms_user)

        response = client.post("/profile/remove-oauth", follow_redirects=False)

        assert response.status_code == 302
        assert response.headers["Location"] == "/profile"

        with FakeUnitOfWork(store=fake_store) as uow:
            user = uow.users.get(ms_user.id)
            assert user.oauth_provider is None
            assert user.oauth_id is None
            assert user.password_hash is not None


class TestOAuthProfileDisplay:
    """OAuth information display in the profile page."""

    def test_password_user_sees_oauth_link_option(self, client: FlaskClient, existing_password_user: User):
        """Password-only user sees the option to link OAuth."""
        _login(client, existing_password_user)

        response = client.get("/profile")

        assert response.status_code == 200
        assert b"Google OAuth" in response.data
        assert b"Not linked" in response.data
        assert b"Link Google account" in response.data

    def test_oauth_user_sees_oauth_active(self, client: FlaskClient, existing_oauth_user: User):
        """OAuth user sees OAuth as the active method."""
        _login(client, existing_oauth_user)

        response = client.get("/profile")

        assert response.status_code == 200
        assert b"Google OAuth" in response.data
        assert b"Active" in response.data
        assert b"Only authentication method" in response.data
        assert b"Change password" not in response.data

    def test_dual_auth_user_sees_both_methods_active(self, client: FlaskClient, existing_dual_auth_user: User):
        """Dual-auth user sees both methods as active."""
        _login(client, existing_dual_auth_user)

        response = client.get("/profile")

        assert response.status_code == 200
        assert b"Password" in response.data
        assert b"Google OAuth" in response.data
        assert response.data.count(b"Active") >= 2
        assert b"Remove" in response.data
        assert b"Unlink" in response.data

    def test_profile_shows_remove_provider_first_hint(self, client: FlaskClient, fake_store: FakeStore):
        """Profile shows a 'Remove X first' hint when a different provider is active."""
        with FakeUnitOfWork(store=fake_store) as uow:
            user, _ = create_user(
                uow=uow,
                email=f"ms-oauth-user-{uuid.uuid4()}@example.com",
                oauth_provider="microsoft",
                oauth_id="microsoft-789",
                first_name="Microsoft",
                last_name="User",
                global_role=GlobalRole.USER,
                accept_data_agreement=True,
            )
            ms_user = user.create_detached_copy()

        _login(client, ms_user)

        response = client.get("/profile")

        assert response.status_code == 200
        assert b"Microsoft OAuth" in response.data
        assert b"Active" in response.data
        assert b"Remove" in response.data or b"Remove Microsoft first" in response.data
