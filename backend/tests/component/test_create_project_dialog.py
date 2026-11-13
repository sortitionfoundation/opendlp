# ABOUTME: Component tests for the three-step "Create new project" dialog, over a FakeUnitOfWork
# ABOUTME: Covers each step, Back, what is carried between steps, when the project comes to exist, and permissions

from io import BytesIO

from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import DataSource, RespondentsSource, TargetsSource
from tests.data import VALID_GSHEET_URL
from tests.fakes import FakeStore, FakeUnitOfWork

HTMX = {"HX-Request": "true"}
NEW = "/backoffice/project/new"
DETAILS = {"title": "A fresh project", "question": "What next?", "number_to_select": "30"}
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


def _projects(fake_store: FakeStore) -> list[Assembly]:
    with FakeUnitOfWork(store=fake_store) as uow:
        return [assembly.create_detached_copy() for assembly in uow.assemblies.all()]


def _step(client: FlaskClient, step: int, go: str = "next", **fields):
    return client.post(f"{NEW}/step", data={"step": str(step), "go": go, **DETAILS, **fields}, headers=HTMX)


class TestOpeningTheDialog:
    def test_the_dashboard_buttons_open_it_in_place(self, logged_in_admin: FlaskClient) -> None:
        html = logged_in_admin.get("/backoffice/dashboard").data.decode()

        assert f'hx-get="{NEW}"' in html
        assert 'hx-target="#project-dialog-host"' in html
        assert 'id="project-dialog-host"' in html
        assert "Create new project" not in html

    def test_htmx_gets_step_one_alone(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.get(NEW, headers=HTMX)

        assert response.status_code == 200
        html = response.data.decode()
        assert "<html" not in html
        assert "Create new project" in html
        assert 'name="title"' in html
        assert "Framing question (optional)" in html
        assert "Panel size (optional)" in html
        assert "First event date" not in html

    def test_the_address_is_the_dashboard_with_the_dialog_open(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Without JavaScript the button is a link, and this is where it goes."""
        response = logged_in_admin.get(NEW)

        assert response.status_code == 200
        html = response.data.decode()
        assert "<html" in html
        assert "Your projects" in html
        assert existing_assembly.title in html
        assert "Create new project" in html

    def test_the_stepper_names_three_steps_and_marks_the_first(self, logged_in_admin: FlaskClient) -> None:
        html = logged_in_admin.get(NEW, headers=HTMX).data.decode()

        assert "Project details" in html
        assert "Data location" in html
        assert "Targets and people" in html
        assert html.count('aria-current="step"') == 1

    def test_the_steps_are_not_links(self, logged_in_admin: FlaskClient) -> None:
        """Back and Next are the only way to move: the stepper shows progress."""
        html = logged_in_admin.get(NEW, headers=HTMX).data.decode()

        stepper_html = html.split('class="stepper"')[1].split("</ol>")[0]
        assert "<a " not in stepper_html

    def test_a_plain_user_cannot_open_it(self, logged_in_user: FlaskClient) -> None:
        assert logged_in_user.get(NEW, headers=HTMX).status_code == 403

    def test_it_needs_a_login(self, client: FlaskClient) -> None:
        response = client.get(NEW)

        assert response.status_code == 302
        assert "login" in response.location


class TestMovingBetweenSteps:
    def test_next_from_step_one_shows_the_location(self, logged_in_admin: FlaskClient) -> None:
        response = _step(logged_in_admin, 1)

        assert response.status_code == 200
        html = response.data.decode()
        assert "Where will you manage your data?" in html
        assert "In OpenDLP" in html
        assert "In Google Sheets" in html

    def test_in_opendlp_is_the_default_location(self, logged_in_admin: FlaskClient) -> None:
        html = " ".join(_step(logged_in_admin, 1).data.decode().split())

        assert '<option value="csv" selected' in html

    def test_step_one_values_ride_along_as_hidden_inputs(self, logged_in_admin: FlaskClient) -> None:
        """The wizard keeps no state on the server."""
        html = _step(logged_in_admin, 1).data.decode()

        assert 'type="hidden" name="title" value="A fresh project"' in html
        assert 'type="hidden" name="question" value="What next?"' in html
        assert 'type="hidden" name="number_to_select" value="30"' in html

    def test_a_missing_title_is_refused_at_step_one(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        response = logged_in_admin.post(f"{NEW}/step", data={"step": "1", "go": "next", "title": ""}, headers=HTMX)

        assert response.status_code == 422
        html = response.data.decode()
        assert "This field is required" in html
        assert "Where will you manage your data?" not in html
        assert _projects(fake_store) == []

    def test_a_short_title_is_refused_at_step_one(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(f"{NEW}/step", data={"step": "1", "go": "next", "title": "ab"}, headers=HTMX)

        assert response.status_code == 422
        assert 'value="ab"' in response.data.decode()

    def test_a_negative_panel_size_is_refused_at_step_one(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(
            f"{NEW}/step",
            data={"step": "1", "go": "next", "title": "Fine title", "number_to_select": "-3"},
            headers=HTMX,
        )

        assert response.status_code == 422

    def test_an_empty_panel_size_is_allowed(self, logged_in_admin: FlaskClient) -> None:
        response = logged_in_admin.post(
            f"{NEW}/step", data={"step": "1", "go": "next", "title": "Fine title", "number_to_select": ""}, headers=HTMX
        )

        assert response.status_code == 200

    def test_next_from_step_two_in_opendlp_shows_the_two_sources(self, logged_in_admin: FlaskClient) -> None:
        html = _step(logged_in_admin, 2, location="csv").data.decode()

        assert "Target data source" in html
        assert "Respondents data source" in html
        assert "Decide later" in html
        assert "Create inside OpenDLP" in html
        assert "Through OpenDLP registration" in html
        assert "Import from CSV" in html
        assert "Spreadsheet URL" not in html

    def test_next_from_step_two_in_google_sheets_shows_the_sheet_form(self, logged_in_admin: FlaskClient) -> None:
        html = _step(logged_in_admin, 2, location="gsheet").data.decode()

        assert "Spreadsheet URL" in html
        assert "Team Configuration" in html
        assert "Check Same Address" in html
        assert "Target data source" not in html

    def test_back_from_step_three_returns_to_the_location(self, logged_in_admin: FlaskClient) -> None:
        html = " ".join(_step(logged_in_admin, 3, go="back", location="gsheet").data.decode().split())

        assert "Where will you manage your data?" in html
        assert '<option value="gsheet" selected' in html

    def test_back_from_step_two_returns_to_the_details_as_typed(self, logged_in_admin: FlaskClient) -> None:
        html = _step(logged_in_admin, 2, go="back", location="gsheet").data.decode()

        assert 'value="A fresh project"' in html
        assert "What next?" in html
        assert 'type="hidden" name="location" value="gsheet"' in html

    def test_back_does_not_validate(self, logged_in_admin: FlaskClient) -> None:
        """Going back is never refused, whatever state the hidden values are in."""
        response = logged_in_admin.post(f"{NEW}/step", data={"step": "2", "go": "back", "title": ""}, headers=HTMX)

        assert response.status_code == 200

    def test_moving_between_steps_creates_nothing(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Cancel before the first write leaves nothing behind."""
        _step(logged_in_admin, 1)
        _step(logged_in_admin, 2, location="csv")
        _step(logged_in_admin, 3, go="back", location="csv")

        assert _projects(fake_store) == []

    def test_before_the_project_exists_the_dialog_closes_to_the_dashboard_with_cancel(
        self, logged_in_admin: FlaskClient
    ) -> None:
        html = _step(logged_in_admin, 2, location="csv").data.decode()

        assert 'href="/backoffice/dashboard"' in html
        assert "Cancel" in html
        assert "Back" in html

    def test_what_was_typed_is_remembered_as_unsaved(self, logged_in_admin: FlaskClient) -> None:
        """The dirty flag rides through each redraw, so leaving still asks."""
        html = " ".join(_step(logged_in_admin, 1, dirty="1").data.decode().split())

        assert 'name="dirty" value="1"' in html


class TestSavingWithoutAnUpload:
    def test_in_opendlp_with_the_defaults_creates_the_project(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        response = logged_in_admin.post(f"{NEW}/save", data={**DETAILS, "location": "csv"}, headers=HTMX)

        assert response.status_code == 200
        (project,) = _projects(fake_store)
        assert response.headers["HX-Redirect"].endswith(f"/backoffice/project/{project.id}")
        assert project.title == "A fresh project"
        assert project.question == "What next?"
        assert project.number_to_select == 30
        assert project.data_source == DataSource.OPENDLP
        assert project.targets_source == TargetsSource.UNDECIDED
        assert project.respondents_source == RespondentsSource.UNDECIDED

    def test_the_chosen_sources_are_stored(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        logged_in_admin.post(
            f"{NEW}/save",
            data={**DETAILS, "location": "csv", "targets_source": "manual", "respondents_source": "registration"},
            headers=HTMX,
        )

        (project,) = _projects(fake_store)
        assert project.targets_source == TargetsSource.MANUAL
        assert project.respondents_source == RespondentsSource.REGISTRATION

    def test_an_empty_panel_size_is_stored_as_zero(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        logged_in_admin.post(
            f"{NEW}/save", data={"title": "No size yet", "number_to_select": "", "location": "csv"}, headers=HTMX
        )

        (project,) = _projects(fake_store)
        assert project.number_to_select == 0

    def test_the_creation_is_flashed_for_the_page_it_lands_on(self, logged_in_admin: FlaskClient) -> None:
        logged_in_admin.post(f"{NEW}/save", data={**DETAILS, "location": "csv"}, headers=HTMX)

        with logged_in_admin.session_transaction() as session:
            messages = [message for _category, message in session.get("_flashes", [])]
        assert any("created successfully" in message for message in messages)

    def test_tampered_details_are_refused_at_save(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        """Hidden inputs are user input: step one is checked again when the project is made."""
        response = logged_in_admin.post(f"{NEW}/save", data={"title": "", "location": "csv"}, headers=HTMX)

        assert response.status_code == 422
        assert 'name="title"' in response.data.decode()
        assert _projects(fake_store) == []

    def test_google_sheets_creates_the_project_with_its_sheet(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        response = logged_in_admin.post(
            f"{NEW}/save", data={**DETAILS, "location": "gsheet", **GSHEET_FIELDS}, headers=HTMX
        )

        assert response.status_code == 200
        (project,) = _projects(fake_store)
        assert response.headers["HX-Redirect"].endswith(f"/backoffice/project/{project.id}?check=1")
        assert project.data_source == DataSource.GSHEET
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.assembly_gsheets.get_by_assembly_id(project.id).url == VALID_GSHEET_URL

    def test_a_refused_sheet_creates_nothing_and_stays_on_step_three(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        response = logged_in_admin.post(
            f"{NEW}/save",
            data={**DETAILS, "location": "gsheet", **GSHEET_FIELDS, "url": "https://example.com/nope"},
            headers=HTMX,
        )

        assert response.status_code == 422
        html = response.data.decode()
        assert "https://example.com/nope" in html
        assert 'type="hidden" name="title" value="A fresh project"' in html
        assert _projects(fake_store) == []

    def test_a_plain_user_cannot_save(self, logged_in_user: FlaskClient, fake_store: FakeStore) -> None:
        response = logged_in_user.post(f"{NEW}/save", data={**DETAILS, "location": "csv"}, headers=HTMX)

        assert response.status_code == 403
        assert _projects(fake_store) == []


class TestTheFirstUploadCreatesTheProject:
    def _upload_targets(self, client: FlaskClient, content: str = TARGETS_CSV, **fields):
        return client.post(
            f"{NEW}/upload-targets",
            data={**DETAILS, "location": "csv", "csv_file": (BytesIO(content.encode()), "targets.csv"), **fields},
            content_type="multipart/form-data",
            headers=HTMX,
        )

    def _upload_respondents(self, client: FlaskClient, content: str = RESPONDENTS_CSV, **fields):
        return client.post(
            f"{NEW}/upload-respondents",
            data={**DETAILS, "location": "csv", "file": (BytesIO(content.encode()), "people.csv"), **fields},
            content_type="multipart/form-data",
            headers=HTMX,
        )

    def test_uploading_targets_creates_the_project_with_them(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        response = self._upload_targets(logged_in_admin, respondents_source="registration")

        assert response.status_code == 200
        (project,) = _projects(fake_store)
        assert project.title == "A fresh project"
        assert project.targets_source == TargetsSource.CSV
        assert project.respondents_source == RespondentsSource.REGISTRATION
        assert "1 target uploaded" in response.data.decode()

    def test_after_the_upload_the_dialog_belongs_to_the_project(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """Still the create dialog, stepper and all, but every button now posts at the project."""
        html = self._upload_targets(logged_in_admin).data.decode()

        (project,) = _projects(fake_store)
        assert "Create new project" in html
        assert 'class="stepper"' in html
        assert f'hx-post="/backoffice/project/{project.id}/data-source/save"' in html
        assert 'name="dialog" value="create"' in html

    def test_after_the_upload_there_is_no_way_back_and_cancel_is_close(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """Step two is locked once something is written, and Cancel could not undo the creation."""
        html = self._upload_targets(logged_in_admin).data.decode()

        (project,) = _projects(fake_store)
        assert '"go": "back"' not in html
        assert "Cancel" not in html
        assert "Close" in html
        assert f'href="/backoffice/project/{project.id}"' in html

    def test_after_the_upload_nothing_is_unsaved(self, logged_in_admin: FlaskClient) -> None:
        html = " ".join(self._upload_targets(logged_in_admin, dirty="1").data.decode().split())

        assert 'name="dirty" value=""' in html
        assert "markDialogDirty" not in html

    def test_uploading_respondents_creates_the_project_with_them(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        response = self._upload_respondents(logged_in_admin, targets_source="manual")

        assert response.status_code == 200
        (project,) = _projects(fake_store)
        assert project.respondents_source == RespondentsSource.CSV
        assert project.targets_source == TargetsSource.MANUAL
        assert project.csv.last_import_filename == "people.csv"
        assert "3 respondents uploaded" in response.data.decode()

    def test_a_refused_targets_file_creates_nothing(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        response = self._upload_targets(logged_in_admin, content="not,a,targets,file\n1,2,3,4")

        assert response.status_code == 422
        html = response.data.decode()
        assert "CSV import failed" in html
        assert f'hx-post="{NEW}/save"' in html
        assert '"go": "back"' in html
        assert _projects(fake_store) == []

    def test_a_refused_respondents_file_creates_nothing(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        response = self._upload_respondents(logged_in_admin, id_column="no_such_column")

        assert response.status_code == 422
        assert "Invalid CSV format" in response.data.decode()
        assert _projects(fake_store) == []

    def test_no_file_creates_nothing(self, logged_in_admin: FlaskClient, fake_store: FakeStore) -> None:
        response = logged_in_admin.post(
            f"{NEW}/upload-targets",
            data={**DETAILS, "location": "csv"},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        assert response.status_code == 422
        assert "Please select a CSV file to upload" in response.data.decode()
        assert _projects(fake_store) == []

    def test_tampered_details_are_refused_before_the_file_is_read(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        response = logged_in_admin.post(
            f"{NEW}/upload-targets",
            data={"title": "", "location": "csv", "csv_file": (BytesIO(TARGETS_CSV.encode()), "targets.csv")},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        assert response.status_code == 422
        assert _projects(fake_store) == []

    def test_the_second_upload_goes_to_the_project_not_a_second_project(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        self._upload_targets(logged_in_admin)
        (project,) = _projects(fake_store)

        response = logged_in_admin.post(
            f"/backoffice/project/{project.id}/data-source/upload-respondents",
            data={"dialog": "create", "file": (BytesIO(RESPONDENTS_CSV.encode()), "people.csv")},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        html = response.data.decode()
        assert len(_projects(fake_store)) == 1
        assert "1 target uploaded" in html
        assert "3 respondents uploaded" in html
        assert "Create new project" in html

    def test_saving_after_an_upload_does_not_flash_twice(
        self, logged_in_admin: FlaskClient, fake_store: FakeStore
    ) -> None:
        """The creation was flashed when it happened; Save adds nothing to it."""
        self._upload_targets(logged_in_admin)
        (project,) = _projects(fake_store)

        logged_in_admin.post(
            f"/backoffice/project/{project.id}/data-source/save",
            data={"dialog": "create", "targets_source": "csv", "respondents_source": ""},
            headers=HTMX,
        )

        with logged_in_admin.session_transaction() as session:
            messages = [message for _category, message in session.get("_flashes", [])]
        assert len(messages) == 1
        assert "created successfully" in messages[0]

    def test_a_plain_user_cannot_upload(self, logged_in_user: FlaskClient, fake_store: FakeStore) -> None:
        assert self._upload_targets(logged_in_user).status_code == 403
        assert _projects(fake_store) == []
