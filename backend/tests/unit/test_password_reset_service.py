"""Unit tests for password reset service layer."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import password_reset_service
from opendlp.service_layer.exceptions import InvalidResetToken, PasswordTooWeak, RateLimitExceeded
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork


class FakePasswordResetTokenRepository:
    """Fake repository for testing."""

    def __init__(self):
        self._tokens = {}
        self._next_id = 1

    def add(self, token):
        if token.id is None:
            token.id = uuid.uuid4()
        self._tokens[token.id] = token

    def get(self, item_id):
        return self._tokens.get(item_id)

    def get_by_token(self, token_string):
        for token in self._tokens.values():
            if token.token == token_string:
                return token
        return None

    def count_recent_requests(self, user_id, since):
        count = 0
        for token in self._tokens.values():
            if token.user_id == user_id and token.created_at >= since:
                count += 1
        return count

    def delete_old_tokens(self, before):
        to_delete = [
            token_id for token_id, token in self._tokens.items()
            if token.created_at < before
        ]
        for token_id in to_delete:
            del self._tokens[token_id]
        return len(to_delete)

    def invalidate_user_tokens(self, user_id):
        count = 0
        for token in self._tokens.values():
            if token.user_id == user_id and token.is_valid():
                token.use()
                count += 1
        return count


class FakeUserRepository:
    """Fake user repository for testing."""

    def __init__(self):
        self._users = {}

    def add(self, user):
        self._users[user.id] = user

    def get(self, user_id):
        return self._users.get(user_id)

    def get_by_email(self, email):
        for user in self._users.values():
            if user.email == email:
                return user
        return None


class FakeUnitOfWork(AbstractUnitOfWork):
    """Fake Unit of Work for testing."""

    def __init__(self):
        self.users = FakeUserRepository()
        self.password_reset_tokens = FakePasswordResetTokenRepository()
        self.committed = False

    def commit(self):
        self.committed = True

    def rollback(self):
        pass


@pytest.fixture
def uow():
    """Create a fake unit of work."""
    return FakeUnitOfWork()


@pytest.fixture
def active_user(uow):
    """Create an active user with password."""
    user = User(
        email="test@example.com",
        global_role=GlobalRole.USER,
        password_hash="hashed_password",
        first_name="Test",
        last_name="User",
    )
    uow.users.add(user)
    return user


@pytest.fixture
def oauth_user(uow):
    """Create an OAuth user."""
    user = User(
        email="oauth@example.com",
        global_role=GlobalRole.USER,
        oauth_provider="google",
        oauth_id="12345",
    )
    uow.users.add(user)
    return user


@pytest.fixture
def inactive_user(uow):
    """Create an inactive user."""
    user = User(
        email="inactive@example.com",
        global_role=GlobalRole.USER,
        password_hash="hashed_password",
        is_active=False,
    )
    uow.users.add(user)
    return user


class TestRequestPasswordReset:
    """Tests for request_password_reset function."""

    def test_creates_token_for_valid_user(self, uow, active_user):
        """Should create token for valid user."""
        result = password_reset_service.request_password_reset(uow, active_user.email)

        assert result is True
        assert uow.committed is True

        # Check token was created
        tokens = list(uow.password_reset_tokens._tokens.values())
        assert len(tokens) == 1
        assert tokens[0].user_id == active_user.id

    def test_returns_true_for_nonexistent_email(self, uow):
        """Should return true but not create token for nonexistent email (anti-enumeration)."""
        result = password_reset_service.request_password_reset(uow, "nonexistent@example.com")

        assert result is True

        # Check no token was created
        tokens = list(uow.password_reset_tokens._tokens.values())
        assert len(tokens) == 0

    def test_returns_true_for_oauth_user(self, uow, oauth_user):
        """Should return true but not create token for OAuth user."""
        result = password_reset_service.request_password_reset(uow, oauth_user.email)

        assert result is True

        # Check no token was created
        tokens = list(uow.password_reset_tokens._tokens.values())
        assert len(tokens) == 0

    def test_returns_true_for_inactive_user(self, uow, inactive_user):
        """Should return true but not create token for inactive user."""
        result = password_reset_service.request_password_reset(uow, inactive_user.email)

        assert result is True

        # Check no token was created
        tokens = list(uow.password_reset_tokens._tokens.values())
        assert len(tokens) == 0

    def test_rate_limit_exceeded(self, uow, active_user):
        """Should raise RateLimitExceeded if too many requests."""
        # Create 3 recent tokens (hitting the limit)
        for _ in range(3):
            token = PasswordResetToken(user_id=active_user.id)
            uow.password_reset_tokens.add(token)

        with pytest.raises(RateLimitExceeded) as exc_info:
            password_reset_service.request_password_reset(uow, active_user.email)

        assert "rate limit" in str(exc_info.value).lower()

    def test_custom_expiry(self, uow, active_user):
        """Should use custom expiry hours."""
        password_reset_service.request_password_reset(uow, active_user.email, expires_in_hours=2)

        tokens = list(uow.password_reset_tokens._tokens.values())
        assert len(tokens) == 1

        # Check expiry is approximately 2 hours
        expected_expiry = tokens[0].created_at + timedelta(hours=2)
        assert abs((tokens[0].expires_at - expected_expiry).total_seconds()) < 1


class TestCheckRateLimit:
    """Tests for check_rate_limit function."""

    def test_allows_first_request(self, uow, active_user):
        """Should allow first request."""
        # Should not raise
        password_reset_service.check_rate_limit(uow, active_user.id)

    def test_blocks_after_limit(self, uow, active_user):
        """Should block after hitting rate limit."""
        # Create 3 tokens within the window
        for _ in range(3):
            token = PasswordResetToken(user_id=active_user.id)
            uow.password_reset_tokens.add(token)

        with pytest.raises(RateLimitExceeded):
            password_reset_service.check_rate_limit(uow, active_user.id)

    def test_allows_after_cooldown(self, uow, active_user):
        """Should allow request after cooldown period."""
        # Create old token (outside cooldown)
        old_time = datetime.now(UTC) - timedelta(minutes=10)
        token = PasswordResetToken(
            user_id=active_user.id,
            created_at=old_time,
            expires_at=old_time + timedelta(hours=1),
        )
        uow.password_reset_tokens.add(token)

        # Should not raise (old token is outside cooldown)
        password_reset_service.check_rate_limit(uow, active_user.id)

    def test_blocks_within_cooldown(self, uow, active_user):
        """Should block requests within cooldown period."""
        # Create very recent token
        token = PasswordResetToken(user_id=active_user.id)
        uow.password_reset_tokens.add(token)

        with pytest.raises(RateLimitExceeded):
            password_reset_service.check_rate_limit(uow, active_user.id)


class TestValidateResetToken:
    """Tests for validate_reset_token function."""

    def test_validates_good_token(self, uow, active_user):
        """Should validate a good token."""
        token = PasswordResetToken(user_id=active_user.id, token="valid-token")
        uow.password_reset_tokens.add(token)

        result = password_reset_service.validate_reset_token(uow, "valid-token")

        assert result is not None
        assert result.token == "valid-token"

    def test_rejects_nonexistent_token(self, uow):
        """Should reject nonexistent token."""
        with pytest.raises(InvalidResetToken, match="Token not found"):
            password_reset_service.validate_reset_token(uow, "nonexistent")

    def test_rejects_expired_token(self, uow, active_user):
        """Should reject expired token."""
        past_time = datetime.now(UTC) - timedelta(hours=2)
        token = PasswordResetToken(
            user_id=active_user.id,
            token="expired-token",
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),
        )
        uow.password_reset_tokens.add(token)

        with pytest.raises(InvalidResetToken, match="expired"):
            password_reset_service.validate_reset_token(uow, "expired-token")

    def test_rejects_used_token(self, uow, active_user):
        """Should reject used token."""
        token = PasswordResetToken(user_id=active_user.id, token="used-token")
        token.use()
        uow.password_reset_tokens.add(token)

        with pytest.raises(InvalidResetToken, match="already been used"):
            password_reset_service.validate_reset_token(uow, "used-token")

    def test_rejects_token_for_inactive_user(self, uow, inactive_user):
        """Should reject token if user is inactive."""
        token = PasswordResetToken(user_id=inactive_user.id, token="inactive-token")
        uow.password_reset_tokens.add(token)

        with pytest.raises(InvalidResetToken, match="inactive"):
            password_reset_service.validate_reset_token(uow, "inactive-token")


class TestResetPasswordWithToken:
    """Tests for reset_password_with_token function."""

    @patch("opendlp.service_layer.password_reset_service.validate_password_strength")
    @patch("opendlp.service_layer.password_reset_service.hash_password")
    def test_resets_password_with_valid_token(
        self, mock_hash, mock_validate, uow, active_user
    ):
        """Should reset password with valid token."""
        mock_validate.return_value = (True, "")
        mock_hash.return_value = "new_hashed_password"

        token = PasswordResetToken(user_id=active_user.id, token="valid-token")
        uow.password_reset_tokens.add(token)

        result = password_reset_service.reset_password_with_token(
            uow, "valid-token", "NewPassword123!"
        )

        assert result.id == active_user.id
        assert active_user.password_hash == "new_hashed_password"
        assert token.is_used()
        assert uow.committed

    @patch("opendlp.service_layer.password_reset_service.validate_password_strength")
    def test_rejects_weak_password(self, mock_validate, uow, active_user):
        """Should reject weak password."""
        mock_validate.return_value = (False, "Password too weak")

        token = PasswordResetToken(user_id=active_user.id, token="valid-token")
        uow.password_reset_tokens.add(token)

        with pytest.raises(PasswordTooWeak, match="Password too weak"):
            password_reset_service.reset_password_with_token(
                uow, "valid-token", "weak"
            )

        # Token should not be marked as used
        assert not token.is_used()

    @patch("opendlp.service_layer.password_reset_service.validate_password_strength")
    @patch("opendlp.service_layer.password_reset_service.hash_password")
    def test_invalidates_other_tokens(self, mock_hash, mock_validate, uow, active_user):
        """Should invalidate all other tokens for user."""
        mock_validate.return_value = (True, "")
        mock_hash.return_value = "new_hashed_password"

        # Create multiple tokens
        token1 = PasswordResetToken(user_id=active_user.id, token="token1")
        token2 = PasswordResetToken(user_id=active_user.id, token="token2")
        uow.password_reset_tokens.add(token1)
        uow.password_reset_tokens.add(token2)

        # Use token1 to reset password
        password_reset_service.reset_password_with_token(uow, "token1", "NewPassword123!")

        # Both tokens should be marked as used
        assert token1.is_used()
        assert token2.is_used()

    def test_rejects_invalid_token(self, uow):
        """Should reject invalid token."""
        with pytest.raises(InvalidResetToken, match="Token not found"):
            password_reset_service.reset_password_with_token(
                uow, "invalid-token", "NewPassword123!"
            )


class TestInvalidateUserTokens:
    """Tests for invalidate_user_tokens function."""

    def test_invalidates_all_active_tokens(self, uow, active_user):
        """Should invalidate all active tokens for user."""
        token1 = PasswordResetToken(user_id=active_user.id)
        token2 = PasswordResetToken(user_id=active_user.id)
        uow.password_reset_tokens.add(token1)
        uow.password_reset_tokens.add(token2)

        count = password_reset_service.invalidate_user_tokens(uow, active_user.id)

        assert count == 2
        assert token1.is_used()
        assert token2.is_used()

    def test_skips_already_used_tokens(self, uow, active_user):
        """Should skip already used tokens."""
        token1 = PasswordResetToken(user_id=active_user.id)
        token2 = PasswordResetToken(user_id=active_user.id)
        token1.use()  # Already used
        uow.password_reset_tokens.add(token1)
        uow.password_reset_tokens.add(token2)

        count = password_reset_service.invalidate_user_tokens(uow, active_user.id)

        assert count == 1  # Only token2 was invalidated

    def test_skips_expired_tokens(self, uow, active_user):
        """Should skip expired tokens."""
        past_time = datetime.now(UTC) - timedelta(hours=2)
        token1 = PasswordResetToken(
            user_id=active_user.id,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),
        )
        token2 = PasswordResetToken(user_id=active_user.id)
        uow.password_reset_tokens.add(token1)
        uow.password_reset_tokens.add(token2)

        count = password_reset_service.invalidate_user_tokens(uow, active_user.id)

        assert count == 1  # Only token2 was invalidated


class TestGetTokenByString:
    """Tests for get_token_by_string function."""

    def test_returns_token_if_found(self, uow, active_user):
        """Should return token if found."""
        token = PasswordResetToken(user_id=active_user.id, token="my-token")
        uow.password_reset_tokens.add(token)

        result = password_reset_service.get_token_by_string(uow, "my-token")

        assert result is not None
        assert result.token == "my-token"

    def test_returns_none_if_not_found(self, uow):
        """Should return None if token not found."""
        result = password_reset_service.get_token_by_string(uow, "nonexistent")

        assert result is None


class TestCleanupExpiredTokens:
    """Tests for cleanup_expired_tokens function."""

    def test_deletes_old_tokens(self, uow, active_user):
        """Should delete tokens older than specified days."""
        # Create old token
        old_time = datetime.now(UTC) - timedelta(days=35)
        old_token = PasswordResetToken(
            user_id=active_user.id,
            created_at=old_time,
            expires_at=old_time + timedelta(hours=1),
        )
        uow.password_reset_tokens.add(old_token)

        # Create recent token
        recent_token = PasswordResetToken(user_id=active_user.id)
        uow.password_reset_tokens.add(recent_token)

        count = password_reset_service.cleanup_expired_tokens(uow, days_old=30)

        assert count == 1
        assert uow.committed

        # Check recent token still exists
        assert uow.password_reset_tokens.get(recent_token.id) is not None

    def test_custom_cleanup_period(self, uow, active_user):
        """Should use custom cleanup period."""
        # Create token 10 days old
        old_time = datetime.now(UTC) - timedelta(days=10)
        old_token = PasswordResetToken(
            user_id=active_user.id,
            created_at=old_time,
            expires_at=old_time + timedelta(hours=1),
        )
        uow.password_reset_tokens.add(old_token)

        # Cleanup tokens older than 7 days
        count = password_reset_service.cleanup_expired_tokens(uow, days_old=7)

        assert count == 1
