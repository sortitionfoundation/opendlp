"""Integration tests for email confirmation flows."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from opendlp import bootstrap
from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.user_invites import UserInvite
from opendlp.domain.users import User
from opendlp.domain.value_objects import GlobalRole
from opendlp.service_layer.email_confirmation_service import (
    cleanup_expired_tokens,
    confirm_email_with_token,
    create_confirmation_token,
    resend_confirmation_email,
)
from opendlp.service_layer.exceptions import EmailNotConfirmed, InvalidConfirmationToken, RateLimitExceeded
from opendlp.service_layer.user_service import authenticate_user, create_user, find_or_create_oauth_user


class TestEmailConfirmationIntegration:
    """Integration tests for email confirmation with real database."""

    def test_password_user_registration_creates_unconfirmed_user(self, sqlite_session_factory):
        """Password registration should create unconfirmed user with token."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)
            uow.commit()

        # Register user
        with uow:
            user, token = create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPassword123",  # pragma: allowlist secret
                invite_code="TESTINVITE",
            )

        assert user.email_confirmed_at is None  # Not confirmed yet
        assert token is not None  # Token was created
        assert token.user_id == user.id

        # Verify token is in database
        with uow:
            stored_token = uow.email_confirmation_tokens.get_by_token(token.token)
            assert stored_token is not None
            assert stored_token.is_valid()

    def test_user_cannot_login_before_confirmation(self, sqlite_session_factory):
        """User cannot login before confirming email."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite and user
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)
            uow.commit()

        with uow:
            user, _token = create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPassword123",  # pragma: allowlist secret
                invite_code="TESTINVITE",
            )

        # Try to login
        with pytest.raises(EmailNotConfirmed):
            authenticate_user(uow, "test@example.com", "StrongPassword123")

    def test_user_can_confirm_email_with_token(self, sqlite_session_factory):
        """User can confirm email with valid token."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite and user
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)
            uow.commit()

        with uow:
            user, token = create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPassword123",  # pragma: allowlist secret
                invite_code="TESTINVITE",
            )

        # Confirm email
        confirmed_user = confirm_email_with_token(uow, token.token)

        assert confirmed_user.email_confirmed_at is not None
        assert confirmed_user.is_email_confirmed()

    def test_user_can_login_after_confirmation(self, sqlite_session_factory):
        """User can login after confirming email."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite and user
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)
            uow.commit()

        with uow:
            user, token = create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPassword123",  # pragma: allowlist secret
                invite_code="TESTINVITE",
            )

        # Confirm email
        confirm_email_with_token(uow, token.token)

        # Now login should work
        authenticated_user = authenticate_user(uow, "test@example.com", "StrongPassword123")
        assert authenticated_user is not None
        assert authenticated_user.is_email_confirmed()

    def test_oauth_user_auto_confirmed(self, sqlite_session_factory):
        """OAuth users are automatically confirmed."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)
            uow.commit()

        # Register OAuth user
        user, created = find_or_create_oauth_user(
            uow=uow,
            provider="google",
            oauth_id="google123",
            email="oauth@example.com",
            invite_code="TESTINVITE",
        )

        assert created is True
        assert user.email_confirmed_at is not None  # Auto-confirmed
        assert user.is_email_confirmed()

    def test_resend_confirmation_creates_new_token(self, sqlite_session_factory):
        """Resend confirmation creates a new token."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite and user
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)
            uow.commit()

        with uow:
            user, original_token = create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPassword123",  # pragma: allowlist secret
                invite_code="TESTINVITE",
            )

        # Resend confirmation
        email_adapter = MagicMock()
        email_adapter.send_email.return_value = True
        resend_confirmation_email(uow, "test@example.com", email_adapter)

        # Check that a new token was created
        with uow:
            tokens = list(uow.email_confirmation_tokens.all())
            assert len(tokens) == 2  # Original + new token

    def test_expired_token_rejected(self, sqlite_session_factory):
        """Expired tokens are rejected."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite and user
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)

            # Create user directly with unconfirmed email
            user = User(
                email="test@example.com",
                global_role=GlobalRole.USER,
                password_hash="hashed",  # pragma: allowlist secret
            )
            uow.users.add(user)
            uow.commit()
            user_id = user.id  # Save ID before session closes

        # Create expired token
        with uow:
            past_time = datetime.now(UTC) - timedelta(hours=25)
            expired_token = EmailConfirmationToken(
                user_id=user_id,
                token="expired-token",
                created_at=past_time,
                expires_at=past_time + timedelta(hours=24),
            )
            uow.email_confirmation_tokens.add(expired_token)
            uow.commit()

        # Try to confirm with expired token
        with pytest.raises(InvalidConfirmationToken, match="expired"):
            confirm_email_with_token(uow, "expired-token")

    def test_rate_limiting_works(self, sqlite_session_factory):
        """Rate limiting prevents spam."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite and user
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)
            uow.commit()

        with uow:
            user, _token = create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPassword123",  # pragma: allowlist secret
                invite_code="TESTINVITE",
            )

        # Request 2 more times (total 3)
        email_adapter = MagicMock()
        email_adapter.send_email.return_value = True
        resend_confirmation_email(uow, "test@example.com", email_adapter)
        resend_confirmation_email(uow, "test@example.com", email_adapter)

        # 4th request should be rate limited
        with pytest.raises(RateLimitExceeded):
            resend_confirmation_email(uow, "test@example.com", email_adapter)

    def test_used_token_rejected(self, sqlite_session_factory):
        """Used tokens cannot be reused."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create invite and user
        with uow:
            invite = UserInvite(
                code="TESTINVITE",
                global_role=GlobalRole.USER,
                created_by=uuid.uuid4(),
                expires_at=datetime.now(UTC) + timedelta(hours=24),
            )
            uow.user_invites.add(invite)
            uow.commit()

        with uow:
            user, token = create_user(
                uow=uow,
                email="test@example.com",
                password="StrongPassword123",  # pragma: allowlist secret
                invite_code="TESTINVITE",
            )

        # Confirm email once
        confirm_email_with_token(uow, token.token)

        # Try to use same token again
        with pytest.raises(InvalidConfirmationToken, match="already been used"):
            confirm_email_with_token(uow, token.token)

    def test_cleanup_removes_old_tokens(self, sqlite_session_factory):
        """Cleanup removes old tokens."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create user
        with uow:
            user = User(
                email="test@example.com",
                global_role=GlobalRole.USER,
                password_hash="hashed",  # pragma: allowlist secret
            )
            uow.users.add(user)
            uow.commit()
            user_id = user.id  # Save ID before session closes

        # Create old token
        with uow:
            old_time = datetime.now(UTC) - timedelta(days=31)
            old_token = EmailConfirmationToken(
                user_id=user_id,
                created_at=old_time,
                expires_at=old_time + timedelta(hours=24),
            )
            uow.email_confirmation_tokens.add(old_token)
            uow.commit()

        # Create recent token
        with uow:
            recent_token = create_confirmation_token(uow, user_id)
            uow.commit()
            recent_token_string = recent_token.token  # Save token string before session closes

        # Cleanup
        count = cleanup_expired_tokens(uow, days_old=30)

        assert count == 1  # Only old token removed

        # Verify recent token still exists
        with uow:
            stored_token = uow.email_confirmation_tokens.get_by_token(recent_token_string)
            assert stored_token is not None

    def test_grandfathered_user_can_login(self, sqlite_session_factory):
        """Existing users with email_confirmed_at set can login."""
        uow = bootstrap.bootstrap(session_factory=sqlite_session_factory)

        # Create a "grandfathered" user (simulating migration)
        with uow:
            user = User(
                email="existing@example.com",
                global_role=GlobalRole.USER,
                password_hash="$2b$12$KIXm3zXvqXvX1XvX1XvX1Oe5KQvX1XvX1XvX1XvX1XvX1XvX1XvX1X",  # pragma: allowlist secret
                email_confirmed_at=datetime.now(UTC) - timedelta(days=30),  # Set by migration
            )
            uow.users.add(user)
            uow.commit()

        # Should be able to check authentication (password won't match but email confirmation check will pass)
        with uow:
            fetched_user = uow.users.get_by_email("existing@example.com")
            assert fetched_user is not None
            assert fetched_user.is_email_confirmed()
