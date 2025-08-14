"""ABOUTME: Security utilities for password hashing and invite code generation
ABOUTME: Provides functions for secure password handling and unique invite code creation"""

from dataclasses import dataclass, fields

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from werkzeug.security import check_password_hash, generate_password_hash

from opendlp.vendor import password_validation as pv


def hash_password(password: str) -> str:
    """Hash a password using werkzeug's secure method."""
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash."""
    return check_password_hash(password_hash, password)


# If you want to generate an invite code, use opendlp.domain.user_invites.generate_invite_code()


@dataclass
class TempUser:
    """
    Temporary user to pass to password validation, so we can check the password
    for similarity to user attributes like email, first_name, last_name etc.

    Try to keep this up to date with domain.users.User
    """

    email: str
    first_name: str = ""
    last_name: str = ""


def validate_password_strength(password: str, user: object) -> tuple[bool, str]:
    """
    Validate password strength requirements.

    Returns tuple of (is_valid, error_message)
    """
    # We use the well maintained Django password validation
    validators = (
        pv.SafeCommonPasswordValidator(),
        pv.MinimumLengthValidator(min_length=9),
        pv.NumericPasswordValidator(),
        # this means we check every attribute of TempUser
        pv.UserAttributeSimilarityValidator(user_attributes=(f.name for f in fields(TempUser))),
    )
    try:
        validate_password(password, user=user, password_validators=validators)
    except ValidationError as error:
        return False, str(error)

    return True, ""
