"""ABOUTME: Tests that infrastructure failures in optional page lookups are not swallowed
ABOUTME: A swallowed database error leaves the surrounding transaction poisoned, so pages must fail loudly"""

from unittest.mock import patch

import pytest


def boom():
    """A failure that is not a domain error - what a dropped connection looks like."""
    return RuntimeError("database connection lost")


class TestRespondentsPageErrorPropagation:
    """The respondents page treats a missing gsheet/CSV config as normal.

    That must not extend to infrastructure failures from the same calls.
    """

    URL = "/backoffice/assembly/{}/respondents"

    def test_gsheet_lookup_failure_is_not_suppressed(self, logged_in_admin, existing_assembly):
        with patch("opendlp.entrypoints.blueprints.respondents.get_assembly_gsheet", side_effect=boom()):
            response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 302

    def test_csv_status_lookup_failure_is_not_suppressed(self, logged_in_admin, existing_assembly):
        with patch("opendlp.entrypoints.blueprints.respondents.get_csv_upload_status", side_effect=boom()):
            response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 302

    def test_missing_gsheet_config_still_renders(self, logged_in_admin, existing_assembly):
        """The reason the suppression existed: a fresh assembly has no config."""
        response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 200


class TestRespondentSchemaPageErrorPropagation:
    """This view handles only the domain errors, so anything else must surface as a 500."""

    URL = "/backoffice/assembly/{}/respondent-schema"

    def test_gsheet_lookup_failure_is_not_suppressed(self, logged_in_admin, existing_assembly):
        with (
            patch("opendlp.entrypoints.blueprints.respondent_field_schema.get_assembly_gsheet", side_effect=boom()),
            pytest.raises(RuntimeError),
        ):
            logged_in_admin.get(self.URL.format(existing_assembly.id))

    def test_csv_status_lookup_failure_is_not_suppressed(self, logged_in_admin, existing_assembly):
        with (
            patch("opendlp.entrypoints.blueprints.respondent_field_schema.get_csv_upload_status", side_effect=boom()),
            pytest.raises(RuntimeError),
        ):
            logged_in_admin.get(self.URL.format(existing_assembly.id))

    def test_page_still_renders_without_any_config(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 200


class TestTargetsPageErrorPropagation:
    URL = "/backoffice/assembly/{}/targets"

    def test_gsheet_lookup_failure_is_not_suppressed(self, logged_in_admin, existing_assembly):
        with patch("opendlp.entrypoints.blueprints.targets.get_assembly_gsheet", side_effect=boom()):
            response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 302

    def test_csv_status_lookup_failure_is_not_suppressed(self, logged_in_admin, existing_assembly):
        with patch("opendlp.entrypoints.blueprints.targets.get_csv_upload_status", side_effect=boom()):
            response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 302

    def test_permission_check_failure_is_not_swallowed(self, logged_in_admin, existing_assembly):
        """`_can_manage` used to report "no permission" for any failure at all."""
        with patch("opendlp.entrypoints.blueprints.targets.can_manage_assembly", side_effect=boom()):
            response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 302

    def test_page_still_renders_without_any_config(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 200


class TestSelectionPageErrorPropagation:
    URL = "/backoffice/assembly/{}/selection"

    def test_gsheet_lookup_failure_is_not_suppressed(self, logged_in_admin, existing_assembly):
        with patch("opendlp.entrypoints.blueprints.gsheets.get_assembly_gsheet", side_effect=boom()):
            response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 302

    def test_csv_status_lookup_failure_is_not_suppressed(self, logged_in_admin, existing_assembly):
        with patch("opendlp.entrypoints.blueprints.gsheets.get_csv_upload_status", side_effect=boom()):
            response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 302

    def test_page_still_renders_without_any_config(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(self.URL.format(existing_assembly.id))

        assert response.status_code == 200
