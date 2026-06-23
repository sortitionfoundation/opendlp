"""ABOUTME: End-to-end PostgreSQL happy-path smokes for two-factor authentication
ABOUTME: Behavioural coverage (invalid-code, backup-code login, regenerate) lives in tests/component/"""

import base64
import secrets

import pyotp
import pytest
from flask.testing import FlaskClient

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import two_factor_service
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from opendlp.service_layer.user_service import create_user
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def test_user(postgres_session_factory, temp_env_vars):
    """Create a test user without 2FA."""
    # Set up encryption key
    raw_key = secrets.token_bytes(32)
    test_key = base64.b64encode(raw_key).decode()
    temp_env_vars(TOTP_ENCRYPTION_KEY=test_key)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user, _ = create_user(
            uow,
            email="testuser@example.com",
            password="SecurePassword123!",  # pragma: allowlist secret
            first_name="Test",
            last_name="User",
            global_role=GlobalRole.USER,
        )

    # Confirm email so user can log in
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        user_obj = uow.users.get(user.id)
        user_obj.confirm_email()
        uow.commit()
        return user_obj.create_detached_copy()


@pytest.fixture
def logged_in_client(client: FlaskClient, test_user: User):
    """Return a client with the test user logged in."""
    # Login the user
    response = client.post(
        "/auth/login",
        data={
            "email": test_user.email,
            "password": "SecurePassword123!",  # pragma: allowlist secret
            "csrf_token": get_csrf_token(client, "/auth/login"),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    return client


class Test2FASetupFlow:
    """Test the complete 2FA setup workflow."""

    def test_setup_2fa_complete_flow(self, logged_in_client: FlaskClient):
        """Test the complete 2FA setup process from start to finish."""
        # Navigate to 2FA settings
        response = logged_in_client.get("/profile/2fa")
        assert response.status_code == 200
        assert b"Two-Factor Authentication" in response.data

        # Start 2FA setup
        response = logged_in_client.get("/profile/2fa/setup")
        assert response.status_code == 200
        assert b"Scan this QR code" in response.data or b"Set Up Two-Factor Authentication" in response.data

        # Extract the TOTP secret from the response
        # In a real implementation, we'd parse the QR code data or session
        # For now, we'll simulate by getting it from the session
        with logged_in_client.session_transaction() as session:
            totp_secret = session.get("totp_setup_secret")
            backup_codes = session.get("totp_setup_backup_codes")

        assert totp_secret is not None, "TOTP secret should be in session"
        assert backup_codes is not None, "Backup codes should be in session"
        assert len(backup_codes) == 8, "Should have 8 backup codes"

        # Generate a valid TOTP code
        totp = pyotp.TOTP(totp_secret)
        valid_code = totp.now()

        # Complete 2FA setup by verifying the code
        response = logged_in_client.post(
            "/profile/2fa/enable",
            data={
                "totp_code": valid_code,
                "csrf_token": get_csrf_token(logged_in_client, "/profile/2fa/enable"),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.headers["Location"] == "/profile/2fa"

        # Verify success message
        with logged_in_client.session_transaction() as session:
            flashes = session.get("_flashes", [])
            assert any("enabled successfully" in message.lower() for _, message in flashes)

        # Verify 2FA is now enabled
        response = logged_in_client.get("/profile/2fa")
        assert response.status_code == 200
        assert b"Enabled" in response.data or b"enabled" in response.data


class Test2FALoginFlow:
    """Test 2FA login workflows."""

    @pytest.fixture
    def user_with_2fa(self, postgres_session_factory, temp_env_vars):
        """Create a test user with 2FA already enabled."""
        # Set up encryption key
        raw_key = secrets.token_bytes(32)
        test_key = base64.b64encode(raw_key).decode()
        temp_env_vars(TOTP_ENCRYPTION_KEY=test_key)

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user, _ = create_user(
                uow,
                email="2fauser@example.com",
                password="SecurePassword123!",  # pragma: allowlist secret
                first_name="2FA",
                last_name="User",
                global_role=GlobalRole.USER,
            )
            user_id = user.id

        # Confirm email so user can log in
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user_obj = uow.users.get(user_id)
            user_obj.confirm_email()
            uow.commit()

        # Enable 2FA for the user
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, user_id)
            totp = pyotp.TOTP(totp_secret)
            valid_code = totp.now()
            two_factor_service.enable_2fa(uow, user_id, totp_secret, valid_code, backup_codes)

        return {
            "email": "2fauser@example.com",
            "password": "SecurePassword123!",  # pragma: allowlist secret
            "totp_secret": totp_secret,
            "backup_codes": backup_codes,
        }

    def test_login_with_2fa_totp_code(self, client: FlaskClient, user_with_2fa):
        """Test successful login with 2FA using TOTP code."""
        # Step 1: Submit email and password
        response = client.post(
            "/auth/login",
            data={
                "email": user_with_2fa["email"],
                "password": user_with_2fa["password"],
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=False,
        )

        # Should redirect to 2FA verification page
        assert response.status_code == 302
        assert "/auth/login/verify-2fa" in response.headers["Location"]

        # Step 2: Submit TOTP code
        totp = pyotp.TOTP(user_with_2fa["totp_secret"])
        valid_code = totp.now()

        response = client.post(
            "/auth/login/verify-2fa",
            data={
                "verification_code": valid_code,
                "csrf_token": get_csrf_token(client, "/auth/login/verify-2fa"),
            },
            follow_redirects=False,
        )

        # Should redirect to dashboard after successful verification
        assert response.status_code == 302
        assert response.headers["Location"] == "/dashboard"

        # Verify user is logged in
        with client.session_transaction() as session:
            assert "_user_id" in session


class Test2FAManagement:
    """Test 2FA management features like disabling."""

    @pytest.fixture
    def logged_in_2fa_user(self, client: FlaskClient, postgres_session_factory, temp_env_vars):
        """Return a client with a 2FA-enabled user logged in."""
        # Set up encryption key
        raw_key = secrets.token_bytes(32)
        test_key = base64.b64encode(raw_key).decode()
        temp_env_vars(TOTP_ENCRYPTION_KEY=test_key)

        # Create user
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user, _ = create_user(
                uow,
                email="manageduser@example.com",
                password="SecurePassword123!",  # pragma: allowlist secret
                first_name="Managed",
                last_name="User",
                global_role=GlobalRole.USER,
            )
            user_id = user.id

        # Confirm email so user can log in
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            user_obj = uow.users.get(user_id)
            user_obj.confirm_email()
            uow.commit()

        # Enable 2FA
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, user_id)
            totp = pyotp.TOTP(totp_secret)
            valid_code = totp.now()
            two_factor_service.enable_2fa(uow, user_id, totp_secret, valid_code, backup_codes)

        # Login the user
        client.post(
            "/auth/login",
            data={
                "email": "manageduser@example.com",
                "password": "SecurePassword123!",  # pragma: allowlist secret
                "csrf_token": get_csrf_token(client, "/auth/login"),
            },
            follow_redirects=False,
        )

        # Complete 2FA verification
        totp = pyotp.TOTP(totp_secret)
        valid_code = totp.now()
        client.post(
            "/auth/login/verify-2fa",
            data={
                "verification_code": valid_code,
                "csrf_token": get_csrf_token(client, "/auth/login/verify-2fa"),
            },
            follow_redirects=False,
        )

        return {"client": client, "totp_secret": totp_secret}

    def test_disable_2fa(self, logged_in_2fa_user):
        """Test disabling 2FA."""
        client = logged_in_2fa_user["client"]
        totp_secret = logged_in_2fa_user["totp_secret"]

        # Generate valid TOTP code
        totp = pyotp.TOTP(totp_secret)
        valid_code = totp.now()

        # Disable 2FA
        response = client.post(
            "/profile/2fa/disable",
            data={
                "totp_code": valid_code,
                "csrf_token": get_csrf_token(client, "/profile/2fa/disable"),
            },
            follow_redirects=False,
        )

        # Should redirect to 2FA settings
        assert response.status_code == 302
        assert "/profile/2fa" in response.headers["Location"]

        # Verify success message
        with client.session_transaction() as session:
            flashes = session.get("_flashes", [])
            assert any("disabled" in message.lower() for _, message in flashes)

        # Verify 2FA is now disabled
        response = client.get("/profile/2fa")
        assert response.status_code == 200
        assert b"Disabled" in response.data or b"Set up" in response.data
