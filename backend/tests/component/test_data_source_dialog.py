# ABOUTME: Component tests for the data source settings dialog on an existing project, over a FakeUnitOfWork
# ABOUTME: Covers opening it, changing the location, CSV uploads and deletes, saving, the lock and permissions

from io import BytesIO

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import AssemblyRole, DataSource, RespondentsSource, TargetsSource
from opendlp.service_layer.assembly_service import add_assembly_gsheet
from opendlp.service_layer.user_service import assign_assembly_role
from tests.data import VALID_GSHEET_URL
from tests.fakes import FakeStore, FakeUnitOfWork

HTMX = {"HX-Request": "true"}
TARGETS_CSV = "feature,value,min,max\nRegion,North,5,10\nRegion,South,5,10"
RESPONDENTS_CSV = "ref,code,Region\n1,a,North\n2,b,South\n3,c,North"

GSHEET_FIELDS = {
    "url": VALID_GSHEET_URL,
    "select_registrants_tab": "Respondents",
    "select_targets_tab": "Categories",
    "replace_registrants_tab": "Remaining",
    "replace_targets_tab": "Replacement Categories",
    "already_selected_tab": "Selected",
    "check_same_address": "y",
    "generate_remaining_tab": "y",
    "team": "uk",
    "id_column": "nationbuilder_id",
}


def _base(assembly: Assembly) -> str:
    return f"/backoffice/project/{assembly.id}/data-source"


def _stored(fake_store: FakeStore, assembly: Assembly) -> Assembly:
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.assemblies.get(assembly.id).create_detached_copy()


def _stored_gsheet(fake_store: FakeStore, assembly: Assembly):
    """The fake store keeps sheets in their own repository rather than on the assembly."""
    with FakeUnitOfWork(store=fake_store) as uow:
        gsheet = uow.assembly_gsheets.get_by_assembly_id(assembly.id)
        return gsheet.create_detached_copy() if gsheet else None


def _upload_targets(client: FlaskClient, assembly: Assembly, content: str = TARGETS_CSV, **fields):
    return client.post(
        f"{_base(assembly)}/upload-targets",
        data={"csv_file": (BytesIO(content.encode()), "targets.csv"), **fields},
        content_type="multipart/form-data",
        headers=HTMX,
    )


def _upload_respondents(client: FlaskClient, assembly: Assembly, content: str = RESPONDENTS_CSV, **fields):
    return client.post(
        f"{_base(assembly)}/upload-respondents",
        data={"file": (BytesIO(content.encode()), "people.csv"), **fields},
        content_type="multipart/form-data",
        headers=HTMX,
    )


@pytest.fixture
def assembly_with_gsheet(fake_store: FakeStore, admin_user, existing_assembly: Assembly) -> Assembly:
    with FakeUnitOfWork(store=fake_store) as uow:
        add_assembly_gsheet(uow=uow, assembly_id=existing_assembly.id, user_id=admin_user.id, url=VALID_GSHEET_URL)
    return existing_assembly


