# ABOUTME: Component tests for backoffice gsheet config + selection-tab routes over a FakeUnitOfWork
# ABOUTME: Drives the real gsheet/selection Flask routes + services against a seeded fake store, no PostgreSQL

import uuid

import pytest
from flask.testing import FlaskClient

from opendlp.adapters import database
from opendlp.domain.assembly import Assembly, AssemblyGSheet, SelectionRunRecord
from opendlp.domain.value_objects import SelectionRunStatus, SelectionTaskType
from tests.fakes import FakeUnitOfWork


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """GSheet/settings writes call SQLAlchemy flag_modified, which needs mapped classes."""
    database.start_mappers()


def _sheet_dialog(client: FlaskClient, assembly: Assembly):
    """The data source dialog showing the Google Sheets settings, whether or not the project has a sheet yet."""
    return client.post(
        f"/backoffice/project/{assembly.id}/data-source/refresh",
        data={"location": "gsheet"},
        headers={"HX-Request": "true"},
    )


class TestBackofficeGSheetConfigForm:
    """The Google Sheets settings in the data source dialog."""

    def test_gsheet_form_shows_new_mode_when_no_config_exists(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that new gsheet form is shown when no config exists."""
        response = _sheet_dialog(logged_in_admin, existing_assembly)
        assert response.status_code == 200
        assert b'name="url"' in response.data
        assert b"Save" in response.data or b"submit" in response.data.lower()

    def test_gsheet_form_contains_required_fields(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that gsheet form contains all required fields."""
        response = _sheet_dialog(logged_in_admin, existing_assembly)
        assert response.status_code == 200

        assert b'name="url"' in response.data
        assert b"select_registrants_tab" in response.data
        assert b"select_targets_tab" in response.data
        assert b"check_same_address" in response.data

    def test_gsheet_form_shows_the_saved_settings_when_config_exists(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that the saved settings are shown, ready to edit, when a gsheet config exists."""
        assembly, _ = assembly_with_gsheet
        response = _sheet_dialog(logged_in_admin, assembly)
        assert response.status_code == 200
        assert b"Edit" in response.data or b"edit" in response.data.lower()
        assert b"docs.google.com/spreadsheets" in response.data

    def test_gsheet_form_can_be_saved_or_closed_when_config_exists(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that the form of an existing config offers Save and Close."""
        assembly, _ = assembly_with_gsheet
        response = _sheet_dialog(logged_in_admin, assembly)
        assert response.status_code == 200
        assert b'name="url"' in response.data
        assert b"Save" in response.data or b"submit" in response.data.lower()
        assert b"Close" in response.data

    def test_gsheet_form_shows_default_values_in_new_mode(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that form defaults are shown when creating new gsheet config."""
        response = _sheet_dialog(logged_in_admin, existing_assembly)
        assert response.status_code == 200
        assert b"Respondents" in response.data
        assert b"Categories" in response.data
        assert b"Selected" in response.data

    def test_gsheet_form_contains_all_fields(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that gsheet form contains all key configuration fields."""
        response = _sheet_dialog(logged_in_admin, existing_assembly)
        assert response.status_code == 200

        assert b'name="url"' in response.data
        assert b"select_registrants_tab" in response.data
        assert b"select_targets_tab" in response.data
        assert b"already_selected_tab" in response.data
        assert b"id_column" in response.data
        assert b"check_same_address_cols_string" in response.data or b"address" in response.data.lower()
        assert b"columns_to_keep_string" in response.data or b"columns" in response.data.lower()
        assert b"check_same_address" in response.data
        assert b"generate_remaining_tab" in response.data


class TestBackofficeGSheetFormSubmission:
    """Test gsheet form submission rendering and validation branches."""

    def test_create_gsheet_config_validation_error_missing_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test validation error when creating gsheet config without URL."""
        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert b'name="url"' in response.data

    def test_create_gsheet_config_validation_error_invalid_url(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test validation error when creating gsheet config with invalid URL."""
        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "https://example.com/not-a-google-sheet",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422

    def test_update_gsheet_config_validation_error(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test validation error when updating gsheet config with invalid data."""
        assembly, _ = assembly_with_gsheet
        response = logged_in_admin.post(
            f"/backoffice/project/{assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert b'name="url"' in response.data

    def test_create_gsheet_shows_warning_for_empty_columns_to_keep(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that warning is shown when columns_to_keep is empty."""
        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "https://docs.google.com/spreadsheets/d/1warningtest/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "id",
                "generate_remaining_tab": "y",
                "columns_to_keep_string": "",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        with logged_in_admin.session_transaction() as session:
            warnings = [message for category, message in session.get("_flashes", []) if category == "warning"]
        assert any("No columns to keep" in message for message in warnings)

    def test_create_gsheet_no_warning_for_empty_columns_with_team(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that team-based defaults prevent columns_to_keep warning."""
        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "https://docs.google.com/spreadsheets/d/1nowarningtest/edit",
                "team": "uk",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address": "y",
                "check_same_address_cols_string": "address1, postcode",
                "columns_to_keep_string": "",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        with logged_in_admin.session_transaction() as session:
            flashes = list(session.get("_flashes", []))
        assert ("success", "Data source settings saved") in [tuple(flash) for flash in flashes]
        assert not [message for category, message in flashes if category == "warning"]

    def test_gsheet_permission_denied_for_regular_user(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test regular users cannot access or submit gsheet configuration."""
        get_response = _sheet_dialog(logged_in_user, existing_assembly)
        assert get_response.status_code in [302, 403]

    def test_gsheet_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Test gsheet page redirects to login when not authenticated."""
        response = _sheet_dialog(client, existing_assembly)
        assert response.status_code == 302
        assert "login" in response.location


class TestBackofficeGSheetValidation:
    """Test gsheet-specific validation rules."""

    def test_hard_validation_check_address_without_columns(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation: check_same_address=True requires address columns."""
        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "https://docs.google.com/spreadsheets/d/validation123/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address": "y",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "first_name, last_name",
            },
        )
        assert response.status_code == 422
        assert b"address columns" in response.data.lower() or b"must specify" in response.data.lower()

    def test_hard_validation_passes_when_team_not_other(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation passes when team auto-generates address columns."""
        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "https://docs.google.com/spreadsheets/d/validation_team_123/edit",
                "team": "uk",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address": "y",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "first_name, last_name",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response.headers

    def test_hard_validation_passes_when_check_address_disabled(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test hard validation: check_same_address=False allows empty address columns."""
        response = logged_in_admin.post(
            f"/backoffice/project/{existing_assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "https://docs.google.com/spreadsheets/d/validation_pass_123/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "first_name, last_name",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert "HX-Redirect" in response.headers

    def test_hard_validation_on_edit(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test hard validation on edit: check_same_address=True requires address columns."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.post(
            f"/backoffice/project/{assembly.id}/data-source/save",
            data={
                "location": "gsheet",
                "url": "https://docs.google.com/spreadsheets/d/edit_validation_123/edit",
                "team": "other",
                "select_registrants_tab": "Respondents",
                "select_targets_tab": "Categories",
                "replace_registrants_tab": "Remaining",
                "replace_targets_tab": "Replacement Categories",
                "already_selected_tab": "Selected",
                "id_column": "test_id",
                "check_same_address": "y",
                "check_same_address_cols_string": "",
                "columns_to_keep_string": "first_name, last_name",
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 422
        assert b"address columns" in response.data.lower() or b"must specify" in response.data.lower()

    def test_url_validation_enforced(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Test that URL validation is properly enforced for various invalid URLs."""
        invalid_urls = [
            "not-a-url",
            "https://example.com/not-google-sheets",
            "https://drive.google.com/file/d/wrong-format",
            "",
        ]

        for invalid_url in invalid_urls:
            response = logged_in_admin.post(
                f"/backoffice/project/{existing_assembly.id}/data-source/save",
                data={
                    "location": "gsheet",
                    "url": invalid_url,
                    "team": "uk",
                    "select_registrants_tab": "Test",
                    "select_targets_tab": "Test",
                    "replace_registrants_tab": "Remaining",
                    "replace_targets_tab": "Replacement",
                    "already_selected_tab": "Selected",
                    "id_column": "test_id",
                },
                headers={"HX-Request": "true"},
            )
            assert response.status_code == 422, f"Expected a refusal for invalid URL: {invalid_url}"


class TestBackofficeSelectionTab:
    """Test selection-tab routes that render before any Celery dispatch."""

    def test_selection_page_loads_without_gsheet_config(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """With no gsheet config the project is held in OpenDLP: the page says what selection waits for."""
        response = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}/selection")
        assert response.status_code == 200
        assert b"Before you can run a selection:" in response.data
        assert b"Check Spreadsheet" not in response.data

    def test_selection_page_loads_with_gsheet_config(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that selection page loads when gsheet is configured."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/project/{assembly.id}/selection")
        assert response.status_code == 200
        assert b"Selection" in response.data

    def test_selection_page_redirects_when_not_logged_in(
        self, client: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/project/{existing_assembly.id}/selection")
        assert response.status_code == 302
        assert "login" in response.location

    def test_selection_page_shows_history_section(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that selection page contains Selection History section."""
        assembly, _gsheet = assembly_with_gsheet
        response = logged_in_admin.get(f"/backoffice/project/{assembly.id}/selection")
        assert response.status_code == 200
        assert b"Selection History" in response.data

    def test_selection_with_run_page_redirects_to_query_param(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: tuple[Assembly, AssemblyGSheet]
    ) -> None:
        """Test that legacy /selection/<run_id> URL redirects to query param version."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = uuid.uuid4()
        response = logged_in_admin.get(f"/backoffice/project/{assembly.id}/selection/{run_id}")
        assert response.status_code == 302
        assert f"current_selection={run_id}" in response.location


class TestGsheetTaskThatCannotBeSent:
    @pytest.mark.parametrize(
        "path",
        ["selection/load", "selection/run", "manage-tabs/start-list", "manage-tabs/start-delete", "replacement/load"],
    )
    def test_the_organiser_is_told_and_the_run_is_failed(
        self, logged_in_admin, assembly_with_gsheet, fake_store, task_runner, path
    ):
        assembly, _gsheet = assembly_with_gsheet
        task_runner.fail_dispatch = ConnectionError("broker down")

        response = logged_in_admin.post(f"/backoffice/project/{assembly.id}/{path}")

        assert response.status_code == 302
        html = logged_in_admin.get(response.location, follow_redirects=True).data.decode()
        assert "The task could not be started. Please try again." in html
        with FakeUnitOfWork(store=fake_store) as uow:
            (record,) = uow.selection_run_records.get_by_assembly_id(assembly.id)
            assert record.status == SelectionRunStatus.FAILED


class TestGsheetWritingRoutesLandInTheRunningTasksModal:
    """Select, replace and delete-tabs refuse while a writing task is unfinished and open its modal."""

    FLASH = "Another task is already running on this project"

    def _add_running(self, fake_store, assembly_id, task_type) -> uuid.UUID:
        run_id = uuid.uuid4()
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.selection_run_records.add(
                SelectionRunRecord(
                    assembly_id=assembly_id,
                    task_id=run_id,
                    task_type=task_type,
                    status=SelectionRunStatus.RUNNING,
                    log_messages=["Working..."],
                )
            )
            uow.commit()
        return run_id

    def _assert_modal(self, logged_in_admin, location: str, label: str) -> None:
        html = logged_in_admin.get(location).data.decode()
        assert self.FLASH in html
        assert label in html
        assert "Cancel Task" in html

    def test_run_selection_opens_the_running_selection(
        self, logged_in_admin, assembly_with_gsheet, fake_store, task_runner
    ):
        assembly, _gsheet = assembly_with_gsheet
        run_id = self._add_running(fake_store, assembly.id, SelectionTaskType.SELECT_GSHEET)

        response = logged_in_admin.post(f"/backoffice/project/{assembly.id}/selection/run")

        assert task_runner.submitted == []
        assert response.status_code == 302
        assert response.location.endswith(f"/selection?current_selection={run_id}")
        self._assert_modal(logged_in_admin, response.location, "Select from Google Sheets")

    def test_delete_tabs_opens_the_running_tab_deletion(
        self, logged_in_admin, assembly_with_gsheet, fake_store, task_runner
    ):
        """The blocking task here is a tab deletion, so the user lands in the manage-tabs modal."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = self._add_running(fake_store, assembly.id, SelectionTaskType.DELETE_OLD_TABS)

        response = logged_in_admin.post(f"/backoffice/project/{assembly.id}/manage-tabs/start-delete")

        assert task_runner.submitted == []
        assert response.status_code == 302
        assert response.location.endswith(f"/selection?current_manage_tabs={run_id}")
        self._assert_modal(logged_in_admin, response.location, "Delete old tabs")

    def test_list_tabs_still_runs_during_a_selection(
        self, logged_in_admin, assembly_with_gsheet, fake_store, task_runner
    ):
        """Listing is read-only, so it is dispatched as normal."""
        assembly, _gsheet = assembly_with_gsheet
        self._add_running(fake_store, assembly.id, SelectionTaskType.SELECT_GSHEET)

        response = logged_in_admin.post(f"/backoffice/project/{assembly.id}/manage-tabs/start-list")

        assert len(task_runner.submitted) == 1
        assert response.status_code == 302
        assert "current_manage_tabs=" in response.location

    def test_replacement_run_opens_the_running_replacement(
        self, logged_in_admin, assembly_with_gsheet, fake_store, task_runner
    ):
        """A Google Sheets replacement blocks on an earlier replacement and opens the replacement modal."""
        assembly, _gsheet = assembly_with_gsheet
        run_id = self._add_running(fake_store, assembly.id, SelectionTaskType.SELECT_REPLACEMENT_GSHEET)

        response = logged_in_admin.post(
            f"/backoffice/project/{assembly.id}/replacement/run", data={"number_to_select": "3"}
        )

        assert task_runner.submitted == []
        assert response.status_code == 302
        assert response.location.endswith(f"/selection?current_replacement={run_id}")
        self._assert_modal(logged_in_admin, response.location, "Select replacements from Google Sheets")
