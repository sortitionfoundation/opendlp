"""ABOUTME: Email confirmation service layer for managing email verification
ABOUTME: Handles confirmation token creation, validation, rate limiting, and email sending"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from flask import render_template, url_for

from opendlp.adapters.email import EmailAdapter
from opendlp.domain.email_confirmation import EmailConfirmationToken
from opendlp.domain.users import User

from .exceptions import InvalidConfirmationToken, RateLimitExceeded
from .unit_of_work import AbstractUnitOfWork

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_TOKEN_EXPIRY_HOURS = 24
RATE_LIMIT_COUNT = 3
RATE_LIMIT_WINDOW_HOURS = 1


def create_confirmation_token(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    expires_in_hours: int = DEFAULT_TOKEN_EXPIRY_HOURS,
) -> EmailConfirmationToken:
    """
    Create an email confirmation token for a user.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of the user requesting confirmation
        expires_in_hours: Hours until token expires (default 24 hours)

    Returns:
        Created EmailConfirmationToken instance

    Raises:
        RateLimitExceeded: If user has exceeded rate limits
    """
    # Note: This function is called from within a UnitOfWork context,
    # so we don't need another `with uow:` block

    # Check rate limiting
    check_rate_limit(uow, user_id)

    # Create confirmation token
    token = EmailConfirmationToken(
        user_id=user_id,
        expires_in_hours=expires_in_hours,
    )

    uow.email_confirmation_tokens.add(token)
    return token


def check_rate_limit(uow: AbstractUnitOfWork, user_id: uuid.UUID) -> None:
    """
    Check if user has exceeded rate limits for email confirmation requests.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of the user requesting confirmation

    Raises:
        RateLimitExceeded: If user has exceeded rate limits
    """
    # Note: This function is called from within a UnitOfWork context,
    # so we don't need another `with uow:` block

    # Check requests in the rate limit window
    since = datetime.now(UTC) - timedelta(hours=RATE_LIMIT_WINDOW_HOURS)
    recent_count = uow.email_confirmation_tokens.count_recent_requests(user_id, since)

    if recent_count >= RATE_LIMIT_COUNT:
        # Calculate retry after time
        retry_after_seconds = int(RATE_LIMIT_WINDOW_HOURS * 3600)
        raise RateLimitExceeded(
            operation="email confirmation",
            retry_after_seconds=retry_after_seconds,
        )


def send_confirmation_email(
    email_adapter: EmailAdapter,
    user: User,
    confirmation_token: str,
    expires_in_hours: int = DEFAULT_TOKEN_EXPIRY_HOURS,
) -> bool:
    """
    Send email confirmation email to user.

    Args:
        email_adapter: Email adapter for sending emails
        user: User to send email to
        confirmation_token: Email confirmation token string
        expires_in_hours: Hours until token expires (for email message)

    Returns:
        True if email sent successfully, False otherwise
    """
    try:
        # Generate confirmation URL
        # Using _external=True to get full URL with domain
        confirmation_url = url_for(
            "auth.confirm_email",
            token=confirmation_token,
            _external=True,
        )

        # Prepare template context
        context = {
            "user_name": user.display_name,
            "email_address": user.email,
            "confirmation_url": confirmation_url,
            "expiry_hours": expires_in_hours,
        }

        # Render email templates
        text_body = render_template("emails/email_confirmation.txt", **context)
        html_body = render_template("emails/email_confirmation.html", **context)

        # Send email
        success = email_adapter.send_email(
            to=[user.email],
            subject="Confirm Your OpenDLP Email Address",
            text_body=text_body,
            html_body=html_body,
        )

        if success:
            logger.info(f"Email confirmation sent to {user.email}")
        else:
            logger.error(f"Failed to send email confirmation to {user.email}")

        return success

    except Exception as e:
        logger.error(f"Error sending email confirmation to {user.email}: {e}")
        return False


def validate_confirmation_token(uow: AbstractUnitOfWork, token_string: str) -> EmailConfirmationToken:
    """
    Validate an email confirmation token.

    Args:
        uow: Unit of Work for database operations
        token_string: The token string to validate

    Returns:
        Valid EmailConfirmationToken instance

    Raises:
        InvalidConfirmationToken: If token is invalid, expired, or used
    """
    with uow:
        token = uow.email_confirmation_tokens.get_by_token(token_string)

        if not token:
            raise InvalidConfirmationToken("Token not found")

        # Help mypy understand the type
        assert isinstance(token, EmailConfirmationToken)

        if token.is_expired():
            raise InvalidConfirmationToken("Token has expired")

        if token.is_used():
            raise InvalidConfirmationToken("Token has already been used")

        # Verify associated user still exists and is active
        user = uow.users.get(token.user_id)
        if not user or not user.is_active:
            raise InvalidConfirmationToken("Associated user not found or inactive")

        return token.create_detached_copy()


def confirm_email_with_token(
    uow: AbstractUnitOfWork,
    token_string: str,
) -> User:
    """
    Confirm user email using a valid token.

    Args:
        uow: Unit of Work for database operations
        token_string: The confirmation token string

    Returns:
        Updated User instance

    Raises:
        InvalidConfirmationToken: If token is invalid
    """
    with uow:
        # Validate token
        token = uow.email_confirmation_tokens.get_by_token(token_string)

        if not token:
            raise InvalidConfirmationToken("Token not found")

        if not token.is_valid():
            if token.is_expired():
                raise InvalidConfirmationToken("Token has expired")
            elif token.is_used():
                raise InvalidConfirmationToken("Token has already been used")
            else:
                raise InvalidConfirmationToken("Token is invalid")

        # Get user
        user = uow.users.get(token.user_id)
        if not user:
            raise InvalidConfirmationToken("Associated user not found")

        if not user.is_active:
            raise InvalidConfirmationToken("User account is inactive")

        # Confirm email
        user.confirm_email()

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

    This is called when an email is successfully confirmed to prevent
    other outstanding tokens from being used.

    Args:
        uow: Unit of Work for database operations
        user_id: ID of the user whose tokens should be invalidated

    Returns:
        Number of tokens invalidated
    """
    # Note: This function is called from within a UnitOfWork context,
    # so we don't need another `with uow:` block
    return uow.email_confirmation_tokens.invalidate_user_tokens(user_id)


def resend_confirmation_email(
    uow: AbstractUnitOfWork,
    email: str,
    email_adapter: EmailAdapter,
) -> bool:
    """
    Request resend of confirmation email.

    This function ALWAYS returns True to prevent email enumeration attacks.
    If the email doesn't exist or is already confirmed, no token is created
    and no email is sent, but the function still returns True.

    Args:
        uow: Unit of Work for database operations
        email: Email address requesting confirmation resend
        email_adapter: Email adapter for sending emails

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

        # If user is already confirmed, return success (anti-enumeration)
        if user.email_confirmed_at:
            return True

        # If user is inactive, return success without creating token
        if not user.is_active:
            return True

        # Check rate limiting
        check_rate_limit(uow, user.id)

        # Create confirmation token
        token = create_confirmation_token(uow, user.id)

        uow.commit()

        # Send confirmation email
        send_confirmation_email(email_adapter, user, token.token)

        return True


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
        count = uow.email_confirmation_tokens.delete_old_tokens(before)
        uow.commit()
        return count
