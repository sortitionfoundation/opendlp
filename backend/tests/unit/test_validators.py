"""ABOUTME: Unit tests for OpenDLP domain validators
ABOUTME: Tests field validators, URL validators, and email validation"""

import pytest
from wtforms import ValidationError

from opendlp.domain.validators import (
    RESERVED_SLUGS,
    GoogleSpreadsheetURLValidator,
    InvalidSlug,
    MockField,
    UrlSlugValidator,
    validate_bool,
    validate_choice,
    validate_email,
    validate_email_field,
    validate_integer,
)


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


class TestUrlSlugValidator:
    """Test cases for the registration page URL slug validator."""

    @pytest.mark.parametrize("slug", ["my-assembly", "abc", "a1-b2", "x", "a-b-c-d", "2024-citizens"])
    def test_accepts_valid_slugs(self, slug):
        assert UrlSlugValidator().validate(slug) == slug

    def test_rejects_empty_string(self):
        with pytest.raises(InvalidSlug, match="cannot be empty") as exc:
            UrlSlugValidator().validate("")
        assert exc.value.reason == "empty"

    @pytest.mark.parametrize(
        "slug",
        [
            "MyAssembly",
            "UPPER",
            "-leading",
            "trailing-",
            "has space",
            "under_score",
            "café",
            "double--hyphen",
            "dot.dot",
        ],
    )
    def test_rejects_malformed_slugs(self, slug):
        with pytest.raises(InvalidSlug) as exc:
            UrlSlugValidator().validate(slug)
        assert exc.value.reason == "malformed"

    def test_rejects_too_long_slug(self):
        with pytest.raises(InvalidSlug, match="longer than") as exc:
            UrlSlugValidator().validate("a" * 101)
        assert exc.value.reason == "too_long"

    @pytest.mark.parametrize("slug", sorted(RESERVED_SLUGS))
    def test_rejects_reserved_slugs(self, slug):
        with pytest.raises(InvalidSlug, match="reserved") as exc:
            UrlSlugValidator().validate(slug)
        assert exc.value.reason == "reserved"

    def test_invalid_slug_subclasses_value_error(self):
        with pytest.raises(ValueError):
            UrlSlugValidator().validate("BAD")


class TestValidateEmail:
    def test_accepts_valid_email(self):
        validate_email("alice@example.com")

    def test_rejects_missing_at(self):
        with pytest.raises(ValueError, match="Invalid email"):
            validate_email("not-an-email")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="Invalid email"):
            validate_email("")


class TestValidateEmailField:
    def test_accepts_valid_email(self):
        value, error = validate_email_field("alice@example.com")
        assert value == "alice@example.com"
        assert error is None

    def test_empty_returns_required_error(self):
        value, error = validate_email_field("")
        assert value is None
        assert error == "This field is required"

    def test_invalid_email_returns_error(self):
        value, error = validate_email_field("not-an-email")
        assert value is None
        assert "valid email" in error.lower()

    def test_rejects_at_only_value(self):
        value, error = validate_email_field("missing@domain")
        assert value is None
        assert "valid email" in error.lower()


class TestValidateBool:
    @pytest.mark.parametrize("raw", ["yes", "true", "1", "Yes", "TRUE"])
    def test_accepts_truthy_values(self, raw):
        cleaned, error = validate_bool(raw, allow_none=False)
        assert cleaned is True
        assert error is None

    @pytest.mark.parametrize("raw", ["no", "false", "0", "No"])
    def test_accepts_falsy_values(self, raw):
        cleaned, error = validate_bool(raw, allow_none=False)
        assert cleaned is False
        assert error is None

    def test_blank_returns_error_when_not_allowed(self):
        cleaned, error = validate_bool("", allow_none=False)
        assert cleaned is None
        assert error is not None

    def test_blank_returns_none_when_allowed(self):
        cleaned, error = validate_bool("", allow_none=True)
        assert cleaned is None
        assert error is None


class TestValidateChoice:
    def test_accepts_value_in_set(self):
        cleaned, error = validate_choice("blue", {"blue", "green"})
        assert cleaned == "blue"
        assert error is None

    def test_accepts_value_when_no_constraints(self):
        cleaned, error = validate_choice("anything", None)
        assert cleaned == "anything"
        assert error is None

    def test_empty_returns_error(self):
        cleaned, error = validate_choice("", {"blue", "green"})
        assert cleaned is None
        assert error is not None

    def test_unknown_value_returns_error(self):
        cleaned, error = validate_choice("purple", {"blue", "green"})
        assert cleaned is None
        assert "valid option" in error.lower()


class TestValidateInteger:
    def test_accepts_integer_string(self):
        cleaned, error = validate_integer("42")
        assert cleaned == 42
        assert error is None

    def test_accepts_negative(self):
        cleaned, error = validate_integer("-7")
        assert cleaned == -7
        assert error is None

    def test_empty_returns_error(self):
        cleaned, error = validate_integer("")
        assert cleaned is None
        assert error is not None

    def test_non_numeric_returns_error(self):
        cleaned, error = validate_integer("abc")
        assert cleaned is None
        assert "valid number" in error.lower()
