"""Unit tests for email confirmation domain model."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from opendlp.domain.email_confirmation import EmailConfirmationToken, generate_confirmation_token


class TestGenerateConfirmationToken:
    """Tests for confirmation token generation."""

    def test_generates_url_safe_token(self):
        """Token should be URL-safe."""
        token = generate_confirmation_token()
        # URL-safe tokens should not contain problematic characters
        assert "/" not in token or "_" in token  # token_urlsafe uses - and _
        assert len(token) > 0

    def test_default_length_is_32(self):
        """Default token should be approximately 43 characters (32 bytes base64 encoded)."""
        token = generate_confirmation_token()
        # 32 bytes base64 encoded is approximately 43 characters
        assert len(token) >= 40  # Allow some variance

    def test_custom_length(self):
        """Custom length should work."""
        token = generate_confirmation_token(length=16)
        assert len(token) >= 20  # 16 bytes is approximately 21 characters

    def test_tokens_are_unique(self):
        """Each call should generate unique tokens."""
        tokens = [generate_confirmation_token() for _ in range(100)]
        assert len(set(tokens)) == 100  # All unique


class TestEmailConfirmationToken:
    """Tests for EmailConfirmationToken domain model."""

    def test_create_with_defaults(self):
        """Create token with default values."""
        user_id = uuid.uuid4()
        token = EmailConfirmationToken(user_id=user_id)

        assert token.id is not None
        assert token.user_id == user_id
        assert token.token is not None
        assert len(token.token) >= 40
        assert token.created_at is not None
        assert token.expires_at is not None
        assert token.used_at is None

    def test_default_expiry_is_24_hours(self):
        """Default expiry should be 24 hours."""
        user_id = uuid.uuid4()
        before = datetime.now(UTC)
        token = EmailConfirmationToken(user_id=user_id)
        datetime.now(UTC)

        expected_expiry = before + timedelta(hours=24)
        # Allow 1 second variance for test execution time
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 1

    def test_custom_expiry(self):
        """Custom expiry should work."""
        user_id = uuid.uuid4()
        token = EmailConfirmationToken(user_id=user_id, expires_in_hours=48)

        expected_expiry = token.created_at + timedelta(hours=48)
        assert token.expires_at == expected_expiry

    def test_invalid_expiry_raises_error(self):
        """Zero or negative expiry should raise error."""
        user_id = uuid.uuid4()

        with pytest.raises(ValueError, match="Expiry hours must be positive"):
            EmailConfirmationToken(user_id=user_id, expires_in_hours=0)

        with pytest.raises(ValueError, match="Expiry hours must be positive"):
            EmailConfirmationToken(user_id=user_id, expires_in_hours=-1)

    def test_is_valid_for_fresh_token(self):
        """Fresh token should be valid."""
        user_id = uuid.uuid4()
        token = EmailConfirmationToken(user_id=user_id)

        assert token.is_valid() is True
        assert token.is_expired() is False
        assert token.is_used() is False

    def test_is_expired_for_old_token(self):
        """Expired token should not be valid."""
        user_id = uuid.uuid4()
        past_time = datetime.now(UTC) - timedelta(hours=25)
        token = EmailConfirmationToken(
            user_id=user_id,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=24),
        )

        assert token.is_valid() is False
        assert token.is_expired() is True
        assert token.is_used() is False

    def test_is_used_after_use(self):
        """Used token should not be valid."""
        user_id = uuid.uuid4()
        token = EmailConfirmationToken(user_id=user_id)

        token.use()

        assert token.is_valid() is False
        assert token.is_used() is True
        assert token.used_at is not None

    def test_cannot_use_twice(self):
        """Using a token twice should raise error."""
        user_id = uuid.uuid4()
        token = EmailConfirmationToken(user_id=user_id)

        token.use()

        with pytest.raises(ValueError, match="Token has already been used"):
            token.use()

    def test_cannot_use_expired_token(self):
        """Cannot use expired token."""
        user_id = uuid.uuid4()
        past_time = datetime.now(UTC) - timedelta(hours=25)
        token = EmailConfirmationToken(
            user_id=user_id,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=24),
        )

        with pytest.raises(ValueError, match="Cannot use invalid token"):
            token.use()

    def test_time_until_expiry(self):
        """Time until expiry should be correct."""
        user_id = uuid.uuid4()
        token = EmailConfirmationToken(user_id=user_id, expires_in_hours=24)

        time_left = token.time_until_expiry()

        # Should be approximately 24 hours
        assert timedelta(hours=23, minutes=59) < time_left < timedelta(hours=24, minutes=1)

    def test_time_until_expiry_negative_for_expired(self):
        """Time until expiry should be negative for expired tokens."""
        user_id = uuid.uuid4()
        past_time = datetime.now(UTC) - timedelta(hours=25)
        token = EmailConfirmationToken(
            user_id=user_id,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=24),
        )

        time_left = token.time_until_expiry()

        assert time_left < timedelta(0)

    def test_equality(self):
        """Tokens with same ID should be equal."""
        user_id = uuid.uuid4()
        token_id = uuid.uuid4()

        token1 = EmailConfirmationToken(user_id=user_id, token_id=token_id, token="abc123")
        token2 = EmailConfirmationToken(user_id=user_id, token_id=token_id, token="xyz789")

        assert token1 == token2

    def test_inequality(self):
        """Tokens with different IDs should not be equal."""
        user_id = uuid.uuid4()

        token1 = EmailConfirmationToken(user_id=user_id)
        token2 = EmailConfirmationToken(user_id=user_id)

        assert token1 != token2

    def test_hash(self):
        """Tokens should be hashable."""
        user_id = uuid.uuid4()
        token = EmailConfirmationToken(user_id=user_id)

        # Should not raise
        hash(token)

        # Should be usable in sets
        token_set = {token}
        assert token in token_set

    def test_create_detached_copy(self):
        """Detached copy should have same values."""
        user_id = uuid.uuid4()
        original = EmailConfirmationToken(user_id=user_id)
        original.use()

        copy = original.create_detached_copy()

        assert copy.id == original.id
        assert copy.user_id == original.user_id
        assert copy.token == original.token
        assert copy.created_at == original.created_at
        assert copy.expires_at == original.expires_at
        assert copy.used_at == original.used_at
        assert copy.is_used() is True

    def test_custom_token_string(self):
        """Can create token with custom token string."""
        user_id = uuid.uuid4()
        custom_token = "my-custom-confirmation-token"

        token = EmailConfirmationToken(user_id=user_id, token=custom_token)

        assert token.token == custom_token
