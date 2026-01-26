"""Integration tests for two-factor authentication setup flow."""

import base64
import secrets
import uuid

import pyotp
import pytest

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import two_factor_service
from opendlp.service_layer.two_factor_service import TwoFactorSetupError, TwoFactorVerificationError
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def test_user_password(sqlite_session_factory, temp_env_vars):
    """Create a test user with password authentication and set encryption key."""
    # Set up encryption key
    raw_key = secrets.token_bytes(32)
    test_key = base64.b64encode(raw_key).decode()
    temp_env_vars(TOTP_ENCRYPTION_KEY=test_key)

    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    email = f"testuser{secrets.token_urlsafe(3)}@example.com"
    with uow:
        user = User(
            email=email,
            global_role=GlobalRole.USER,
            password_hash="password_hash",  # pragma: allowlist secret
            first_name="Test",
            last_name="User",
        )
        uow.users.add(user)
        uow.commit()
        return user.id


@pytest.fixture
def test_user_oauth(sqlite_session_factory):
    """Create a test user with OAuth authentication."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    email = f"oauthuser{secrets.token_urlsafe(3)}@example.com"
    with uow:
        user = User(
            email=email,
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="google123",
            first_name="OAuth",
            last_name="User",
        )
        uow.users.add(user)
        uow.commit()
        return user.id


def test_full_2fa_setup_flow(sqlite_session_factory, test_user_password):
    """Test complete 2FA setup flow from initiation to enablement."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Step 1: Initiate 2FA setup
    totp_secret, qr_code_url, backup_codes = two_factor_service.setup_2fa(uow, test_user_password)

    # Verify setup returns valid data
    assert isinstance(totp_secret, str)
    assert len(totp_secret) == 32  # Base32 secret length
    assert qr_code_url.startswith("data:image/png;base64,")
    assert len(backup_codes) == 8
    assert all(len(code) == 9 for code in backup_codes)  # XXXX-XXXX format

    # Step 2: Generate valid TOTP code
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()

    # Step 3: Enable 2FA with valid code
    two_factor_service.enable_2fa(uow, test_user_password, totp_secret, valid_code, backup_codes)

    # Step 4: Verify 2FA is enabled in database
    with uow:
        user = uow.users.get(test_user_password)
        assert user.totp_enabled is True
        assert user.totp_secret_encrypted is not None
        assert user.totp_enabled_at is not None

    # Step 5: Verify backup codes were stored
    with uow:
        stored_codes = list(uow.user_backup_codes.get_codes_for_user(test_user_password))
        assert len(stored_codes) == 8
        assert all(not code.is_used() for code in stored_codes)

    # Step 6: Verify audit log entry
    with uow:
        audit_logs = list(uow.two_factor_audit_logs.get_logs_for_user(test_user_password))
        assert len(audit_logs) == 1
        assert audit_logs[0].action == "enabled"
        assert audit_logs[0].performed_by == test_user_password


def test_setup_fails_for_oauth_user(sqlite_session_factory, test_user_oauth):
    """Test that OAuth users cannot enable 2FA."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    with pytest.raises(TwoFactorSetupError, match="Cannot enable 2FA for OAuth users"):
        two_factor_service.setup_2fa(uow, test_user_oauth)


def test_enable_fails_with_invalid_code(sqlite_session_factory, test_user_password):
    """Test that enabling 2FA fails with invalid TOTP code."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Initiate setup
    totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, test_user_password)

    # Try to enable with invalid code
    with pytest.raises(TwoFactorVerificationError, match="Invalid authentication code"):
        two_factor_service.enable_2fa(uow, test_user_password, totp_secret, "000000", backup_codes)

    # Verify 2FA is still disabled
    with uow:
        user = uow.users.get(test_user_password)
        assert user.totp_enabled is False


