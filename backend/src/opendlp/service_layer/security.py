"""ABOUTME: Security utilities for password hashing and invite code generation
ABOUTME: Provides functions for secure password handling and unique invite code creation"""

from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password: str) -> str:
    """Hash a password using werkzeug's secure method."""
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return check_password_hash(password_hash, password)


# If you want to generate an invite code, use opendlp.domain.user_invites.generate_invite_code()


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password strength requirements.

    Returns tuple of (is_valid, error_message)
    """
    # TODO: consider using Django password strength validation
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"

    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"

    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"

    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"

    return True, ""
