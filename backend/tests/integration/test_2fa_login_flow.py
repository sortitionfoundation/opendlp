"""Integration tests for two-factor authentication login flow."""

import base64
import secrets
from datetime import UTC, datetime, timedelta

import pyotp
import pytest

from opendlp.domain.totp_attempts import TotpVerificationAttempt
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import totp_service, two_factor_service
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def test_user_with_2fa(sqlite_session_factory, temp_env_vars):
    """Create a test user with 2FA enabled."""
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
        user_id = user.id

    # Enable 2FA
    totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, user_id)
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()
    two_factor_service.enable_2fa(uow, user_id, totp_secret, valid_code, backup_codes)

    return {
        "user_id": user_id,
        "email": email,
        "totp_secret": totp_secret,
        "backup_codes": backup_codes,
    }


@pytest.fixture
def test_user_without_2fa(sqlite_session_factory):
    """Create a test user without 2FA."""
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


def test_login_with_2fa_totp_code(sqlite_session_factory, test_user_with_2fa):
    """Test successful login with 2FA using TOTP code."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    user_id = test_user_with_2fa["user_id"]
    totp_secret = test_user_with_2fa["totp_secret"]

    # Get user and verify 2FA is required
    with uow:
        user = uow.users.get(user_id)
        assert user.requires_2fa() is True

    # Generate valid TOTP code
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()

    # Verify the TOTP code
    with uow:
        user = uow.users.get(user_id)
        decrypted_secret = totp_service.decrypt_totp_secret(user.totp_secret_encrypted, user_id)
        is_valid = totp_service.verify_totp_code(decrypted_secret, valid_code)
        assert is_valid is True

        # Record successful attempt
        totp_service.record_totp_attempt(uow, user_id, success=True)

    # Verify attempt was recorded
    with uow:
        cutoff = datetime.now(UTC) - timedelta(minutes=1)
        attempts = list(uow.totp_attempts.get_attempts_since(user_id, cutoff))
        assert len(attempts) == 1
        assert attempts[0].success is True


def test_login_with_2fa_backup_code(sqlite_session_factory, test_user_with_2fa):
    """Test successful login with 2FA using backup code."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    user_id = test_user_with_2fa["user_id"]
    backup_codes = test_user_with_2fa["backup_codes"]

    # Get initial count of unused codes
    with uow:
        initial_count = totp_service.count_remaining_backup_codes(uow, user_id)
        assert initial_count == 8

    # Use first backup code
    backup_code = backup_codes[0]
    with uow:
        is_valid = totp_service.verify_backup_code(uow, user_id, backup_code)
        assert is_valid is True

    # Verify backup code was consumed
    with uow:
        remaining_count = totp_service.count_remaining_backup_codes(uow, user_id)
        assert remaining_count == 7

        # Verify the backup code cannot be reused
        is_valid_again = totp_service.verify_backup_code(uow, user_id, backup_code)
        assert is_valid_again is False


def test_login_with_2fa_invalid_code(sqlite_session_factory, test_user_with_2fa):
    """Test login failure with invalid TOTP code."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    user_id = test_user_with_2fa["user_id"]

    # Try with invalid code
    invalid_code = "000000"
    with uow:
        user = uow.users.get(user_id)
        decrypted_secret = totp_service.decrypt_totp_secret(user.totp_secret_encrypted, user_id)
        is_valid = totp_service.verify_totp_code(decrypted_secret, invalid_code)
        assert is_valid is False

        # Record failed attempt
        totp_service.record_totp_attempt(uow, user_id, success=False)

    # Verify failed attempt was recorded
    with uow:
        cutoff = datetime.now(UTC) - timedelta(minutes=1)
        attempts = list(uow.totp_attempts.get_attempts_since(user_id, cutoff))
        assert len(attempts) == 1
        assert attempts[0].success is False


def test_rate_limiting_after_failed_attempts(sqlite_session_factory, test_user_with_2fa):
    """Test rate limiting after 5 failed TOTP verification attempts."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    user_id = test_user_with_2fa["user_id"]

    # Check initial rate limit (should be allowed with 5 attempts remaining)
    with uow:
        is_allowed, attempts_remaining = totp_service.check_totp_rate_limit(uow, user_id)
        assert is_allowed is True
        assert attempts_remaining == 5

    # Record 5 failed attempts
    for _i in range(5):
        with uow:
            totp_service.record_totp_attempt(uow, user_id, success=False)

    # Check rate limit after 5 failed attempts (should be blocked)
    with uow:
        is_allowed, attempts_remaining = totp_service.check_totp_rate_limit(uow, user_id)
        assert is_allowed is False
        assert attempts_remaining == 0


