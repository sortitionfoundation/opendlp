"""ABOUTME: Security utilities for password hashing and invite code generation
ABOUTME: Provides functions for secure password handling and unique invite code creation"""

from collections.abc import Iterable
from dataclasses import dataclass, fields
from functools import cache

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

from opendlp.domain.users import UNUSABLE_PASSWORD_PREFIX
from opendlp.vendor import password_validation as pv


def hash_password(password: str) -> str:
    """Hash a password using werkzeug's secure method."""
    return generate_password_hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against its hash.

    An unusable password hash never matches - we reject it here rather than
    relying on how werkzeug handles a hash it cannot parse.
    """
    if not password_hash or password_hash.startswith(UNUSABLE_PASSWORD_PREFIX):
        return False
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


@cache
def get_password_validators() -> Iterable[pv.PasswordValidator]:
    """Build the validators on first use and share them thereafter.

    They are stateless, and SafeCommonPasswordValidator reads Django's gzipped
    common-password list when constructed - too costly to repeat per password.
    The attribute names must be materialised (not a generator) because the
    similarity validator stores the iterable it is given and iterates it on
    every validate() call.
    """
    return (
        pv.SafeCommonPasswordValidator(),
        pv.MinimumLengthValidator(min_length=10),
        pv.MaximumLengthValidator(max_length=256),
        pv.NumericPasswordValidator(),
        # this means we check every attribute of TempUser
        pv.UserAttributeSimilarityValidator(user_attributes=tuple(f.name for f in fields(TempUser))),
    )


def validate_password_strength(password: str, user: object) -> tuple[bool, str]:
    """
    Validate password strength requirements.

    Returns tuple of (is_valid, error_message)
    """
    # We use the well maintained Django password validation
    try:
        validate_password(password, user=user, password_validators=get_password_validators())
    except ValidationError as error:
        return False, str(error)

    return True, ""


def password_validators_help_texts() -> list[str]:
    """
    Return a list of all help texts of all configured validators.
    """
    return [v.get_help_text() for v in get_password_validators()]


def password_validators_help_text_html() -> Markup:
    """
    Return an HTML string with all help texts of all configured validators
    in an <ul>.
    """
    help_items = [Markup("<li>{ht}</li>").format(ht=ht) for ht in password_validators_help_texts()]
    return Markup("<ul>{items}</ul>").format(items=Markup("").join(help_items))
