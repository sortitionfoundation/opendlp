"""Integration tests for password reset flow."""

import secrets
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer import password_reset_service
from opendlp.service_layer.exceptions import InvalidResetToken, RateLimitExceeded
from opendlp.service_layer.security import hash_password
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork


@pytest.fixture
def test_user_email(sqlite_session_factory):
    """Create a test user with password authentication."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    email_suffix = secrets.token_urlsafe(3)
    email = f"testuser{email_suffix}@example.com"
    with uow:
        user = User(
            email=email,
            global_role=GlobalRole.USER,
            password_hash="old_password_hash",  # pragma: allowlist secret
            first_name="Test",
            last_name="User",
        )
        uow.users.add(user)
        uow.commit()
        return user.id, email


@pytest.fixture
def test_user(test_user_email):
    test_user_id, _ = test_user_email
    return test_user_id


def test_full_password_reset_flow(sqlite_session_factory, test_user_email):
    """Test complete password reset flow from request to completion."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    test_user_id, test_email = test_user_email

    # Step 1: Request password reset
    success = password_reset_service.request_password_reset(uow, test_email)
    assert success is True

    # Step 2: Verify token was created
    with uow:
        tokens = list(uow.password_reset_tokens.get_active_tokens_for_user(test_user_id))
        assert len(tokens) == 1
        token = tokens[0].create_detached_copy()
        assert token.user_id == test_user_id
        assert token.is_valid()

    # Step 3: Validate the token
    validated_token = password_reset_service.validate_reset_token(uow, token.token)
    assert validated_token.token == token.token

    # Step 4: Reset password with token
    new_password_hash = hash_password("NewSecurePassword123!")

    with (
        patch("opendlp.service_layer.password_reset_service.hash_password") as mock_hash,
        patch("opendlp.service_layer.password_reset_service.validate_password_strength") as mock_validate,
    ):
        mock_hash.return_value = new_password_hash
        mock_validate.return_value = (True, "")

        user = password_reset_service.reset_password_with_token(uow, token.token, "NewSecurePassword123!")

        assert user.id == test_user_id

    # Step 5: Verify password was changed
    with uow:
        updated_user = uow.users.get(test_user_id)
        assert updated_user.password_hash == new_password_hash

    # Step 6: Verify token was marked as used
    with uow:
        used_token = uow.password_reset_tokens.get_by_token(token.token)
        assert used_token.is_used()


def test_rate_limiting(sqlite_session_factory, test_user_email):
    """Test that rate limiting prevents excessive requests."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)
    _, email = test_user_email

    # Make 3 requests (hitting the limit)
    for _i in range(3):
        password_reset_service.request_password_reset(uow, email)

    # 4th request should fail
    with pytest.raises(RateLimitExceeded):
        password_reset_service.request_password_reset(uow, email)


def test_expired_token_cannot_be_used(sqlite_session_factory, test_user):
    """Test that expired tokens cannot be used."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Create an expired token
    with uow:
        past_time = datetime.now(UTC) - timedelta(hours=2)
        token = PasswordResetToken(
            user_id=test_user,
            created_at=past_time,
            expires_at=past_time + timedelta(hours=1),
            token="expired-token-123",
        )
        uow.password_reset_tokens.add(token)
        uow.commit()

    # Try to validate expired token
    with pytest.raises(InvalidResetToken, match="expired"):
        password_reset_service.validate_reset_token(uow, "expired-token-123")


def test_used_token_cannot_be_reused(sqlite_session_factory, test_user):
    """Test that used tokens cannot be reused."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Create and use a token
    with uow:
        token = PasswordResetToken(user_id=test_user, token="used-token-456")
        token.use()
        uow.password_reset_tokens.add(token)
        uow.commit()

    # Try to validate used token
    with pytest.raises(InvalidResetToken, match="already been used"):
        password_reset_service.validate_reset_token(uow, "used-token-456")


def test_nonexistent_email_returns_success_but_no_token(sqlite_session_factory):
    """Test that nonexistent emails return success (anti-enumeration)."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Request reset for nonexistent email
    success = password_reset_service.request_password_reset(uow, "nonexistent@example.com")
    assert success is True

    # Verify no tokens were created
    with uow:
        all_tokens = list(uow.password_reset_tokens.all())
        # Filter for tokens that might be for this email (there won't be any)
        assert len([t for t in all_tokens if t.token == "nonexistent"]) == 0


