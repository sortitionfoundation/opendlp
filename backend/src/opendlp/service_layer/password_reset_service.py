"""ABOUTME: Password reset service layer for managing password recovery
ABOUTME: Handles reset token creation, validation, rate limiting, and password updates"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from flask import render_template, url_for

from opendlp.adapters.email import EmailAdapter
from opendlp.domain.password_reset import PasswordResetToken
from opendlp.domain.users import User

from .exceptions import InvalidResetToken, PasswordTooWeak, RateLimitExceeded
from .security import TempUser, hash_password, validate_password_strength
from .unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_TOKEN_EXPIRY_HOURS = 1
RATE_LIMIT_COUNT = 3
RATE_LIMIT_WINDOW_HOURS = 1
COOLDOWN_MINUTES = 5


def request_password_reset(
    uow: AbstractUnitOfWork,
    email: str,
    expires_in_hours: int = DEFAULT_TOKEN_EXPIRY_HOURS,
) -> bool:
    """
    Create a password reset token and prepare for email sending.

    This function ALWAYS returns True to prevent email enumeration attacks.
    If the email doesn't exist or is an OAuth user, no token is created,
    but the function still returns True.

    Args:
        uow: Unit of Work for database operations
        email: Email address requesting password reset
        expires_in_hours: Hours until token expires (default 1 hour)

    Returns:
        Always returns True (anti-enumeration)

    Raises:
        RateLimitExceeded: If user has exceeded rate limits
    """
    with uow:
        # Look up user by email
        user = uow.users.get_by_email(email)

        # If user doesn't exist, return success (anti-enumeration)
        if not user:
            return True

        # If user is OAuth-based, return success without creating token
        if user.oauth_provider:
            return True

        # If user is inactive, return success without creating token
        if not user.is_active:
            return True

        # Check rate limiting
        check_rate_limit(uow, user.id)

        # Create reset token
        token = PasswordResetToken(
            user_id=user.id,
            expires_in_hours=expires_in_hours,
        )

        uow.password_reset_tokens.add(token)
        uow.commit()

        # Return True - email sending happens in the caller
        return True


def check_rate_limit(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> None:
    """
    Check if user has exceeded rate limits for password reset requests.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of the user requesting reset

    Raises:
        RateLimitExceeded: If user has exceeded rate limits
    """
    # Note: This function is called from within a UnitOfWork context,
    # so we don't need another `with uow:` block

    # Check requests in the rate limit window
    since = datetime.now(UTC) - timedelta(hours=RATE_LIMIT_WINDOW_HOURS)
    recent_count = uow.password_reset_tokens.count_recent_requests(user_id, since)

    if recent_count >= RATE_LIMIT_COUNT:
        # Calculate retry after time
        retry_after_seconds = int(RATE_LIMIT_WINDOW_HOURS * 3600)
        raise RateLimitExceeded(
            operation="password reset",
            retry_after_seconds=retry_after_seconds,
        )


def validate_reset_token(uow: AbstractUnitOfWork, token_string: str) -> PasswordResetToken:
    """
    Validate a password reset token.

    Args:
        uow: Unit of Work for database operations
        token_string: The token string to validate

    Returns:
        Valid PasswordResetToken instance

    Raises:
        InvalidResetToken: If token is invalid, expired, or used
    """
    with uow:
        token = uow.password_reset_tokens.get_by_token(token_string)

        if not token:
            raise InvalidResetToken("Token not found")

        if token.is_expired():
            raise InvalidResetToken("Token has expired")

        if token.is_used():
            raise InvalidResetToken("Token has already been used")

        # Verify associated user still exists and is active
        user = uow.users.get(token.user_id)
        if not user or not user.is_active:
            raise InvalidResetToken("Associated user not found or inactive")

        return token.create_detached_copy()


def reset_password_with_token(
    uow: AbstractUnitOfWork,
    token_string: str,
    new_password: str,
) -> User:
    """
    Reset user password using a valid token.

    Args:
        uow: Unit of Work for database operations
        token_string: The reset token string
        new_password: New password to set

    Returns:
        Updated User instance

    Raises:
        InvalidResetToken: If token is invalid
        PasswordTooWeak: If password doesn't meet requirements
    """
    with uow:
        # Validate token
        token = uow.password_reset_tokens.get_by_token(token_string)

        if not token:
            raise InvalidResetToken("Token not found")

        if not token.is_valid():
            if token.is_expired():
                raise InvalidResetToken("Token has expired")
            elif token.is_used():
                raise InvalidResetToken("Token has already been used")
            else:
                raise InvalidResetToken("Token is invalid")

        # Get user
        user = uow.users.get(token.user_id)
        if not user:
            raise InvalidResetToken("Associated user not found")

        if not user.is_active:
            raise InvalidResetToken("User account is inactive")

        # Validate new password strength
        temp_user = TempUser(
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
        )
        is_valid, error_msg = validate_password_strength(new_password, temp_user)
        if not is_valid:
            raise PasswordTooWeak(error_msg)

        # Update password
        user.password_hash = hash_password(new_password)

        # Mark token as used
        token.use()

        # Invalidate all other tokens for this user
        invalidate_user_tokens(uow, user.id)

        detached_user = user.create_detached_copy()
        uow.commit()
        assert isinstance(detached_user, User)

        return detached_user


def invalidate_user_tokens(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> int:
    """
    Mark all active tokens for a user as used.

    This is called when a password is successfully reset to prevent
    other outstanding tokens from being used.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of the user whose tokens should be invalidated

    Returns:
        Number of tokens invalidated
    """
    # Note: This function is called from within a UnitOfWork context,
    # so we don't need another `with uow:` block
    return uow.password_reset_tokens.invalidate_user_tokens(user_id)


def get_token_by_string(uow: AbstractUnitOfWork, token_string: str) -> PasswordResetToken | None:
    """
    Get a password reset token by its string value.

    Args:
        uow: Unit of Work for database operations
        token_string: The token string

    Returns:
        PasswordResetToken if found, None otherwise
    """
    with uow:
        token = uow.password_reset_tokens.get_by_token(token_string)
        return token.create_detached_copy() if token else None


def cleanup_expired_tokens(uow: AbstractUnitOfWork, days_old: int = 30) -> int:
    """
    Delete old expired and used tokens from the database.

    Tokens are kept for audit purposes for a configurable period,
    then cleaned up to avoid database bloat.

    Args:
        uow: Unit of Work for database operations
        days_old: Delete tokens older than this many days (default 30)

    Returns:
        Number of tokens deleted
    """
    with uow:
        before = datetime.now(UTC) - timedelta(days=days_old)
        count = uow.password_reset_tokens.delete_old_tokens(before)
        uow.commit()
        return count


def send_password_reset_email(
    email_adapter: EmailAdapter,
    user: User,
    reset_token: str,
    expires_in_hours: int = DEFAULT_TOKEN_EXPIRY_HOURS,
) -> bool:
    """
    Send password reset email to user.

    Args:
        email_adapter: Email adapter for sending emails
        user: User to send email to
        reset_token: Password reset token string
        expires_in_hours: Hours until token expires (for email message)

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Generate reset URL
        # Using _external=True to get full URL with domain
        reset_url = url_for(
            "auth.reset_password",
            token=reset_token,
            _external=True,
        )

        # Prepare template context
        context = {
            "user_name": user.display_name if user.first_name or user.last_name else None,
            "email_address": user.email,
            "reset_url": reset_url,
            "expiry_hours": expires_in_hours,
        }

        # Render email templates
        text_body = render_template("emails/password_reset.txt", **context)
        html_body = render_template("emails/password_reset.html", **context)

        # Send email
        success = email_adapter.send_email(
            to=[user.email],
            subject="Reset Your OpenDLP Password",
            text_body=text_body,
            html_body=html_body,
        )

        if success:
            logger.info(f"Password reset email sent to {user.email}")
        else:
            logger.error(f"Failed to send password reset email to {user.email}")

        return success

    except Exception as e:
        logger.error(f"Error sending password reset email to {user.email}: {e}")
        return False
