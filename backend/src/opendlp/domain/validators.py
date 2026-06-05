"""ABOUTME: Domain validators for OpenDLP
ABOUTME: Contains field validators, URL validators, and email validation"""

import re
from typing import Any
from urllib.parse import urlparse

import gspread.utils
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import EmailValidator
from wtforms import ValidationError
from wtforms.validators import URL

RESERVED_SLUGS = frozenset({"preview", "submit", "admin", "static", "assets"})

_SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_SLUG_MAX_LENGTH = 100


class InvalidSlug(ValueError):
    """A URL slug failed validation. ``reason`` is one of empty/too_long/malformed/reserved."""

    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        super().__init__(message)


class SlugError(ValueError):
    """A registration-page slug failed validation or uniqueness.

    ``field`` is one of ``"url_slug"`` or ``"short_url_slug"``.
    ``reason`` is one of ``"taken"``, ``"reserved"``, ``"malformed"``, ``"too_long"``, ``"empty"``.
    Subclasses ``ValueError`` so existing callers that catch ``ValueError`` continue to work.
    """

    def __init__(self, field: str, reason: str, message: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(message)


class UrlSlugValidator:
    """Validator for registration page URL slugs.

    Accepts lowercase ASCII alphanumerics and hyphens, 1-100 characters, with no
    leading or trailing hyphen. Rejects reserved values. Raises InvalidSlug on
    failure - this is a domain validator, not a WTForms one.
    """

    def validate(self, value: str) -> str:
        if not value:
            raise InvalidSlug("empty", "URL slug cannot be empty")
        if len(value) > _SLUG_MAX_LENGTH:
            raise InvalidSlug("too_long", f"URL slug cannot be longer than {_SLUG_MAX_LENGTH} characters")
        if not _SLUG_RE.match(value):
            raise InvalidSlug(
                "malformed",
                "URL slug must be lowercase letters, numbers and hyphens, with no leading or trailing hyphen",
            )
        if value in RESERVED_SLUGS:
            raise InvalidSlug("reserved", f"URL slug '{value}' is reserved and cannot be used")
        return value


class GoogleSpreadsheetURLValidator:
    """
    Validator for Google Spreadsheet URLs.

    Validates that a URL is:
    1. A valid URL (using WTForms URL validator)
    2. Uses HTTPS scheme
    3. Contains a Google Spreadsheet ID that can be extracted by gspread

    Can be used both as a WTForms validator and directly with validate_str().
    """

    def __init__(self, message: str | None = None) -> None:
        self.message = message
        self.url_validator = URL(allow_ip=False)

    def validate_str(self, url_str: str | None) -> None:
        """
        Validate a raw string as a Google Spreadsheet URL.

        Args:
            url_str: The URL string to validate

        Raises:
            ValidationError: If the URL is invalid
        """
        # Create a mock field object for WTForms validator
        mock_field = MockField(url_str)
        self(None, mock_field)

    def __call__(self, form: Any, field: Any) -> None:
        """
        WTForms validator interface.

        Args:
            form: The form (unused)
            field: The field containing the URL data

        Raises:
            ValidationError: If the URL is invalid
        """
        url = field.data

        # Handle None or empty string
        if not url:
            raise ValidationError(self.message or "Invalid URL - empty.")

        # First validate it's a proper URL using WTForms URL validator
        try:
            self.url_validator(form, field)
        except ValidationError as err:
            raise ValidationError(self.message or "Invalid URL.") from err

        # Parse the URL to check scheme
        parsed_url = urlparse(url)

        # Check that it uses HTTPS
        if parsed_url.scheme != "https":
            raise ValidationError(self.message or "Google Spreadsheet URLs must use HTTPS.")

        # Try to extract Google Spreadsheet ID using gspread
        try:
            gspread.utils.extract_id_from_url(url)
        except Exception as err:
            raise ValidationError(
                self.message or "Invalid Google Spreadsheet URL - could not find spreadsheet key."
            ) from err


class MockField:
    """Mock field object for internal use with WTForms validators."""

    def __init__(self, data: str | None) -> None:
        self.data = data

    def gettext(self, message: str) -> str:
        """Mock gettext method for WTForms compatibility."""
        return message


def validate_email(email: str) -> None:
    """Validate an email address using Django's EmailValidator. Raises ValueError on failure."""
    # we use the well-tested and maintained Django EmailValidator
    # Note that passing in the message is important - if we don't do that then
    # the validator will try to use the default message, which will trigger the
    # auto localisation of the string which then blows up.
    validator = EmailValidator(message="Invalid email address")
    try:
        validator(email)
    except DjangoValidationError as error:
        raise ValueError("Invalid email address") from error


def validate_bool(str_value: str, allow_none: bool) -> tuple[bool | None, str | None]:
    """Validate boolean from a radio button. Accepts yes/no/true/false/1/0 (case-insensitive).

    Returns (value, error). When allow_none is True a blank value returns (None, None)
    instead of an error.
    """
    lower = str_value.lower()
    if lower in ("yes", "true", "1"):
        return True, None
    if lower in ("no", "false", "0"):
        return False, None
    if allow_none:
        return None, None
    return None, "Please select Yes or No"


def validate_choice(str_value: str, valid_values: set[str] | None) -> tuple[str | None, str | None]:
    """Validate a choice field. Returns (value, error)."""
    if not str_value:
        return None, "Please select an option"
    if valid_values and str_value not in valid_values:
        return None, "Please select a valid option"
    return str_value, None


def validate_integer(str_value: str) -> tuple[int | None, str | None]:
    """Validate an integer field. Returns (value, error)."""
    if not str_value:
        return None, "This field is required"
    try:
        return int(str_value), None
    except ValueError:
        return None, "Please enter a valid number"


def validate_email_field(str_value: str) -> tuple[str | None, str | None]:
    """Validate an email form field. Returns (value, error).

    Wraps validate_email in the (value, error) tuple pattern used by form field validators.
    """
    if not str_value:
        return None, "This field is required"
    try:
        validate_email(str_value)
        return str_value, None
    except ValueError:
        return None, "Please enter a valid email address"
