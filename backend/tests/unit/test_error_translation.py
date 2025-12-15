"""ABOUTME: Unit tests for sortition error translation helpers
ABOUTME: Tests translation of sortition_algorithms errors using error codes and parameters"""

from typing import cast
from unittest.mock import patch

from sortition_algorithms.errors import (
    BadDataError,
    ParseTableErrorMsg,
    ParseTableMultiError,
    ParseTableMultiValueErrorMsg,
    SelectionError,
    SelectionMultilineError,
)

from opendlp.service_layer.error_translation import (
    translate_sortition_error,
    translate_sortition_error_to_html,
)


class TestTranslateSimpleError:
    """Tests for translating simple sortition errors (BadDataError, SelectionError, etc.)"""

    def test_translate_error_with_error_code_and_params(self) -> None:
        """Should translate error using error_code and error_params"""
        error = BadDataError(
            message="No 'id' column for people found in CSV file!",
            error_code="missing_column",
            error_params={"column": "id", "error_label": "for people", "data_container": "CSV file"},
        )

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:
            # Mock gettext to return a format string
            mock_gettext.return_value = "Missing '%(column)s' column %(error_label)s in %(data_container)s!"

            result = translate_sortition_error(error)

            # Verify it called gettext with the right key
            mock_gettext.assert_called_once_with("errors.missing_column")
            # Verify the result has parameters substituted
            assert result == "Missing 'id' column for people in CSV file!"

    def test_translate_error_without_error_code_falls_back_to_english(self) -> None:
        """Should use English message when error_code is empty"""
        error = BadDataError(message="Something went wrong")

        result = translate_sortition_error(error)

        assert result == "Something went wrong"

    def test_translate_error_when_translation_fails_falls_back_to_english(self) -> None:
        """Should fall back to English if translation raises exception"""
        error = SelectionError(
            message="Selection failed",
            error_code="some_error",
            error_params={"foo": "bar"},
        )

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:
            # Make gettext return something that will fail parameter substitution
            mock_gettext.return_value = "Translated message with %(wrong_param)s"

            result = translate_sortition_error(error)

            # Should fall back to English message
            assert result == "Selection failed"

    def test_translate_non_sortition_error_returns_string(self) -> None:
        """Should handle non-sortition errors by returning str(error)"""
        error = ValueError("This is not a sortition error")

        result = translate_sortition_error(error)

        assert result == "This is not a sortition error"

    def test_translate_error_to_html_same_as_text_for_simple_errors(self) -> None:
        """HTML version should produce same result as text for simple errors"""
        error = BadDataError(
            message="No 'name' column found!",
            error_code="missing_column",
            error_params={"column": "name", "error_label": "", "data_container": "spreadsheet"},
        )

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:
            mock_gettext.return_value = "Column '%(column)s' not found in %(data_container)s"

            text_result = translate_sortition_error(error)
            html_result = translate_sortition_error_to_html(error)

            # For simple errors, text and HTML should be identical
            assert text_result == html_result
            assert html_result == "Column 'name' not found in spreadsheet"