def test_rate_limit_resets_after_time_window(sqlite_session_factory, test_user_with_2fa):
    """Test that rate limit resets after the 15-minute time window."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    user_id = test_user_with_2fa["user_id"]

    # Record 5 failed attempts with old timestamps (16 minutes ago)
    old_timestamp = datetime.now(UTC) - timedelta(minutes=16)
    with uow:
        for _i in range(5):
            old_attempt = TotpVerificationAttempt(user_id=user_id, success=False, attempted_at=old_timestamp)
            uow.totp_attempts.add(old_attempt)
        uow.commit()

    # Check rate limit (should be allowed since attempts are outside the 15-minute window)
    with uow:
        is_allowed, attempts_remaining = totp_service.check_totp_rate_limit(uow, user_id)
        assert is_allowed is True
        assert attempts_remaining == 5


def test_successful_attempt_does_not_count_toward_rate_limit(sqlite_session_factory, test_user_with_2fa):
    """Test that successful attempts don't count toward rate limit."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    user_id = test_user_with_2fa["user_id"]

    # Record 3 failed and 2 successful attempts
    with uow:
        for _i in range(3):
            totp_service.record_totp_attempt(uow, user_id, success=False)
        for _i in range(2):
            totp_service.record_totp_attempt(uow, user_id, success=True)

    # Check rate limit (should have 2 attempts remaining, not 0)
    with uow:
        is_allowed, attempts_remaining = totp_service.check_totp_rate_limit(uow, user_id)
        assert is_allowed is True
        assert attempts_remaining == 2


def test_user_without_2fa_does_not_require_verification(sqlite_session_factory, test_user_without_2fa):
    """Test that users without 2FA enabled don't require verification."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    with uow:
        user = uow.users.get(test_user_without_2fa)
        assert user.requires_2fa() is False
        assert user.totp_enabled is False


def test_oauth_user_bypasses_2fa(sqlite_session_factory):
    """Test that OAuth users bypass 2FA even if they somehow had it enabled."""
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

        # Verify OAuth user doesn't require 2FA
        assert user.requires_2fa() is False


def test_invalid_backup_code_format(sqlite_session_factory, test_user_with_2fa):
    """Test that invalid backup code format is rejected."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    user_id = test_user_with_2fa["user_id"]

    # Try with malformed backup code
    invalid_code = "INVALID"
    with uow:
        is_valid = totp_service.verify_backup_code(uow, user_id, invalid_code)
        assert is_valid is False


def test_2fa_verification_with_expired_codes(sqlite_session_factory, test_user_with_2fa):
    """Test that old TOTP codes are rejected."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    user_id = test_user_with_2fa["user_id"]
    totp_secret = test_user_with_2fa["totp_secret"]

    # Generate a code from 2 minutes ago (should be invalid)
    totp = pyotp.TOTP(totp_secret)
    # TOTP codes are valid for 30 seconds, with a window of 1 (90 seconds total)
    # So a code from 2 minutes ago should definitely be invalid
    old_timestamp = datetime.now(UTC) - timedelta(minutes=2)
    old_code = totp.at(old_timestamp)

    # Verify the old code is rejected
    with uow:
        user = uow.users.get(user_id)
        decrypted_secret = totp_service.decrypt_totp_secret(user.totp_secret_encrypted, user_id)
        is_valid = totp_service.verify_totp_code(decrypted_secret, old_code)
        assert is_valid is False
