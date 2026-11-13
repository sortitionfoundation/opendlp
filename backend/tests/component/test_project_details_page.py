# ABOUTME: Component tests for the project details page and the values edited in place on it, over a FakeUnitOfWork
# ABOUTME: Covers the Basic details card, each editable field's save and refusal, what a save sends out of band, and who may edit

from datetime import date

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.value_objects import AssemblyRole
from opendlp.service_layer.user_service import assign_assembly_role
from tests.fakes import FakeStore, FakeUnitOfWork

HTMX = {"HX-Request": "true"}


def _details(assembly: Assembly) -> str:
    return f"/backoffice/project/{assembly.id}"


def _save(client: FlaskClient, assembly: Assembly, field: str, value: str, htmx: bool = True, **extra):
    return client.post(
        f"{_details(assembly)}/edit-field",
        data={"field": field, field: value, **extra},
        headers=HTMX if htmx else {},
    )


def _stored(fake_store: FakeStore, assembly: Assembly) -> Assembly:
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.assemblies.get(assembly.id).create_detached_copy()


@pytest.fixture
def reader(fake_store: FakeStore, logged_in_user: FlaskClient, regular_user, existing_assembly: Assembly):
    """The regular user, signed in, with a read-only role on the project."""
    with FakeUnitOfWork(store=fake_store) as uow:
        assign_assembly_role(uow, regular_user.id, existing_assembly.id, AssemblyRole.READ_ONLY)
    return logged_in_user


