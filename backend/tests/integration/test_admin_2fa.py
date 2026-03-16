"""Integration tests for admin two-factor authentication management."""

import base64
import secrets
from datetime import datetime

import pyotp
import pytest

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import two_factor_service
from opendlp.service_layer.two_factor_service import TwoFactorSetupError
from tests.fakes import FakeUnitOfWork


@pytest.fixture
def uow_with_admin_and_2fa_user(temp_env_vars):
    """Create a FakeUnitOfWork with an admin user and a user with 2FA enabled."""
    # Set up encryption key
    raw_key = secrets.token_bytes(32)
    test_key = base64.b64encode(raw_key).decode()
    temp_env_vars(TOTP_ENCRYPTION_KEY=test_key)

    uow = FakeUnitOfWork()

    # Create admin user
    admin_email = f"admin{secrets.token_urlsafe(3)}@example.com"
    with uow:
        admin = User(
            email=admin_email,
            global_role=GlobalRole.ADMIN,
            password_hash="password_hash",  # pragma: allowlist secret
            first_name="Admin",
            last_name="User",
        )
        uow.users.add(admin)
        uow.commit()
        admin_id = admin.id

    # Create regular user with 2FA enabled
    user_email = f"testuser{secrets.token_urlsafe(3)}@example.com"
    with uow:
        user = User(
            email=user_email,
            global_role=GlobalRole.USER,
            password_hash="password_hash",  # pragma: allowlist secret
            first_name="Test",
            last_name="User",
        )
        uow.users.add(user)
        uow.commit()
        user_id = user.id

    # Enable 2FA for the regular user
    totp_secret, _, backup_codes = two_factor_service.setup_2fa(uow, user_id)
    totp = pyotp.TOTP(totp_secret)
    valid_code = totp.now()
    two_factor_service.enable_2fa(uow, user_id, totp_secret, valid_code, backup_codes)

    return {
        "uow": uow,
        "admin_id": admin_id,
        "user_id": user_id,
        "user_email": user_email,
        "totp_secret": totp_secret,
    }


def test_admin_disable_2fa(uow_with_admin_and_2fa_user):
    """Test admin can disable 2FA for a user."""
    uow = uow_with_admin_and_2fa_user["uow"]
    user_id = uow_with_admin_and_2fa_user["user_id"]
    admin_id = uow_with_admin_and_2fa_user["admin_id"]

    # Verify 2FA is enabled
    with uow:
        user = uow.users.get(user_id)
        assert user.totp_enabled is True
        assert user.totp_secret_encrypted is not None

    # Admin disables 2FA
    with uow:
        two_factor_service.admin_disable_2fa(uow, user_id, admin_id)

    # Verify 2FA is disabled
    with uow:
        user = uow.users.get(user_id)
        assert user.totp_enabled is False
        assert user.totp_secret_encrypted is None

        # Verify all backup codes are deleted
        backup_codes = list(uow.user_backup_codes.get_unused_codes_for_user(user_id))
        assert len(backup_codes) == 0


def test_admin_disable_2fa_creates_audit_log(uow_with_admin_and_2fa_user):
    """Test that admin disabling 2FA creates an audit log entry."""
    uow = uow_with_admin_and_2fa_user["uow"]
    user_id = uow_with_admin_and_2fa_user["user_id"]
    admin_id = uow_with_admin_and_2fa_user["admin_id"]

    # Admin disables 2FA
    with uow:
        two_factor_service.admin_disable_2fa(uow, user_id, admin_id)

    # Verify audit log entry was created
    with uow:
        audit_logs = list(uow.two_factor_audit_logs.get_logs_for_user(user_id, limit=10))

        # Should have 2 logs: 'enabled' from setup and 'admin_disabled' from admin action
        assert len(audit_logs) >= 2

        # Most recent should be admin_disabled
        latest_log = audit_logs[0]
        assert latest_log.action == "admin_disabled"
        assert latest_log.performed_by == admin_id
        assert latest_log.user_id == user_id