class TestOpeningTheDialog:
    def test_htmx_gets_the_dialog_alone(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """The details page swaps this into its dialog host, so it must not be a whole page."""
        response = logged_in_admin.get(_base(existing_assembly), headers=HTMX)

        assert response.status_code == 200
        html = response.data.decode()
        assert "Data source settings" in html
        assert "<html" not in html
        assert 'role="dialog"' in html

    def test_without_htmx_it_opens_over_the_details_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """The address is a link too: it lands on the page with the dialog open."""
        response = logged_in_admin.get(_base(existing_assembly))

        assert response.status_code == 302
        assert response.location.endswith(f"/backoffice/project/{existing_assembly.id}?data_source=1")
        page = logged_in_admin.get(response.location)
        assert 'aria-labelledby="project-dialog-title"' in page.data.decode()

    def test_the_details_page_has_no_dialog_unless_asked(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(f"/backoffice/project/{existing_assembly.id}").data.decode()

        assert 'id="project-dialog-host"' in html
        assert 'role="dialog"' not in html

    def test_a_new_project_is_held_in_opendlp_and_undecided(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """The defaults: In OpenDLP, and "Decide later" for both kinds of data."""
        html = logged_in_admin.get(_base(existing_assembly), headers=HTMX).data.decode()

        assert '<option value="csv"\n                        selected' in html or 'value="csv" selected' in " ".join(
            html.split()
        )
        assert "Decide later" in html
        assert "Target data source" in html
        assert "Respondents data source" in html

    def test_it_has_no_stepper(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """The stepper belongs to creating a project; this one already exists."""
        html = logged_in_admin.get(_base(existing_assembly), headers=HTMX).data.decode()

        assert 'class="stepper"' not in html
        assert "Create new project" not in html

    def test_someone_who_cannot_manage_the_project_is_refused(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_user.get(_base(existing_assembly), headers=HTMX)

        assert response.status_code == 403

    def test_a_read_only_member_does_not_get_the_dialog_on_the_details_page(
        self, fake_store: FakeStore, logged_in_user: FlaskClient, regular_user, existing_assembly: Assembly
    ) -> None:
        """?data_source=1 opens nothing for someone who could not save it."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assign_assembly_role(uow, regular_user.id, existing_assembly.id, AssemblyRole.READ_ONLY)

        response = logged_in_user.get(f"/backoffice/project/{existing_assembly.id}?data_source=1")

        assert response.status_code == 200
        assert 'role="dialog"' not in response.data.decode()


class TestChoosingTheLocation:
    def test_choosing_google_sheets_redraws_with_the_sheet_fields(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/refresh", data={"location": "gsheet"}, headers=HTMX
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert "Spreadsheet URL" in html
        assert "Target data source" not in html

    def test_redrawing_writes_nothing(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        logged_in_admin.post(f"{_base(existing_assembly)}/refresh", data={"location": "gsheet"}, headers=HTMX)

        assert _stored(fake_store, existing_assembly).data_source == DataSource.UNDECIDED

    def test_the_location_is_fixed_once_there_is_a_sheet(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: Assembly
    ) -> None:
        """Asking for OpenDLP on a project with a sheet still shows the sheet, with the choice disabled."""
        response = logged_in_admin.post(
            f"{_base(assembly_with_gsheet)}/refresh", data={"location": "csv"}, headers=HTMX
        )

        html = response.data.decode()
        assert "Spreadsheet URL" in html
        assert "disabled" in html
        assert "Remove Google Sheets settings" in html

    def test_the_location_is_fixed_once_there_are_targets(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _upload_targets(logged_in_admin, existing_assembly)

        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/refresh", data={"location": "gsheet"}, headers=HTMX
        )

        html = response.data.decode()
        assert "Spreadsheet URL" not in html
        assert "Target data source" in html


class TestUploadingTargets:
    def test_an_upload_shows_the_count_and_stays_in_the_dialog(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _upload_targets(logged_in_admin, existing_assembly)

        assert response.status_code == 200
        html = response.data.decode()
        assert "1 target uploaded" in html
        assert "Delete targets" in html
        assert "<html" not in html

    def test_an_upload_records_import_from_csv_without_save(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Closing the dialog after an upload must not leave "Decide later" beside uploaded targets."""
        _upload_targets(logged_in_admin, existing_assembly)

        stored = _stored(fake_store, existing_assembly)
        assert stored.data_source == DataSource.OPENDLP
        assert stored.targets_source == TargetsSource.CSV
        assert stored.respondents_source == RespondentsSource.UNDECIDED

    def test_the_other_dropdown_keeps_what_was_chosen(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """An unsaved choice for respondents survives the redraw an upload of targets causes."""
        response = _upload_targets(logged_in_admin, existing_assembly, respondents_source="registration")

        assert "respondentsSource: 'registration'" in response.data.decode()

    def test_no_file_is_refused_in_place(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/upload-targets",
            data={"targets_source": "csv"},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        assert response.status_code == 422
        html = response.data.decode()
        assert "Please select a CSV file to upload" in html
        assert "There is a problem" in html

    def test_a_bad_file_is_refused_in_place_and_nothing_is_stored(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _upload_targets(logged_in_admin, existing_assembly, content="not,a,targets,file\n1,2,3,4")

        assert response.status_code == 422
        assert "CSV import failed" in response.data.decode()
        assert _stored(fake_store, existing_assembly).targets_source == TargetsSource.UNDECIDED

    def test_a_csv_cannot_go_into_a_google_sheets_project(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: Assembly
    ) -> None:
        """Only the interface used to stop this; the route does now."""
        response = _upload_targets(logged_in_admin, assembly_with_gsheet)

        assert response.status_code == 422
        assert "managed in Google Sheets" in response.data.decode()

    def test_someone_who_cannot_manage_the_project_is_refused(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        assert _upload_targets(logged_in_user, existing_assembly).status_code == 403


class TestUploadingRespondents:
    def test_an_upload_shows_the_count_and_records_the_choice(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _upload_respondents(logged_in_admin, existing_assembly)

        assert response.status_code == 200
        assert "3 respondents uploaded" in response.data.decode()
        stored = _stored(fake_store, existing_assembly)
        assert stored.respondents_source == RespondentsSource.CSV
        assert stored.csv.last_import_filename == "people.csv"
        assert stored.csv.csv_id_column == "ref"

    def test_the_id_column_named_is_used(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _upload_respondents(logged_in_admin, existing_assembly, id_column="code")

        assert _stored(fake_store, existing_assembly).csv.csv_id_column == "code"

    def test_no_file_is_refused_in_place(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/upload-respondents",
            data={"respondents_source": "csv"},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        assert response.status_code == 422
        assert "Please select a CSV file to upload" in response.data.decode()

    def test_a_file_that_is_not_utf8_is_refused_in_place(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/upload-respondents",
            data={"file": (BytesIO(b"ref,code\n1,\xff\xfe"), "people.csv")},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        assert response.status_code == 422
        assert "UTF-8" in response.data.decode()

    def test_an_unknown_id_column_is_refused_in_place(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _upload_respondents(logged_in_admin, existing_assembly, id_column="no_such_column")

        assert response.status_code == 422
        assert "Invalid CSV format" in response.data.decode()
        assert _stored(fake_store, existing_assembly).respondents_source == RespondentsSource.UNDECIDED

    def test_a_second_file_with_other_columns_goes_to_the_confirmation_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """The dialog cannot hold the column comparison, so htmx is told to load its page."""
        _upload_respondents(logged_in_admin, existing_assembly)

        response = _upload_respondents(logged_in_admin, existing_assembly, content="ref,code,Age\n1,a,40")

        assert response.status_code == 200
        assert response.headers["HX-Redirect"].endswith("/data/upload-respondents/confirm-diff")


class TestDeletingFromTheDialog:
    def test_the_dialog_names_the_delete_forms(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """Deleting is a form of its own outside the dialog's form, which the button names."""
        html = _upload_targets(logged_in_admin, existing_assembly).data.decode()

        assert 'form="project-delete-targets"' in html
        assert 'id="project-delete-targets"' in html
        assert f'action="/backoffice/project/{existing_assembly.id}/data/delete-targets"' in html

    def test_there_is_no_delete_form_for_what_is_not_there(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(_base(existing_assembly), headers=HTMX).data.decode()

        assert "delete-targets" not in html
        assert "delete-respondents" not in html
        assert "gsheet/delete" not in html

    def test_deleting_targets_comes_back_to_the_dialog(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _upload_targets(logged_in_admin, existing_assembly)

        response = logged_in_admin.post(f"/backoffice/project/{existing_assembly.id}/data/delete-targets", data={})

        assert response.status_code == 302
        assert response.location.endswith(f"/backoffice/project/{existing_assembly.id}?data_source=1")

    def test_deleting_respondents_comes_back_to_the_dialog(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _upload_respondents(logged_in_admin, existing_assembly)

        response = logged_in_admin.post(f"/backoffice/project/{existing_assembly.id}/data/delete-respondents", data={})

        assert response.status_code == 302
        assert response.location.endswith(f"/backoffice/project/{existing_assembly.id}?data_source=1")

    def test_removing_the_sheet_comes_back_to_the_dialog_unlocked(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: Assembly
    ) -> None:
        response = logged_in_admin.post(
            f"/backoffice/project/{assembly_with_gsheet.id}/gsheet/delete",
            data={},
            follow_redirects=True,
        )

        html = response.data.decode()
        assert 'aria-labelledby="project-dialog-title"' in html
        assert "Remove Google Sheets settings" not in html

    def test_deleting_everything_unlocks_the_location(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _upload_targets(logged_in_admin, existing_assembly)
        logged_in_admin.post(f"/backoffice/project/{existing_assembly.id}/data/delete-targets", data={})

        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/refresh", data={"location": "gsheet"}, headers=HTMX
        )

        assert "Spreadsheet URL" in response.data.decode()


class TestSaving:
    def test_saving_the_choices_stores_them_and_goes_to_the_details_page(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/save",
            data={"location": "csv", "targets_source": "manual", "respondents_source": "registration"},
            headers=HTMX,
        )

        assert response.status_code == 200
        assert response.headers["HX-Redirect"].endswith(f"/backoffice/project/{existing_assembly.id}")
        stored = _stored(fake_store, existing_assembly)
        assert stored.data_source == DataSource.OPENDLP
        assert stored.targets_source == TargetsSource.MANUAL
        assert stored.respondents_source == RespondentsSource.REGISTRATION

    def test_saving_choices_locks_nothing(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """A stored choice is a statement of intent: with no data the location can still change."""
        logged_in_admin.post(
            f"{_base(existing_assembly)}/save",
            data={"location": "csv", "targets_source": "manual", "respondents_source": "registration"},
            headers=HTMX,
        )

        html = logged_in_admin.post(
            f"{_base(existing_assembly)}/refresh", data={"location": "gsheet"}, headers=HTMX
        ).data.decode()

        assert "Spreadsheet URL" in html

    def test_an_unrecognised_choice_keeps_the_stored_one(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        logged_in_admin.post(
            f"{_base(existing_assembly)}/save",
            data={"location": "csv", "targets_source": "telepathy", "respondents_source": "csv"},
            headers=HTMX,
        )

        stored = _stored(fake_store, existing_assembly)
        assert stored.targets_source == TargetsSource.UNDECIDED
        assert stored.respondents_source == RespondentsSource.CSV

    def test_saving_a_sheet_stores_it_and_asks_for_an_access_check(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/save", data={"location": "gsheet", **GSHEET_FIELDS}, headers=HTMX
        )

        assert response.status_code == 200
        assert response.headers["HX-Redirect"].endswith(f"/backoffice/project/{existing_assembly.id}?check=1")
        stored = _stored(fake_store, existing_assembly)
        assert stored.data_source == DataSource.GSHEET
        assert _stored_gsheet(fake_store, existing_assembly).url == VALID_GSHEET_URL

    def test_a_sheet_with_a_bad_url_is_refused_in_place(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.post(
            f"{_base(existing_assembly)}/save",
            data={"location": "gsheet", **GSHEET_FIELDS, "url": "https://example.com/not-a-sheet"},
            headers=HTMX,
        )

        assert response.status_code == 422
        html = response.data.decode()
        assert "https://example.com/not-a-sheet" in html
        assert _stored_gsheet(fake_store, existing_assembly) is None

    def test_saving_again_updates_the_sheet(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, assembly_with_gsheet: Assembly
    ) -> None:
        logged_in_admin.post(
            f"{_base(assembly_with_gsheet)}/save",
            data={"location": "gsheet", **GSHEET_FIELDS, "select_registrants_tab": "People"},
            headers=HTMX,
        )

        assert _stored_gsheet(fake_store, assembly_with_gsheet).select_registrants_tab == "People"

    def test_a_locked_location_cannot_be_changed_by_posting_another(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, assembly_with_gsheet: Assembly
    ) -> None:
        """The disabled dropdown is not the protection: the route decides from the data."""
        response = logged_in_admin.post(
            f"{_base(assembly_with_gsheet)}/save",
            data={"location": "csv", "targets_source": "csv"},
            headers=HTMX,
        )

        assert response.status_code == 422
        assert _stored(fake_store, assembly_with_gsheet).targets_source == TargetsSource.UNDECIDED

    def test_someone_who_cannot_manage_the_project_is_refused(
        self, logged_in_user: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_user.post(f"{_base(existing_assembly)}/save", data={"location": "csv"}, headers=HTMX)

        assert response.status_code == 403
