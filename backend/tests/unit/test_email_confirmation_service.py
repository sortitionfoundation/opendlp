"""Unit tests for email confirmation service layer."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import email_confirmation_service
from opendlp.service_layer.exceptions import InvalidConfirmationToken, RateLimitExceeded
from opendlp.service_layer.unit_of_work import AbstractUnitOfWork

# ============================================================================
# Test-specific Fake Repositories
# ============================================================================
# NOTE: These fakes are intentionally kept here rather than in tests/fakes.py
# because they are simpler and more focused than the shared fakes. The shared
# FakeUnitOfWork includes 9+ repositories with complex dependencies, which would
# make these unit tests slower and harder to understand. These minimal fakes
# only implement what's needed for testing the email confirmation service in
# isolation, following the same pattern as test_password_reset_service.py.
# ============================================================================


class FakeEmailConfirmationTokenRepository:
    """Fake repository for testing."""

    def __init__(self):
        self._tokens = {}

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
        to_delete = [token_id for token_id, token in self._tokens.items() if token.created_at < before]
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
        self.email_confirmation_tokens = FakeEmailConfirmationTokenRepository()
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
def unconfirmed_user(uow):
    """Create an unconfirmed user with password."""
    user = User(
        email="test@example.com",
        global_role=GlobalRole.USER,
        password_hash="hashed_password",  # pragma: allowlist secret
        first_name="Test",
        last_name="User",
    )
    uow.users.add(user)
    return user


@pytest.fixture
def confirmed_user(uow):
    """Create a confirmed user."""
    user = User(
        email="confirmed@example.com",
        global_role=GlobalRole.USER,
        password_hash="hashed_password",  # pragma: allowlist secret
        first_name="Confirmed",
        last_name="User",
        email_confirmed_at=datetime.now(UTC),
    )
    uow.users.add(user)
    return user


@pytest.fixture
def oauth_user(uow):
    """Create an OAuth user (auto-confirmed)."""
    user = User(
        email="oauth@example.com",
        global_role=GlobalRole.USER,
        oauth_provider="google",
        oauth_id="12345",
        email_confirmed_at=datetime.now(UTC),
    )
    uow.users.add(user)
    return user


@pytest.fixture
def inactive_user(uow):
    """Create an inactive user."""
    user = User(
        email="inactive@example.com",
        global_role=GlobalRole.USER,
        password_hash="hashed_password",  # pragma: allowlist secret
        is_active=False,
    )
    uow.users.add(user)
    return user


class TestCreateConfirmationToken:
    """Tests for create_confirmation_token function."""

    def test_creates_token_for_user(self, uow, unconfirmed_user):
        """Should create token for user."""
        with uow:
            token = email_confirmation_service.create_confirmation_token(uow, unconfirmed_user.id)

        assert token is not None
        assert token.user_id == unconfirmed_user.id
        assert token.token is not None
        assert token.is_valid()

    def test_default_expiry_24_hours(self, uow, unconfirmed_user):
        """Should use default expiry of 24 hours."""
        with uow:
            token = email_confirmation_service.create_confirmation_token(uow, unconfirmed_user.id)

        expected_expiry = token.created_at + timedelta(hours=24)
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 1

    def test_custom_expiry(self, uow, unconfirmed_user):
        """Should use custom expiry hours."""
        with uow:
            token = email_confirmation_service.create_confirmation_token(uow, unconfirmed_user.id, expires_in_hours=48)

        expected_expiry = token.created_at + timedelta(hours=48)
        assert abs((token.expires_at - expected_expiry).total_seconds()) < 1

    def test_rate_limit_exceeded(self, uow, unconfirmed_user):
        """Should raise RateLimitExceeded if too many requests."""
        # Create 3 recent tokens (hitting the limit)
        for _ in range(3):
            token = EmailConfirmationToken(user_id=unconfirmed_user.id)
            uow.email_confirmation_tokens.add(token)

        with pytest.raises(RateLimitExceeded) as exc_info, uow:
            email_confirmation_service.create_confirmation_token(uow, unconfirmed_user.id)

        assert "rate limit" in str(exc_info.value).lower()


class TestCheckRateLimit:
    """Tests for check_rate_limit function."""

    def test_allows_first_request(self, uow, unconfirmed_user):
        """Should allow first request."""
        with uow:
            # Should not raise
            email_confirmation_service.check_rate_limit(uow, unconfirmed_user.id)

    def test_blocks_after_limit(self, uow, unconfirmed_user):
        """Should block after hitting rate limit."""
        # Create 3 tokens within the window
        for _ in range(3):
            token = EmailConfirmationToken(user_id=unconfirmed_user.id)
            uow.email_confirmation_tokens.add(token)

        with pytest.raises(RateLimitExceeded), uow:
            email_confirmation_service.check_rate_limit(uow, unconfirmed_user.id)

    def test_allows_old_tokens(self, uow, unconfirmed_user):
        """Should allow request if old tokens are outside window."""
        # Create 3 old tokens (outside 1 hour window)
        old_time = datetime.now(UTC) - timedelta(hours=2)
        for _ in range(3):
            token = EmailConfirmationToken(
                user_id=unconfirmed_user.id,
                created_at=old_time,
                expires_at=old_time + timedelta(hours=24),
            )
            uow.email_confirmation_tokens.add(token)

        with uow:
            # Should not raise
            email_confirmation_service.check_rate_limit(uow, unconfirmed_user.id)


class TestSendConfirmationEmail:
    """Tests for send_confirmation_email function."""

    def test_sends_email_successfully(self, unconfirmed_user):
        """Should send email successfully."""
        from tests.fakes import FakeTemplateRenderer, FakeURLGenerator

        email_adapter = MagicMock()
        email_adapter.send_email.return_value = True

        template_renderer = FakeTemplateRenderer()
        url_generator = FakeURLGenerator()

        result = email_confirmation_service.send_confirmation_email(
            email_adapter, template_renderer, url_generator, unconfirmed_user, "token123"
        )

        assert result is True
        email_adapter.send_email.assert_called_once()
        call_args = email_adapter.send_email.call_args[1]
        assert call_args["to"] == [unconfirmed_user.email]
        assert "Confirm" in call_args["subject"]

    def test_handles_email_failure(self, unconfirmed_user):
        """Should handle email sending failure."""
        from tests.fakes import FakeTemplateRenderer, FakeURLGenerator

        email_adapter = MagicMock()
        email_adapter.send_email.return_value = False

        template_renderer = FakeTemplateRenderer()
        url_generator = FakeURLGenerator()

        result = email_confirmation_service.send_confirmation_email(
            email_adapter, template_renderer, url_generator, unconfirmed_user, "token123"
        )

        assert result is False


class TestValidateConfirmationToken:
    """Tests for validate_confirmation_token function."""

    def test_validates_good_token(self, uow, unconfirmed_user):
        """Should validate a good token."""
        token = EmailConfirmationToken(user_id=unconfirmed_user.id, token="valid-token")
        uow.email_confirmation_tokens.add(token)

        result = email_confirmation_service.validate_confirmation_token(uow, "valid-token")

        assert result is not None
        assert result.token == "valid-token"

    def test_rejects_nonexistent_token(self, uow):
        """Should reject nonexistent token."""
        with pytest.raises(InvalidConfirmationToken, match="Token not found"):
            email_confirmation_service.validate_confirmation_token(uow, "nonexistent")

    def test_rejects_expired_token(self, uow, unconfirmed_user):
        """Should reject expired token."""
        past_time = datetime.now(UTC) - timedelta(hours=25)
        token = EmailConfirmationToken(
            user_id=unconfirmed_user.id,
            token="expired-token",
            created_at=past_time,
            expires_at=past_time + timedelta(hours=24),
        )
        uow.email_confirmation_tokens.add(token)

        with pytest.raises(InvalidConfirmationToken, match="expired"):
            email_confirmation_service.validate_confirmation_token(uow, "expired-token")

    def test_rejects_used_token(self, uow, unconfirmed_user):
        """Should reject used token."""
        token = EmailConfirmationToken(user_id=unconfirmed_user.id, token="used-token")
        token.use()
        uow.email_confirmation_tokens.add(token)

        with pytest.raises(InvalidConfirmationToken, match="already been used"):
            email_confirmation_service.validate_confirmation_token(uow, "used-token")

    def test_rejects_token_for_inactive_user(self, uow, inactive_user):
        """Should reject token if user is inactive."""
        token = EmailConfirmationToken(user_id=inactive_user.id, token="inactive-token")
        uow.email_confirmation_tokens.add(token)

        with pytest.raises(InvalidConfirmationToken, match="inactive"):
            email_confirmation_service.validate_confirmation_token(uow, "inactive-token")


class TestConfirmEmailWithToken:
    """Tests for confirm_email_with_token function."""

    def test_confirms_email_successfully(self, uow, unconfirmed_user):
        """Should confirm email successfully."""
        token = EmailConfirmationToken(user_id=unconfirmed_user.id, token="confirm-token")
        uow.email_confirmation_tokens.add(token)

        result = email_confirmation_service.confirm_email_with_token(uow, "confirm-token")

        assert result is not None
        assert result.email_confirmed_at is not None
        assert uow.committed is True

    def test_marks_token_as_used(self, uow, unconfirmed_user):
        """Should mark token as used after confirmation."""
        token = EmailConfirmationToken(user_id=unconfirmed_user.id, token="confirm-token")
        uow.email_confirmation_tokens.add(token)

        email_confirmation_service.confirm_email_with_token(uow, "confirm-token")

        # Check token is now used
        stored_token = uow.email_confirmation_tokens.get_by_token("confirm-token")
        assert stored_token.is_used()

    def test_invalidates_other_tokens(self, uow, unconfirmed_user):
        """Should invalidate other valid tokens for user."""
        # Create multiple tokens
        token1 = EmailConfirmationToken(user_id=unconfirmed_user.id, token="token1")
        token2 = EmailConfirmationToken(user_id=unconfirmed_user.id, token="token2")
        uow.email_confirmation_tokens.add(token1)
        uow.email_confirmation_tokens.add(token2)

        # Confirm with token1
        email_confirmation_service.confirm_email_with_token(uow, "token1")

        # Check token2 is also invalidated
        stored_token2 = uow.email_confirmation_tokens.get_by_token("token2")
        assert stored_token2.is_used()

    def test_rejects_invalid_token(self, uow):
        """Should reject invalid token."""
        with pytest.raises(InvalidConfirmationToken):
            email_confirmation_service.confirm_email_with_token(uow, "invalid")


class TestResendConfirmationEmail:
    """Tests for resend_confirmation_email function."""

    def test_creates_token_for_unconfirmed_user(self, uow, unconfirmed_user):
        """Should create token for unconfirmed user."""
        from tests.fakes import FakeTemplateRenderer, FakeURLGenerator

        email_adapter = MagicMock()
        email_adapter.send_email.return_value = True

        template_renderer = FakeTemplateRenderer()
        url_generator = FakeURLGenerator()

        # Mock send_confirmation_email to avoid email sending
        with patch("opendlp.service_layer.email_confirmation_service.send_confirmation_email") as mock_send:
            mock_send.return_value = True

            result = email_confirmation_service.resend_confirmation_email(
                uow, unconfirmed_user.email, email_adapter, template_renderer, url_generator
            )

            assert result is True
            assert uow.committed is True
            mock_send.assert_called_once()

        # Check token was created
        tokens = list(uow.email_confirmation_tokens._tokens.values())
        assert len(tokens) == 1
        assert tokens[0].user_id == unconfirmed_user.id

    def test_returns_true_for_nonexistent_email(self, uow):
        """Should return true but not create token for nonexistent email (anti-enumeration)."""
        from tests.fakes import FakeTemplateRenderer, FakeURLGenerator

        email_adapter = MagicMock()
        email_adapter.send_email.return_value = True

        template_renderer = FakeTemplateRenderer()
        url_generator = FakeURLGenerator()

        result = email_confirmation_service.resend_confirmation_email(
            uow, "nonexistent@example.com", email_adapter, template_renderer, url_generator
        )

        assert result is True
        email_adapter.send_email.assert_not_called()

        # Check no token was created
        tokens = list(uow.email_confirmation_tokens._tokens.values())
        assert len(tokens) == 0

    def test_returns_true_for_confirmed_user(self, uow, confirmed_user):
        """Should return true but not create token for already confirmed user."""
        from tests.fakes import FakeTemplateRenderer, FakeURLGenerator

        email_adapter = MagicMock()
        email_adapter.send_email.return_value = True

        template_renderer = FakeTemplateRenderer()
        url_generator = FakeURLGenerator()

        result = email_confirmation_service.resend_confirmation_email(
            uow, confirmed_user.email, email_adapter, template_renderer, url_generator
        )

        assert result is True
        email_adapter.send_email.assert_not_called()

        # Check no token was created
        tokens = list(uow.email_confirmation_tokens._tokens.values())
        assert len(tokens) == 0

    def test_returns_true_for_inactive_user(self, uow, inactive_user):
        """Should return true but not create token for inactive user."""
        from tests.fakes import FakeTemplateRenderer, FakeURLGenerator

        email_adapter = MagicMock()
        email_adapter.send_email.return_value = True

        template_renderer = FakeTemplateRenderer()
        url_generator = FakeURLGenerator()

        result = email_confirmation_service.resend_confirmation_email(
            uow, inactive_user.email, email_adapter, template_renderer, url_generator
        )

        assert result is True
        email_adapter.send_email.assert_not_called()

        # Check no token was created
        tokens = list(uow.email_confirmation_tokens._tokens.values())
        assert len(tokens) == 0

    def test_rate_limit_exceeded(self, uow, unconfirmed_user):
        """Should raise RateLimitExceeded if too many requests."""
        from tests.fakes import FakeTemplateRenderer, FakeURLGenerator

        email_adapter = MagicMock()
        email_adapter.send_email.return_value = True

        template_renderer = FakeTemplateRenderer()
        url_generator = FakeURLGenerator()

        # Create 3 recent tokens (hitting the limit)
        for _ in range(3):
            token = EmailConfirmationToken(user_id=unconfirmed_user.id)
            uow.email_confirmation_tokens.add(token)

        with pytest.raises(RateLimitExceeded):
            email_confirmation_service.resend_confirmation_email(
                uow, unconfirmed_user.email, email_adapter, template_renderer, url_generator
            )


class TestInvalidateUserTokens:
    """Tests for invalidate_user_tokens function."""

    def test_invalidates_all_valid_tokens(self, uow, unconfirmed_user):
        """Should invalidate all valid tokens for user."""
        # Create multiple valid tokens
        for i in range(3):
            token = EmailConfirmationToken(user_id=unconfirmed_user.id, token=f"token{i}")
            uow.email_confirmation_tokens.add(token)

        with uow:
            count = email_confirmation_service.invalidate_user_tokens(uow, unconfirmed_user.id)

        assert count == 3

        # All tokens should be used
        for i in range(3):
            token = uow.email_confirmation_tokens.get_by_token(f"token{i}")
            assert token.is_used()

    def test_does_not_invalidate_expired_tokens(self, uow, unconfirmed_user):
        """Should not invalidate already expired tokens."""
        # Create one valid and one expired token
        valid_token = EmailConfirmationToken(user_id=unconfirmed_user.id, token="valid")
        uow.email_confirmation_tokens.add(valid_token)

        past_time = datetime.now(UTC) - timedelta(hours=25)
        expired_token = EmailConfirmationToken(
            user_id=unconfirmed_user.id,
            token="expired",
            created_at=past_time,
            expires_at=past_time + timedelta(hours=24),
        )
        uow.email_confirmation_tokens.add(expired_token)

        with uow:
            count = email_confirmation_service.invalidate_user_tokens(uow, unconfirmed_user.id)

        # Only the valid token should be invalidated
        assert count == 1


class TestCleanupExpiredTokens:
    """Tests for cleanup_expired_tokens function."""

    def test_deletes_old_tokens(self, uow, unconfirmed_user):
        """Should delete old tokens."""
        # Create old tokens
        old_time = datetime.now(UTC) - timedelta(days=31)
        for i in range(3):
            token = EmailConfirmationToken(
                user_id=unconfirmed_user.id,
                token=f"old{i}",
                created_at=old_time,
                expires_at=old_time + timedelta(hours=24),
            )
            uow.email_confirmation_tokens.add(token)

        count = email_confirmation_service.cleanup_expired_tokens(uow, days_old=30)

        assert count == 3
        assert len(uow.email_confirmation_tokens._tokens) == 0

    def test_keeps_recent_tokens(self, uow, unconfirmed_user):
        """Should keep recent tokens."""
        # Create recent tokens
        recent_time = datetime.now(UTC) - timedelta(days=1)
        for i in range(3):
            token = EmailConfirmationToken(
                user_id=unconfirmed_user.id,
                token=f"recent{i}",
                created_at=recent_time,
                expires_at=recent_time + timedelta(hours=24),
            )
            uow.email_confirmation_tokens.add(token)

        count = email_confirmation_service.cleanup_expired_tokens(uow, days_old=30)

        assert count == 0
        assert len(uow.email_confirmation_tokens._tokens) == 3