def test_admin_cannot_disable_2fa_for_oauth_user(uow_with_admin_and_2fa_user):
    """Test that admin cannot disable 2FA for OAuth users."""
    uow = uow_with_admin_and_2fa_user["uow"]
    admin_id = uow_with_admin_and_2fa_user["admin_id"]
    email = f"oauthuser{secrets.token_urlsafe(3)}@example.com"

    # Create OAuth user with 2FA somehow enabled (edge case)
    with uow:
        user = User(
            email=email,
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="google123",
            first_name="OAuth",
            last_name="User",
        )
        # Manually set totp_enabled (shouldn't happen in real scenarios)
        user.totp_enabled = True
        uow.users.add(user)
        uow.commit()
        user_id = user.id

    # Attempt to disable 2FA should fail
    with pytest.raises(TwoFactorSetupError, match="Cannot disable 2FA for OAuth users"), uow:
        two_factor_service.admin_disable_2fa(uow, user_id, admin_id)


def test_admin_cannot_disable_2fa_when_not_enabled(uow_with_admin_and_2fa_user):
    """Test that admin cannot disable 2FA for users who don't have it enabled."""
    uow = uow_with_admin_and_2fa_user["uow"]
    admin_id = uow_with_admin_and_2fa_user["admin_id"]
    email = f"testuser{secrets.token_urlsafe(3)}@example.com"

    # Create user without 2FA
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

    # Attempt to disable 2FA should fail
    with pytest.raises(TwoFactorSetupError, match="2FA is not enabled for this user"), uow:
        two_factor_service.admin_disable_2fa(uow, user_id, admin_id)


def test_get_2fa_audit_logs(uow_with_admin_and_2fa_user):
    """Test retrieving 2FA audit logs for a user."""
    uow = uow_with_admin_and_2fa_user["uow"]
    user_id = uow_with_admin_and_2fa_user["user_id"]
    admin_id = uow_with_admin_and_2fa_user["admin_id"]

    # Perform several 2FA actions to generate audit logs
    # 1. Already have 'enabled' from fixture

    # 2. Admin disables 2FA
    with uow:
        two_factor_service.admin_disable_2fa(uow, user_id, admin_id)

    # Get audit logs and verify while still in session
    with uow:
        audit_logs = two_factor_service.get_2fa_audit_logs(uow, user_id, limit=10)

        # Verify we got logs in correct order (most recent first)
        assert len(audit_logs) >= 2
        assert audit_logs[0].action == "admin_disabled"
        assert audit_logs[1].action == "enabled"

        # Verify log details
        assert audit_logs[0].user_id == user_id
        assert audit_logs[0].performed_by == admin_id
        assert audit_logs[1].user_id == user_id
        assert audit_logs[1].performed_by == user_id  # User enabled it themselves


def test_get_2fa_audit_logs_respects_limit(uow_with_admin_and_2fa_user):
    """Test that get_2fa_audit_logs respects the limit parameter."""
    uow = uow_with_admin_and_2fa_user["uow"]
    user_id = uow_with_admin_and_2fa_user["user_id"]

    # We already have 1 log entry from the fixture (enabled)
    # Get with limit=1 and verify while still in session
    with uow:
        audit_logs = two_factor_service.get_2fa_audit_logs(uow, user_id, limit=1)

        assert len(audit_logs) == 1
        assert audit_logs[0].action == "enabled"


def test_get_2fa_status_includes_correct_info(uow_with_admin_and_2fa_user):
    """Test that get_2fa_status returns correct information."""
    uow = uow_with_admin_and_2fa_user["uow"]
    user_id = uow_with_admin_and_2fa_user["user_id"]

    with uow:
        status = two_factor_service.get_2fa_status(uow, user_id)

    assert status["enabled"] is True
    assert status["enabled_at"] is not None
    assert isinstance(status["enabled_at"], datetime)
    assert status["is_oauth_user"] is False
    assert status["backup_codes_remaining"] == 8


def test_get_2fa_status_for_oauth_user():
    """Test that get_2fa_status works correctly for OAuth users."""
    uow = FakeUnitOfWork()
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
        user_id = user.id

    with uow:
        status = two_factor_service.get_2fa_status(uow, user_id)

    assert status["enabled"] is False
    assert status["enabled_at"] is None
    assert status["is_oauth_user"] is True
    assert status["backup_codes_remaining"] == 0
