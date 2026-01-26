"""Unit tests for User 2FA domain methods."""

from datetime import UTC, datetime

import pytest

from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole


class TestUser2FAMethods:
    """Test User domain model 2FA methods."""

    def test_enable_totp_sets_fields(self):
        """Test that enable_totp() sets the correct fields."""
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed_password",  # pragma: allowlist secret
        )

        encrypted_secret = "encrypted_secret_abc123"  # pragma: allowlist secret
        user.enable_totp(encrypted_secret)

        assert user.totp_secret_encrypted == encrypted_secret
        assert user.totp_enabled is True
        assert isinstance(user.totp_enabled_at, datetime)
        assert user.totp_enabled_at.tzinfo == UTC

    def test_enable_totp_raises_for_oauth_users(self):
        """Test that OAuth users cannot enable 2FA."""
        user = User(
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="12345",
        )

        with pytest.raises(ValueError, match="Cannot enable 2FA for OAuth users"):
            user.enable_totp("encrypted_secret")  # pragma: allowlist secret

    def test_disable_totp_clears_fields(self):
        """Test that disable_totp() clears all 2FA fields."""
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed_password",  # pragma: allowlist secret
            totp_secret_encrypted="encrypted_secret",  # pragma: allowlist secret
            totp_enabled=True,
            totp_enabled_at=datetime.now(UTC),
        )

        user.disable_totp()

        assert user.totp_secret_encrypted is None
        assert user.totp_enabled is False
        assert user.totp_enabled_at is None

    def test_requires_2fa_true_for_password_users_with_2fa(self):
        """Test that requires_2fa() returns True for password users with 2FA enabled."""
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed_password",  # pragma: allowlist secret
            totp_secret_encrypted="encrypted_secret",  # pragma: allowlist secret
            totp_enabled=True,
            totp_enabled_at=datetime.now(UTC),
        )

        assert user.requires_2fa() is True

    def test_requires_2fa_false_for_password_users_without_2fa(self):
        """Test that requires_2fa() returns False for password users without 2FA."""
        user = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed_password",  # pragma: allowlist secret
        )

        assert user.requires_2fa() is False

    def test_requires_2fa_false_for_oauth_users(self):
        """Test that requires_2fa() returns False for OAuth users (even if 2FA is enabled)."""
        user = User(
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="12345",
            totp_secret_encrypted="encrypted_secret",  # pragma: allowlist secret
            totp_enabled=True,
        )

        assert user.requires_2fa() is False

    def test_create_detached_copy_includes_2fa_fields(self):
        """Test that create_detached_copy() includes 2FA fields."""
        original = User(
            email="test@example.com",
            global_role=GlobalRole.USER,
            password_hash="hashed_password",  # pragma: allowlist secret
            totp_secret_encrypted="encrypted_secret",  # pragma: allowlist secret
            totp_enabled=True,
            totp_enabled_at=datetime.now(UTC),
        )

        copy = original.create_detached_copy()

        assert copy.totp_secret_encrypted == original.totp_secret_encrypted
        assert copy.totp_enabled == original.totp_enabled
        assert copy.totp_enabled_at == original.totp_enabled_at
        assert copy.id == original.id  # Same ID for detached copy
