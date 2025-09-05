"""ABOUTME: Domain validators for OpenDLP
ABOUTME: Contains custom validators including Google Spreadsheet URL validation"""

from typing import Any
from urllib.parse import urlparse

import gspread.utils
from wtforms import ValidationError
from wtforms.validators import URL


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
