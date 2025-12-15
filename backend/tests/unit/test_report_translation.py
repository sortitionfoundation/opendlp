"""ABOUTME: Unit tests for sortition run report translation helpers
ABOUTME: Tests translation of sortition_algorithms RunReport messages using message codes and parameters"""

from unittest.mock import patch

from sortition_algorithms.errors import BadDataError
from sortition_algorithms.utils import ReportLevel, RunReport

from opendlp.service_layer.report_translation import translate_run_report_to_html


class TestTranslateRunReportToHtml:
    """Tests for translating RunReport messages to HTML"""

    def test_translate_report_with_message_code(self) -> None:
        """Should translate line with message_code using translation key"""
        report = RunReport()
        report.add_message("loading_features_from_file", file_path="/path/to/features.csv")

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:
            mock_gettext.return_value = "Chargement des caractéristiques depuis le fichier %(file_path)s."

            result = translate_run_report_to_html(report)

            mock_gettext.assert_called_once_with("report.loading_features_from_file")
            assert "Chargement des caractéristiques depuis le fichier /path/to/features.csv." in result

    def test_translate_report_without_message_code_uses_english(self) -> None:
        """Should use English line text when no message_code is present"""
        report = RunReport()
        report.add_line("This is an English message without a code")

        result = translate_run_report_to_html(report)

        assert "This is an English message without a code" in result

    def test_translate_report_with_multiple_messages(self) -> None:
        """Should translate multiple messages in sequence"""
        report = RunReport()
        report.add_message("loading_features_from_string")
        report.add_message("features_found", count=5)
        report.add_line("Some untranslated message")

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:

            def fake_gettext(key: str) -> str:
                translations = {
                    "report.loading_features_from_string": "Chargement des caractéristiques depuis une chaîne.",
                    "report.features_found": "Nombre de caractéristiques trouvées: %(count)s",
                }
                return translations.get(key, key)

            mock_gettext.side_effect = fake_gettext

            result = translate_run_report_to_html(report)

            assert "Chargement des caractéristiques depuis une chaîne." in result
            assert "Nombre de caractéristiques trouvées: 5" in result
            assert "Some untranslated message" in result
            # Should be separated by <br />
            assert "<br />" in result

    def test_translate_report_handles_translation_failure(self) -> None:
        """Should fall back to English if translation fails"""
        report = RunReport()
        report.add_message("trial_number", trial=3)

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:
            # Return a template with wrong parameter name
            mock_gettext.return_value = "Trial: %(wrong_param)s"

            result = translate_run_report_to_html(report)

            # Should fall back to original English message
            assert "Trial number: 3" in result

    def test_translate_report_with_important_level(self) -> None:
        """Should wrap important messages in bold tags"""
        report = RunReport()
        report.add_message("selection_success", level=ReportLevel.IMPORTANT)

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:
            mock_gettext.return_value = "SUCCÈS!! Final:"

            result = translate_run_report_to_html(report)

            assert "<b>SUCCÈS!! Final:</b>" in result

    def test_translate_report_with_critical_level(self) -> None:
        """Should wrap critical messages in bold red tags"""
        report = RunReport()
        report.add_message("selection_failed", level=ReportLevel.CRITICAL, attempts=10)

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:
            mock_gettext.return_value = "Échec %(attempts)s fois. Abandonné."

            result = translate_run_report_to_html(report)

            assert '<b style="color: red">Échec 10 fois. Abandonné.</b>' in result

    def test_translate_report_with_table_passes_through(self) -> None:
        """Should pass table through as HTML without translation"""
        report = RunReport()
        report.add_table(
            table_headings=["Feature", "Min", "Max"],
            table_data=[["Age", 18, 65], ["Gender", 0, 100]],
        )

        result = translate_run_report_to_html(report)

        # Should contain HTML table markup
        assert "<table>" in result
        assert "<th>Feature" in result
        assert "<td>Age" in result
        assert "18</td>" in result

    def test_translate_report_with_error_uses_error_translation(self) -> None:
        """Should translate errors using error_translation module"""
        report = RunReport()
        error = BadDataError(
            message="No 'id' column found!",
            error_code="missing_column",
            error_params={"column": "id", "error_label": "", "data_container": "CSV"},
        )
        report.add_error(error, is_fatal=True)

        with patch("opendlp.service_layer.report_translation.translate_sortition_error_to_html") as mock_translate:
            mock_translate.return_value = "Colonne 'id' manquante dans CSV"

            result = translate_run_report_to_html(report)

            # Should call error translation
            mock_translate.assert_called_once_with(error)
            # Should wrap fatal error in bold tags
            assert "<b>Colonne 'id' manquante dans CSV</b>" in result

    def test_translate_report_with_non_fatal_error(self) -> None:
        """Should not wrap non-fatal errors in bold tags"""
        report = RunReport()
        error = BadDataError(message="Warning: something unusual")
        report.add_error(error, is_fatal=False)

        with patch("opendlp.service_layer.report_translation.translate_sortition_error_to_html") as mock_translate:
            mock_translate.return_value = "Avertissement: quelque chose d'inhabituel"

            result = translate_run_report_to_html(report)

            # Should not have bold tags for non-fatal
            assert result == "Avertissement: quelque chose d'inhabituel"
            assert "<b>" not in result

    def test_translate_report_with_logged_messages_included_by_default(self) -> None:
        """Should include logged messages by default"""
        report = RunReport()
        report.add_message_and_log("trial_number", log_level=20, trial=1)  # INFO level

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:
            mock_gettext.return_value = "Essai numéro: %(trial)s"

            result = translate_run_report_to_html(report, include_logged=True)

            assert "Essai numéro: 1" in result

    def test_translate_report_with_logged_messages_excluded(self) -> None:
        """Should exclude logged messages when include_logged=False"""
        report = RunReport()
        report.add_message_and_log("trial_number", log_level=20, trial=1)
        report.add_message("loading_features_from_string")

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:

            def fake_gettext(key: str) -> str:
                translations = {
                    "report.trial_number": "Trial: %(trial)s",
                    "report.loading_features_from_string": "Loading features...",
                }
                return translations.get(key, key)

            mock_gettext.side_effect = fake_gettext

            result = translate_run_report_to_html(report, include_logged=False)

            # Should exclude the logged message
            assert "Trial: 1" not in result
            # But include the non-logged message
            assert "Loading features..." in result

    def test_translate_report_escapes_html_in_messages(self) -> None:
        """Should escape HTML characters in translated messages"""
        report = RunReport()
        report.add_line("Message with <script>alert('xss')</script> tags")

        result = translate_run_report_to_html(report)

        # Should escape HTML tags
        assert "&lt;script&gt;" in result
        assert "&lt;/script&gt;" in result
        assert "<script>" not in result

    def test_translate_report_complex_integration(self) -> None:
        """Integration test with mixed content types"""
        report = RunReport()

        # Add various types of content
        report.add_message("loading_features_from_file", file_path="features.csv")
        report.add_message("features_found", count=3)
        report.add_table(
            table_headings=["Feature", "Values"],
            table_data=[["Age", 5], ["Gender", 3]],
        )
        report.add_message("using_legacy_algorithm")
        error = BadDataError(message="Test error", error_code="test_error", error_params={})
        report.add_error(error, is_fatal=False)
        report.add_message("selection_success", level=ReportLevel.IMPORTANT)

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:

            def fake_gettext(key: str) -> str:
                translations = {
                    "report.loading_features_from_file": "Chargement: %(file_path)s",
                    "report.features_found": "Trouvé: %(count)s",
                    "report.using_legacy_algorithm": "Utilisation de l'algorithme hérité.",
                    "report.selection_success": "SUCCÈS!!",
                }
                return translations.get(key, key)

            mock_gettext.side_effect = fake_gettext

            with patch(
                "opendlp.service_layer.report_translation.translate_sortition_error_to_html"
            ) as mock_error_translate:
                mock_error_translate.return_value = "Erreur de test"

                result = translate_run_report_to_html(report)

                # Check all elements present
                assert "Chargement: features.csv" in result
                assert "Trouvé: 3" in result
                assert "<table>" in result
                # The apostrophe gets HTML-escaped
                assert "Utilisation de l" in result and "algorithme hérité." in result
                assert "Erreur de test" in result
                assert "<b>SUCCÈS!!</b>" in result
                assert "<br />" in result


class TestReportTranslationEdgeCases:
    """Tests for edge cases and error conditions"""

    def test_translate_empty_report(self) -> None:
        """Should handle empty report gracefully"""
        report = RunReport()

        result = translate_run_report_to_html(report)

        assert result == ""

    def test_translate_report_with_empty_params(self) -> None:
        """Should handle message with no parameters"""
        report = RunReport()
        report.add_message("using_legacy_algorithm")  # No params

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:
            mock_gettext.return_value = "Using legacy algorithm."

            result = translate_run_report_to_html(report)

            assert "Using legacy algorithm." in result

    def test_translate_report_with_special_characters_in_params(self) -> None:
        """Should handle special characters in parameters"""
        report = RunReport()
        report.add_message("loading_features_from_file", file_path="/path/with/spëcial/chàrs/文件.csv")

        with patch("opendlp.service_layer.report_translation._") as mock_gettext:
            mock_gettext.return_value = "Loading: %(file_path)s"

            result = translate_run_report_to_html(report)

            assert "Loading: /path/with/spëcial/chàrs/文件.csv" in result