class TestTranslateParseTableMultiError:
    """Tests for translating ParseTableMultiError (validation errors with multiple sub-errors)"""

    def test_translate_parse_error_with_single_column_errors(self) -> None:
        """Should translate each sub-error and add row/column context"""
        sub_errors: list[ParseTableErrorMsg] = [
            ParseTableErrorMsg(
                row=2,
                row_name="person_123",
                key="age",
                value="abc",
                msg="'abc' is not a number",
                error_code="not_a_number",
                error_params={"value": "abc"},
            ),
            ParseTableErrorMsg(
                row=3,
                row_name="person_456",
                key="gender",
                value="",
                msg="Empty value in gender feature",
                error_code="empty_value_in_feature",
                error_params={"feature_column_name": "gender", "feature_name": "Gender"},
            ),
        ]
        error = ParseTableMultiError(errors=cast(list[ParseTableErrorMsg | ParseTableMultiValueErrorMsg], sub_errors))

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:

            def fake_gettext(key: str) -> str:
                # Mock translations for error codes and context templates
                translations = {
                    "errors.not_a_number": "'%(value)s' is not a valid number",
                    "errors.empty_value_in_feature": "Empty value in %(feature_column_name)s %(feature_name)s",
                    "errors.parse_error_single_column": "%(msg)s: for row %(row)s, column header %(key)s",
                }
                return translations.get(key, key)

            mock_gettext.side_effect = fake_gettext

            result = translate_sortition_error(error)

            # Should have translated both errors with context
            assert "'abc' is not a valid number: for row 2, column header age" in result
            assert "Empty value in gender Gender: for row 3, column header gender" in result
            # Should be separated by newlines
            assert "\n" in result

    def test_translate_parse_error_with_multi_column_error(self) -> None:
        """Should translate multi-column errors with keys joined by commas"""
        sub_error = ParseTableMultiValueErrorMsg(
            row=5,
            row_name="feature_age",
            keys=["min", "max"],
            values=["50", "30"],
            msg="Minimum (50) should not be greater than maximum (30)",
            error_code="min_greater_than_max",
            error_params={"min": "50", "max": "30"},
        )
        error = ParseTableMultiError(errors=[sub_error])

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:

            def fake_gettext(key: str) -> str:
                translations = {
                    "errors.min_greater_than_max": "Min (%(min)s) > Max (%(max)s)",
                    "errors.parse_error_multi_column": "%(msg)s: for row %(row)s, column headers %(keys)s",
                }
                return translations.get(key, key)

            mock_gettext.side_effect = fake_gettext

            result = translate_sortition_error(error)

            assert "Min (50) > Max (30): for row 5, column headers min, max" in result

    def test_translate_parse_error_without_error_code_falls_back_to_english(self) -> None:
        """Should use English message when sub-error has no error_code"""
        sub_error = ParseTableErrorMsg(
            row=1,
            row_name="person_1",
            key="email",
            value="invalid",
            msg="Invalid email format",
            error_code="",  # No error code
            error_params={},
        )
        error = ParseTableMultiError(errors=[sub_error])

        result = translate_sortition_error(error)

        # Should fall back to the str() representation of sub_error
        assert "Invalid email format: for row 1, column header email" in result

    def test_translate_parse_error_to_html_uses_br_separator(self) -> None:
        """HTML version should use <br /> instead of newlines"""
        sub_errors: list[ParseTableErrorMsg] = [
            ParseTableErrorMsg(
                row=1,
                row_name="p1",
                key="col1",
                value="val1",
                msg="Error 1",
                error_code="test_error",
                error_params={},
            ),
            ParseTableErrorMsg(
                row=2,
                row_name="p2",
                key="col2",
                value="val2",
                msg="Error 2",
                error_code="test_error",
                error_params={},
            ),
        ]
        error = ParseTableMultiError(errors=cast(list[ParseTableErrorMsg | ParseTableMultiValueErrorMsg], sub_errors))

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:

            def fake_gettext(key: str) -> str:
                translations = {
                    "errors.test_error": "Test error",
                    "errors.parse_error_single_column": "%(msg)s: row %(row)s, col %(key)s",
                }
                return translations.get(key, key)

            mock_gettext.side_effect = fake_gettext

            html_result = translate_sortition_error_to_html(error)
            text_result = translate_sortition_error(error)

            # HTML should use <br />
            assert "<br />" in html_result
            assert "\n" not in html_result

            # Text should use newline
            assert "\n" in text_result
            assert "<br />" not in text_result

    def test_translate_parse_error_handles_translation_failure(self) -> None:
        """Should fall back to original message if translation fails"""
        sub_error = ParseTableErrorMsg(
            row=1,
            row_name="p1",
            key="test",
            value="val",
            msg="Original message",
            error_code="some_error",
            error_params={"param": "value"},
        )
        error = ParseTableMultiError(errors=[sub_error])

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:
            # Make translation fail with wrong parameters
            mock_gettext.side_effect = lambda key: "Translation %(wrong_param)s" if "error" in key else key

            result = translate_sortition_error(error)

            # Should fall back to original message
            assert "Original message" in result


class TestErrorTranslationIntegration:
    """Integration tests using real error messages from sortition_algorithms"""

    def test_real_spreadsheet_not_found_error(self) -> None:
        """Test with actual spreadsheet_not_found error from library"""
        error = SelectionError(
            message="Google spreadsheet not found: MySpreadsheet.",
            error_code="spreadsheet_not_found",
            error_params={"spreadsheet_name": "MySpreadsheet"},
        )

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:
            # Simulate the actual translation lookup
            mock_gettext.return_value = "Spreadsheet non trouvé: %(spreadsheet_name)s"

            result = translate_sortition_error(error)

            mock_gettext.assert_called_once_with("errors.spreadsheet_not_found")
            assert result == "Spreadsheet non trouvé: MySpreadsheet"

    def test_real_tab_not_found_error(self) -> None:
        """Test with actual tab_not_found error from library"""
        error = SelectionError(
            message="Error in Google sheet: no tab called 'Features' found in spreadsheet 'Test Sheet'.",
            error_code="tab_not_found",
            error_params={"tab_name": "Features", "spreadsheet_title": "Test Sheet"},
        )

        with patch("opendlp.service_layer.error_translation._") as mock_gettext:
            mock_gettext.return_value = "Onglet '%(tab_name)s' introuvable dans la feuille '%(spreadsheet_title)s'"

            result = translate_sortition_error(error)

            assert result == "Onglet 'Features' introuvable dans la feuille 'Test Sheet'"

    def test_real_infeasible_quotas_multiline_error(self) -> None:
        """Test with actual multiline error for infeasible quotas"""
        error = SelectionMultilineError(
            lines=[
                "The quotas are infeasible:",
                "Inconsistent numbers in min and max in the feature input:",
                "The smallest maximum is 5 for feature 'Young'",
                "The largest minimum is 10 for feature 'Old'",
            ],
            error_code="infeasible_quotas_header",
            error_params={},
        )

        # SelectionMultilineError messages are pre-formatted, so we return them as-is
        result = translate_sortition_error(error)

        # Should return the original formatted message
        assert "The quotas are infeasible:" in result
        assert "Inconsistent numbers in min and max" in result
