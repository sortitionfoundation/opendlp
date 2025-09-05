"""ABOUTME: Unit tests for OpenDLP domain validators
ABOUTME: Tests URL validation and Google Spreadsheet URL validation"""

import pytest
from wtforms import ValidationError

from opendlp.domain.validators import GoogleSpreadsheetURLValidator, MockField


class TestGoogleSpreadsheetURLValidator:
    """Test cases for Google Spreadsheet URL validator."""

    def test_validate_str_empty_string_raises_validation_error(self):
        """Empty string should raise ValidationError."""
        validator = GoogleSpreadsheetURLValidator()

        with pytest.raises(ValidationError, match="Invalid URL"):
            validator.validate_str("")

    def test_validate_str_none_value_raises_validation_error(self):
        """None value should raise ValidationError."""
        validator = GoogleSpreadsheetURLValidator()

        with pytest.raises(ValidationError, match="Invalid URL"):
            validator.validate_str(None)

    def test_validate_str_invalid_url_raises_validation_error(self):
        """Invalid URL should raise ValidationError."""
        validator = GoogleSpreadsheetURLValidator()

        with pytest.raises(ValidationError, match="Invalid URL"):
            validator.validate_str("not-a-url")

    def test_validate_str_http_url_raises_validation_error(self):
        """HTTP URL (not HTTPS) should raise ValidationError."""
        validator = GoogleSpreadsheetURLValidator()

        with pytest.raises(ValidationError, match="Google Spreadsheet URLs must use HTTPS"):
            validator.validate_str("http://docs.google.com/spreadsheets/d/1234567890/edit")

    def test_validate_str_https_url_without_extractable_key_raises_validation_error(self):
        """HTTPS URL without extractable Google Spreadsheet ID should raise ValidationError."""
        validator = GoogleSpreadsheetURLValidator()

        with pytest.raises(ValidationError, match="Invalid Google Spreadsheet URL"):
            validator.validate_str("https://example.com/not-a-spreadsheet")

    def test_validate_str_valid_google_spreadsheet_url_passes(self):
        """Valid Google Spreadsheet URL should pass validation."""
        validator = GoogleSpreadsheetURLValidator()

        # This should not raise any exception
        validator.validate_str(
            "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
        )

    def test_validate_str_valid_google_spreadsheet_url_with_gid_passes(self):
        """Valid Google Spreadsheet URL with gid parameter should pass validation."""
        validator = GoogleSpreadsheetURLValidator()

        # This should not raise any exception
        validator.validate_str(
            "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit#gid=0"
        )

    def test_validate_str_valid_google_spreadsheet_url_with_additional_params_passes(self):
        """Valid Google Spreadsheet URL with additional parameters should pass validation."""
        validator = GoogleSpreadsheetURLValidator()

        # This should not raise any exception
        validator.validate_str(
            "https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit?usp=sharing"
        )

    def test_validate_str_different_google_domains_pass(self):
        """Google Spreadsheet URLs from different Google domains should pass."""
        validator = GoogleSpreadsheetURLValidator()

        # Test various Google domain variations
        domains = [
            "docs.google.com",
            "drive.google.com",
        ]

        for domain in domains:
            url = f"https://{domain}/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
            # This should not raise any exception
            validator.validate_str(url)

    def test_validate_str_non_google_https_url_raises_validation_error(self):
        """HTTPS URL that's not a Google Spreadsheet should raise ValidationError."""
        validator = GoogleSpreadsheetURLValidator()

        with pytest.raises(ValidationError, match="Invalid Google Spreadsheet URL"):
            validator.validate_str("https://github.com/some/repo")

    def test_validate_str_malformed_google_spreadsheet_url_raises_validation_error(self):
        """Malformed Google Spreadsheet URL should raise ValidationError."""
        validator = GoogleSpreadsheetURLValidator()

        # Missing spreadsheet ID
        with pytest.raises(ValidationError, match="Invalid Google Spreadsheet URL"):
            validator.validate_str("https://docs.google.com/spreadsheets/d/")

    def test_validate_str_custom_error_message(self):
        """Custom error message should be used when provided."""
        custom_message = "Please provide a valid Google Spreadsheet URL"
        validator = GoogleSpreadsheetURLValidator(message=custom_message)

        with pytest.raises(ValidationError, match=custom_message):
            validator.validate_str("not-a-url")

    def test_wtforms_field_validation_happy_path(self):
        """WTForms field validation should work with valid Google Spreadsheet URL."""
        validator = GoogleSpreadsheetURLValidator()
        field = MockField("https://docs.google.com/spreadsheets/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit")

        # This should not raise any exception
        validator(None, field)

    def test_wtforms_field_validation_unhappy_path(self):
        """WTForms field validation should raise ValidationError for invalid URL."""
        validator = GoogleSpreadsheetURLValidator()
        field = MockField("not-a-url")

        with pytest.raises(ValidationError, match="Invalid URL"):
            validator(None, field)