def test_oauth_user_cannot_reset_password(sqlite_session_factory):
    """Test that OAuth users cannot request password reset."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Create OAuth user
    with uow:
        oauth_user = User(
            email="oauth@example.com",
            global_role=GlobalRole.USER,
            oauth_provider="google",
            oauth_id="google123",
        )
        uow.users.add(oauth_user)
        uow.commit()
        oauth_user_id = oauth_user.id

    # Request reset for OAuth user
    success = password_reset_service.request_password_reset(uow, "oauth@example.com")
    assert success is True  # Returns success (anti-enumeration)

    # Verify no token was created
    with uow:
        tokens = list(uow.password_reset_tokens.get_active_tokens_for_user(oauth_user_id))
        assert len(tokens) == 0


def test_inactive_user_cannot_reset_password(sqlite_session_factory):
    """Test that inactive users cannot request password reset."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Create inactive user
    with uow:
        inactive_user = User(
            email="inactive@example.com",
            global_role=GlobalRole.USER,
            password_hash="password_hash",  # pragma: allowlist secret
            is_active=False,
        )
        uow.users.add(inactive_user)
        uow.commit()
        inactive_user_id = inactive_user.id

    # Request reset for inactive user
    success = password_reset_service.request_password_reset(uow, "inactive@example.com")
    assert success is True  # Returns success (anti-enumeration)

    # Verify no token was created
    with uow:
        tokens = list(uow.password_reset_tokens.get_active_tokens_for_user(inactive_user_id))
        assert len(tokens) == 0


def test_token_cleanup(sqlite_session_factory, test_user):
    """Test that old tokens can be cleaned up."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Create old tokens
    with uow:
        old_time = datetime.now(UTC) - timedelta(days=35)
        old_token = PasswordResetToken(
            user_id=test_user,
            created_at=old_time,
            expires_at=old_time + timedelta(hours=1),
            token="old-token-789",
        )
        uow.password_reset_tokens.add(old_token)

        # Create recent token
        recent_token = PasswordResetToken(user_id=test_user, token="recent-token-101")
        uow.password_reset_tokens.add(recent_token)
        uow.commit()

    # Clean up tokens older than 30 days
    count = password_reset_service.cleanup_expired_tokens(uow, days_old=30)
    assert count == 1

    # Verify old token was deleted, recent one remains
    with uow:
        assert uow.password_reset_tokens.get_by_token("old-token-789") is None
        assert uow.password_reset_tokens.get_by_token("recent-token-101") is not None


def test_invalidate_other_tokens_on_reset(sqlite_session_factory, test_user):
    """Test that all other tokens are invalidated when password is reset."""
    uow = SqlAlchemyUnitOfWork(sqlite_session_factory)

    # Create multiple tokens
    with uow:
        token1 = PasswordResetToken(user_id=test_user, token="token1")
        token2 = PasswordResetToken(user_id=test_user, token="token2")
        token3 = PasswordResetToken(user_id=test_user, token="token3")
        uow.password_reset_tokens.add(token1)
        uow.password_reset_tokens.add(token2)
        uow.password_reset_tokens.add(token3)
        uow.commit()

    # Reset password with token1
    with (
        patch("opendlp.service_layer.password_reset_service.hash_password") as mock_hash,
        patch("opendlp.service_layer.password_reset_service.validate_password_strength") as mock_validate,
    ):
        mock_hash.return_value = "new_hash"
        mock_validate.return_value = (True, "")

        password_reset_service.reset_password_with_token(uow, "token1", "NewPassword123!")

    # Verify all tokens are now used
    with uow:
        assert uow.password_reset_tokens.get_by_token("token1").is_used()
        assert uow.password_reset_tokens.get_by_token("token2").is_used()
        assert uow.password_reset_tokens.get_by_token("token3").is_used()