class TestBasicDetailsCard:
    def test_the_card_shows_the_projects_values(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(_details(existing_assembly)).data.decode()

        assert "Basic details" in html
        assert "Existing Assembly" in html
        assert "What is the existing question?" in html
        assert "Active" in html
        assert "Panel size" in html
        assert "First event date" in html
        assert "Last Updated" in html

    def test_a_manager_gets_a_pencil_for_each_editable_value(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(_details(existing_assembly)).data.decode()

        for name in ("project title", "framing question", "panel size", "first event date"):
            assert f'aria-label="Edit {name}"' in html
        assert html.count('x-data="inlineEdit"') == 4
        assert f'hx-post="{_details(existing_assembly)}/edit-field"' in html

    def test_status_created_and_last_updated_have_no_pencil(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(_details(existing_assembly)).data.decode()

        assert 'aria-label="Edit status"' not in html
        assert 'aria-label="Edit created"' not in html

    def test_there_is_no_edit_project_button(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """The edit page is gone: every value is edited where it is shown."""
        assert "Edit project<" not in logged_in_admin.get(_details(existing_assembly)).data.decode()

    def test_an_empty_question_reads_not_set(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.assemblies.get(existing_assembly.id).question = ""

        assert "Not set" in logged_in_admin.get(_details(existing_assembly)).data.decode()

    def test_a_reader_sees_the_values_without_pencils(self, reader: FlaskClient, existing_assembly: Assembly) -> None:
        html = reader.get(_details(existing_assembly)).data.decode()

        assert "Existing Assembly" in html
        assert "What is the existing question?" in html
        assert 'x-data="inlineEdit"' not in html
        assert 'aria-label="Edit project title"' not in html

    def test_the_page_heading_can_be_swapped_by_id(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """A saved title updates the heading out of band, so the heading needs a name."""
        assert 'id="project-page-title"' in logged_in_admin.get(_details(existing_assembly)).data.decode()


class TestSavingAValue:
    def test_a_title_is_saved_and_the_row_comes_back_at_rest(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "title", "A better title")

        assert response.status_code == 200
        html = response.data.decode()
        assert 'id="project-title-row"' in html
        assert "A better title" in html
        assert "data-editing" not in html
        assert "<html" not in html
        assert _stored(fake_store, existing_assembly).title == "A better title"

    def test_a_saved_title_updates_the_heading_and_the_browser_title(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = _save(logged_in_admin, existing_assembly, "title", "A better title").data.decode()

        assert '<h1 id="project-page-title" hx-swap-oob="innerHTML">A better title</h1>' in html
        assert "<title>A better title - Project details</title>" in html

    def test_other_values_leave_the_heading_alone(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = _save(logged_in_admin, existing_assembly, "question", "A new question?").data.decode()

        assert "project-page-title" not in html
        assert "<title>" not in html

    def test_every_save_refreshes_last_updated_and_flashes(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = _save(logged_in_admin, existing_assembly, "question", "A new question?").data.decode()

        assert 'id="project-updated-row"' in html
        assert 'hx-swap-oob="true"' in html
        assert 'id="floating-alerts"' in html
        assert "Project details saved" in html

    def test_a_save_moves_last_updated(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        before = _stored(fake_store, existing_assembly).updated_at

        _save(logged_in_admin, existing_assembly, "question", "A new question?")

        assert _stored(fake_store, existing_assembly).updated_at > before

    def test_a_question_keeps_its_lines(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        _save(logged_in_admin, existing_assembly, "question", "First line\nSecond line")

        assert "Second line" in _stored(fake_store, existing_assembly).question

    def test_a_question_can_be_emptied(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "question", "")

        assert response.status_code == 200
        assert _stored(fake_store, existing_assembly).question == ""
        assert "Not set" in response.data.decode()

    def test_a_date_is_saved_and_read_back_in_words(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "first_assembly_date", "2031-04-01")

        assert response.status_code == 200
        assert _stored(fake_store, existing_assembly).first_assembly_date == date(2031, 4, 1)
        html = response.data.decode()
        assert "April" in html
        assert 'value="2031-04-01"' in html

    def test_a_date_can_be_cleared(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "first_assembly_date", "")

        assert response.status_code == 200
        assert _stored(fake_store, existing_assembly).first_assembly_date is None

    def test_a_save_from_inside_the_row_asks_for_focus_back(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = _save(logged_in_admin, existing_assembly, "title", "A better title", return_focus="1").data.decode()

        assert "autofocus" in html

    def test_without_htmx_a_save_goes_back_to_the_details_page(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "title", "A better title", htmx=False)

        assert response.status_code == 302
        assert response.location.endswith(_details(existing_assembly))
        assert _stored(fake_store, existing_assembly).title == "A better title"


class TestThePanelSize:
    def test_a_panel_size_is_saved(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "number_to_select", "40")

        assert response.status_code == 200
        assert _stored(fake_store, existing_assembly).number_to_select == 40
        assert "Panel size saved." in response.data.decode()

    def test_with_no_targets_to_move_the_flash_says_nothing_of_them(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = _save(logged_in_admin, existing_assembly, "number_to_select", "40").data.decode()

        assert "recalculated" not in html

    def test_zero_is_allowed(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "number_to_select", "0")

        assert response.status_code == 200
        assert _stored(fake_store, existing_assembly).number_to_select == 0

    @pytest.mark.parametrize("bad", ["-1", "lots", ""])
    def test_a_bad_panel_size_is_refused_in_place(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly, bad: str
    ) -> None:
        before = _stored(fake_store, existing_assembly).number_to_select

        response = _save(logged_in_admin, existing_assembly, "number_to_select", bad)

        assert response.status_code == 422
        assert "data-editing" in response.data.decode()
        assert _stored(fake_store, existing_assembly).number_to_select == before


class TestARefusedValue:
    def test_a_short_title_comes_back_open_with_the_reason(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "title", "ab")

        assert response.status_code == 422
        html = response.data.decode()
        assert 'id="project-title-row"' in html
        assert "data-editing" in html
        assert 'value="ab"' in html
        assert 'aria-invalid="true"' in html
        assert '<input type="hidden" value="Existing Assembly" x-ref="saved">' in html
        assert _stored(fake_store, existing_assembly).title == "Existing Assembly"

    def test_a_refusal_sends_nothing_out_of_band(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = _save(logged_in_admin, existing_assembly, "title", "").data.decode()

        assert "hx-swap-oob" not in html

    def test_an_overlong_question_is_refused(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        assert _save(logged_in_admin, existing_assembly, "question", "x" * 1001).status_code == 422

    def test_a_date_that_is_not_one_is_refused(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        assert _save(logged_in_admin, existing_assembly, "first_assembly_date", "next spring").status_code == 422

    def test_without_htmx_a_refusal_is_flashed_on_the_details_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(logged_in_admin, existing_assembly, "title", "ab", htmx=False)

        assert response.status_code == 302
        page = logged_in_admin.get(response.location).data.decode()
        assert "Field must be between 3 and 200 characters long" in page

    @pytest.mark.parametrize("field", ["status", "created_by_user_id", "id", "data_source", ""])
    def test_a_field_that_is_not_edited_here_is_refused(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly, field: str
    ) -> None:
        """Only the four values with a pencil can be set through this route."""
        response = _save(logged_in_admin, existing_assembly, field, "archived")

        assert response.status_code == 400
        assert _stored(fake_store, existing_assembly).status == existing_assembly.status


class TestWhoMayEdit:
    def test_a_reader_cannot_save(
        self, fake_store: FakeStore, reader: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = _save(reader, existing_assembly, "title", "Not allowed")

        assert response.status_code == 403
        assert _stored(fake_store, existing_assembly).title == "Existing Assembly"

    def test_someone_with_no_role_cannot_save(self, logged_in_user: FlaskClient, existing_assembly: Assembly) -> None:
        assert _save(logged_in_user, existing_assembly, "title", "Not allowed").status_code == 403

    def test_it_needs_a_login(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        response = _save(client, existing_assembly, "title", "Not allowed")

        assert response.status_code == 302
        assert "login" in response.location


class TestTheOldEditPage:
    def test_its_address_goes_to_the_details_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.get(f"{_details(existing_assembly)}/edit")

        assert response.status_code == 302
        assert response.location.endswith(_details(existing_assembly))

    def test_it_still_needs_a_login(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        response = client.get(f"{_details(existing_assembly)}/edit")

        assert response.status_code == 302
        assert "login" in response.location