def test_disable_2fa_flow(sqlite_session_factory, test_user_password):
    """Test disabling 2FA after it's enabled."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Enable 2FA first
    totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, test_user_password)
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()
    two_factor_service.enable_2fa(uow, test_user_password, totp_secret, valid_code, backup_codes)

    # Verify 2FA is enabled
    with uow:
        user = uow.users.get(test_user_password)
        assert user.totp_enabled is True

    # Disable 2FA with valid code
    new_code = totp.now()
    two_factor_service.disable_2fa(uow, test_user_password, new_code)

    # Verify 2FA is disabled
    with uow:
        user = uow.users.get(test_user_password)
        assert user.totp_enabled is False
        assert user.totp_secret_encrypted is None
        assert user.totp_enabled_at is None

    # Verify backup codes were deleted
    with uow:
        stored_codes = list(uow.user_backup_codes.get_codes_for_user(test_user_password))
        assert len(stored_codes) == 0

    # Verify audit logs
    with uow:
        audit_logs = list(uow.two_factor_audit_logs.get_logs_for_user(test_user_password))
        assert len(audit_logs) == 2
        actions = {log.action for log in audit_logs}
        assert actions == {"enabled", "disabled"}


def test_regenerate_backup_codes(sqlite_session_factory, test_user_password):
    """Test regenerating backup codes."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Enable 2FA
    totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, test_user_password)
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()
    two_factor_service.enable_2fa(uow, test_user_password, totp_secret, valid_code, backup_codes)

    # Get original backup codes
    with uow:
        original_codes = list(uow.user_backup_codes.get_codes_for_user(test_user_password))
        original_ids = {code.id for code in original_codes}

    # Regenerate backup codes
    new_code = totp.now()
    new_backup_codes = two_factor_service.regenerate_backup_codes(uow, test_user_password, new_code)

    # Verify new codes were generated
    assert len(new_backup_codes) == 8

    # Verify old codes were replaced
    with uow:
        stored_codes = list(uow.user_backup_codes.get_codes_for_user(test_user_password))
        assert len(stored_codes) == 8
        new_ids = {code.id for code in stored_codes}
        assert original_ids.isdisjoint(new_ids)  # No overlap between old and new

    # Verify audit log
    with uow:
        audit_logs = list(uow.two_factor_audit_logs.get_logs_for_user(test_user_password))
        regenerate_logs = [log for log in audit_logs if log.action == "backup_codes_regenerated"]
        assert len(regenerate_logs) == 1


def test_get_2fa_status(sqlite_session_factory, test_user_password):
    """Test getting 2FA status for a user."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Check status before enabling
    status = two_factor_service.get_2fa_status(uow, test_user_password)
    assert status["enabled"] is False
    assert status["enabled_at"] is None
    assert status["is_oauth_user"] is False
    assert status["backup_codes_remaining"] == 0

    # Enable 2FA
    totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, test_user_password)
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()
    two_factor_service.enable_2fa(uow, test_user_password, totp_secret, valid_code, backup_codes)

    # Check status after enabling
    status = two_factor_service.get_2fa_status(uow, test_user_password)
    assert status["enabled"] is True
    assert status["enabled_at"] is not None
    assert status["is_oauth_user"] is False
    assert status["backup_codes_remaining"] == 8


def test_cannot_setup_when_already_enabled(sqlite_session_factory, test_user_password):
    """Test that setup fails if 2FA is already enabled."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Enable 2FA
    totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, test_user_password)
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()
    two_factor_service.enable_2fa(uow, test_user_password, totp_secret, valid_code, backup_codes)

    # Try to setup again
    with pytest.raises(TwoFactorSetupError, match="2FA is already enabled"):
        two_factor_service.setup_2fa(uow, test_user_password)


def test_user_not_found(sqlite_session_factory):
    """Test that operations fail for non-existent users."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    fake_user_id = uuid.uuid4()

    with pytest.raises(TwoFactorSetupError, match="User not found"):
        two_factor_service.setup_2fa(uow, fake_user_id)

    with pytest.raises(TwoFactorSetupError, match="User not found"):
        two_factor_service.get_2fa_status(uow, fake_user_id)
