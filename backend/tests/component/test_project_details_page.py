# ABOUTME: Component tests for the project details page and the values edited in place on it, over a FakeUnitOfWork
# ABOUTME: Covers the Basic details card, each editable field's save and refusal, what a save sends out of band, and who may edit

from datetime import date
from io import BytesIO

import pytest
from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.value_objects import AssemblyRole
from opendlp.service_layer.assembly_service import add_assembly_gsheet, create_assembly
from opendlp.service_layer.user_service import assign_assembly_role
from tests.data import VALID_GSHEET_URL
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


class TestDataSourceCard:
    @pytest.fixture
    def assembly_with_gsheet(self, fake_store: FakeStore, admin_user, existing_assembly: Assembly) -> Assembly:
        with FakeUnitOfWork(store=fake_store) as uow:
            add_assembly_gsheet(uow=uow, assembly_id=existing_assembly.id, user_id=admin_user.id, url=VALID_GSHEET_URL)
        return existing_assembly

    def test_a_new_project_is_in_opendlp_and_undecided(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(_details(existing_assembly)).data.decode()

        assert "Data source" in html
        assert "Data location" in html
        assert "In OpenDLP" in html
        assert "Target data source" in html
        assert "Respondents data source" in html
        assert html.count("Decide later") == 2

    def test_a_manager_gets_the_cog_that_opens_the_settings_dialog(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(_details(existing_assembly)).data.decode()

        assert 'aria-label="Data source settings"' in html
        assert f'hx-get="{_details(existing_assembly)}/data-source"' in html
        assert 'hx-target="#project-dialog-host"' in html
        assert 'aria-haspopup="dialog"' in html
        assert 'data-focus-id="data-source-settings"' in html

    def test_a_reader_sees_the_card_without_the_cog(self, reader: FlaskClient, existing_assembly: Assembly) -> None:
        html = reader.get(_details(existing_assembly)).data.decode()

        assert "Data location" in html
        assert 'aria-label="Data source settings"' not in html

    def test_uploaded_targets_are_counted_beside_their_source(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        logged_in_admin.post(
            f"{_details(existing_assembly)}/data-source/upload-targets",
            data={"csv_file": (BytesIO(b"feature,value,min,max\nRegion,North,5,10\nRegion,South,5,10"), "t.csv")},
            content_type="multipart/form-data",
            headers=HTMX,
        )

        html = logged_in_admin.get(_details(existing_assembly)).data.decode()

        assert "Import from CSV" in html
        assert "1 target uploaded" in html

    def test_a_google_sheets_project_shows_its_url_and_no_source_rows(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: Assembly
    ) -> None:
        html = logged_in_admin.get(_details(assembly_with_gsheet)).data.decode()

        assert "In Google Sheets" in html
        assert "Spreadsheet URL" in html
        assert f'href="{VALID_GSHEET_URL}"' in html
        assert "Target data source" not in html

    def test_a_google_sheets_project_offers_an_access_check(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: Assembly
    ) -> None:
        html = logged_in_admin.get(_details(assembly_with_gsheet)).data.decode()

        assert 'id="gsheet-access-status"' in html
        assert f'hx-post="{_details(assembly_with_gsheet)}/gsheet/check"' in html
        assert 'hx-trigger="load"' not in html

    def test_after_a_save_the_access_check_runs_on_load(
        self, logged_in_admin: FlaskClient, assembly_with_gsheet: Assembly
    ) -> None:
        """Saving the sheet's settings lands here with ?check=1."""
        html = logged_in_admin.get(f"{_details(assembly_with_gsheet)}?check=1").data.decode()

        assert 'hx-trigger="load"' in html

    def test_a_reader_cannot_set_off_the_access_check(
        self, fake_store: FakeStore, reader: FlaskClient, admin_user, existing_assembly: Assembly
    ) -> None:
        with FakeUnitOfWork(store=fake_store) as uow:
            add_assembly_gsheet(uow=uow, assembly_id=existing_assembly.id, user_id=admin_user.id, url=VALID_GSHEET_URL)

        html = reader.get(f"{_details(existing_assembly)}?check=1").data.decode()

        assert 'hx-trigger="load"' not in html
        assert "/gsheet/check" not in html

    def test_an_opendlp_project_has_no_access_check(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        assert 'id="gsheet-access-status"' not in logged_in_admin.get(_details(existing_assembly)).data.decode()


class TestRegistrationLinkCard:
    def _seed_page(
        self,
        fake_store: FakeStore,
        assembly: Assembly,
        *,
        name: str,
        url_slug: str,
        short_url_slug: str = "",
        status=None,
    ) -> RegistrationPage:
        page = RegistrationPage(assembly_id=assembly.id, name=name, url_slug=url_slug, short_url_slug=short_url_slug)
        if status is not None:
            page.status = status
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.registration_pages.add(page)
            uow.commit()
        return page

    @staticmethod
    def _card(html: str) -> str:
        """The card's own markup: from its id to the next card, or to the dialog host that ends the page."""
        start = html.index('id="registration-link"')
        ends = [html.find(marker, start) for marker in ('id="team"', 'id="project-dialog-host"')]
        return html[start : min(end for end in ends if end != -1)]

    def test_with_no_page_the_card_is_empty_and_offers_to_create_one(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        card = self._card(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "Registration link" in card
        assert "Create" in card
        assert "<dl>" not in card
        assert f'href="{_details(existing_assembly)}/registration"' in card

    def test_with_one_page_it_shows_its_links_and_see_details(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        self._seed_page(fake_store, existing_assembly, name="English", url_slug="details-en", short_url_slug="111111")

        card = self._card(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "See details" in card
        assert "/register/details-en" in card
        assert "/r/111111" in card
        assert "URL link" in card
        assert "Short URL link" in card
        assert "QR code" in card
        assert f"{_details(existing_assembly)}/registration/details-en/qr-code.png" in card

    def test_with_several_pages_it_shows_one_and_counts_them_all(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        self._seed_page(fake_store, existing_assembly, name="English", url_slug="details-en", short_url_slug="111111")
        self._seed_page(fake_store, existing_assembly, name="Spanish", url_slug="details-es")
        self._seed_page(fake_store, existing_assembly, name="Welsh", url_slug="details-cy")

        card = self._card(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "See all (3)" in card
        assert "/register/details-en" in card
        assert "details-es" not in card
        assert "details-cy" not in card

    def test_a_page_with_no_short_url_has_no_short_link_or_qr_code(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """The QR code encodes the short URL, so without one there is nothing to download."""
        self._seed_page(fake_store, existing_assembly, name="Spanish", url_slug="details-es")

        card = self._card(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "/register/details-es" in card
        assert "Short URL link" not in card
        assert "QR code" not in card

    def test_the_published_page_is_shown_ahead_of_an_older_closed_one(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        self._seed_page(
            fake_store, existing_assembly, name="Last year", url_slug="old-closed", status=RegistrationPageStatus.CLOSED
        )
        self._seed_page(
            fake_store,
            existing_assembly,
            name="This year",
            url_slug="live-now",
            status=RegistrationPageStatus.PUBLISHED,
        )

        card = self._card(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "/register/live-now" in card
        assert "old-closed" not in card
        assert "See all (2)" in card

    def test_the_card_has_no_form_to_create_a_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Creating a page happens on the Registration tab, which the card's link goes to."""
        assert "registration/create" not in logged_in_admin.get(_details(existing_assembly)).data.decode()


class TestTeamCard:
    @pytest.fixture
    def manager(self, fake_store: FakeStore, logged_in_user: FlaskClient, regular_user, existing_assembly: Assembly):
        """The regular user, signed in, managing the project alongside its creator."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assign_assembly_role(uow, regular_user.id, existing_assembly.id, AssemblyRole.ASSEMBLY_MANAGER)
        return logged_in_user

    @staticmethod
    def _card(html: str) -> str:
        start = html.index('<div id="team"')
        return html[start : html.index('id="project-dialog-host"', start)]

    def test_the_card_lists_the_team_with_short_role_names(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user
    ) -> None:
        card = self._card(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "Team" in card
        assert admin_user.email in card
        assert "Project manager" in card
        assert "assembly-manager" not in card

    def test_a_manager_gets_the_add_button_a_bin_and_a_pencil(
        self, manager: FlaskClient, existing_assembly: Assembly, admin_user
    ) -> None:
        card = self._card(manager.get(_details(existing_assembly)).data.decode())

        assert "Add a team member" in card
        assert f'hx-get="{_details(existing_assembly)}/team/add"' in card
        assert f'action="{_details(existing_assembly)}/members/{admin_user.id}/remove"' in card
        assert f'hx-get="{_details(existing_assembly)}/team/{admin_user.id}/role"' in card
        assert 'aria-label="Remove Test Admin from the team"' in card
        assert 'aria-label="Change the role of Test Admin"' in card

    def test_a_reader_sees_the_table_alone(self, reader: FlaskClient, existing_assembly: Assembly, admin_user) -> None:
        card = self._card(reader.get(_details(existing_assembly)).data.decode())

        assert admin_user.email in card
        assert "Add a team member" not in card
        assert "/remove" not in card
        assert "/role" not in card

    def test_a_non_admin_is_not_offered_what_would_orphan_the_project(
        self, fake_store: FakeStore, logged_in_organiser: FlaskClient, organiser_user
    ) -> None:
        """The only manager's row has no bin and no pencil for someone who could not undo it."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = create_assembly(uow=uow, title="Organiser's own", created_by_user_id=organiser_user.id)
            assembly = assembly.create_detached_copy()

        card = self._card(logged_in_organiser.get(_details(assembly)).data.decode())

        assert "Last manager" in card
        assert f"/members/{organiser_user.id}/remove" not in card
        assert f"/team/{organiser_user.id}/role" not in card

    def test_an_admin_is_offered_them_even_for_the_only_manager(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user
    ) -> None:
        card = self._card(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "Last manager" not in card
        assert f"/members/{admin_user.id}/remove" in card


class TestAddingATeamMember:
    def _add(self, client: FlaskClient, assembly: Assembly, user_id, role: str = "READ_ONLY", again: bool = False):
        query = "?again=1" if again else ""
        return client.post(
            f"{_details(assembly)}/team/add{query}", data={"user_id": str(user_id), "role": role}, headers=HTMX
        )

    def test_the_dialog_opens_over_htmx(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        response = logged_in_admin.get(f"{_details(existing_assembly)}/team/add", headers=HTMX)

        assert response.status_code == 200
        html = response.data.decode()
        assert "<html" not in html
        assert "Add a team member" in html
        assert f"{_details(existing_assembly)}/members/search" in html
        assert "Add and add another" in html

    def test_the_roles_are_a_dropdown_that_still_explains_each_role(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        html = logged_in_admin.get(f"{_details(existing_assembly)}/team/add", headers=HTMX).data.decode()

        assert "<select" in html
        assert "Can view the project but cannot make changes" in html

    def test_without_htmx_its_address_goes_to_the_details_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.get(f"{_details(existing_assembly)}/team/add")

        assert response.status_code == 302
        assert response.location.endswith(f"{_details(existing_assembly)}#team")

    def test_add_closes_the_dialog_and_refreshes_the_card(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly, regular_user
    ) -> None:
        response = self._add(logged_in_admin, existing_assembly, regular_user.id)

        assert response.status_code == 200
        html = response.data.decode()
        assert 'role="dialog"' not in html
        assert '<div id="team" hx-swap-oob="true">' in html
        assert regular_user.email in html
        assert "Read only" in html
        assert "added to project with role Read only" in html
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(regular_user.id).get_assembly_role(existing_assembly.id) == AssemblyRole.READ_ONLY

    def test_add_and_add_another_keeps_the_dialog_open_and_empty(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly, regular_user
    ) -> None:
        response = self._add(logged_in_admin, existing_assembly, regular_user.id, again=True)

        assert response.status_code == 200
        html = response.data.decode()
        assert 'role="dialog"' in html
        assert "Test User has been added" in html
        assert f'value="{regular_user.id}"' not in html
        assert '<div id="team" hx-swap-oob="true">' in html
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(regular_user.id).get_assembly_role(existing_assembly.id) == AssemblyRole.READ_ONLY

    def test_no_user_chosen_is_refused_in_the_dialog(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        response = logged_in_admin.post(
            f"{_details(existing_assembly)}/team/add", data={"user_id": "", "role": "READ_ONLY"}, headers=HTMX
        )

        assert response.status_code == 422
        html = response.data.decode()
        assert 'role="dialog"' in html
        assert "This field is required" in html

    @pytest.mark.parametrize("user_id", ["not-a-uuid", "00000000-0000-0000-0000-000000000000"])
    def test_a_user_that_does_not_exist_is_refused_in_the_dialog(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, user_id: str
    ) -> None:
        response = self._add(logged_in_admin, existing_assembly, user_id)

        assert response.status_code == 422
        assert "Choose a user from the list" in response.data.decode()

    def test_a_role_that_does_not_exist_is_refused(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, regular_user
    ) -> None:
        assert self._add(logged_in_admin, existing_assembly, regular_user.id, role="EMPEROR").status_code == 422

    def test_a_reader_cannot_add_anyone(
        self, fake_store: FakeStore, reader: FlaskClient, existing_assembly: Assembly, organiser_user
    ) -> None:
        response = self._add(reader, existing_assembly, organiser_user.id)

        assert response.status_code == 403
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(organiser_user.id).get_assembly_role(existing_assembly.id) is None

    def test_without_htmx_an_add_goes_back_to_the_card(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, regular_user
    ) -> None:
        response = logged_in_admin.post(
            f"{_details(existing_assembly)}/team/add", data={"user_id": str(regular_user.id), "role": "READ_ONLY"}
        )

        assert response.status_code == 302
        assert response.location.endswith(f"{_details(existing_assembly)}#team")


class TestChangingARole:
    @pytest.fixture
    def member(self, fake_store: FakeStore, regular_user, existing_assembly: Assembly):
        with FakeUnitOfWork(store=fake_store) as uow:
            assign_assembly_role(uow, regular_user.id, existing_assembly.id, AssemblyRole.READ_ONLY)
        return regular_user

    def _url(self, assembly: Assembly, user) -> str:
        return f"{_details(assembly)}/team/{user.id}/role"

    def test_the_dialog_says_who_and_starts_on_their_role(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, member
    ) -> None:
        html = " ".join(logged_in_admin.get(self._url(existing_assembly, member), headers=HTMX).data.decode().split())

        assert "Change role" in html
        assert "Test User" in html
        assert member.email in html
        assert '<option value="READ_ONLY" selected' in html

    def test_a_change_closes_the_dialog_and_refreshes_the_card(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly, member
    ) -> None:
        response = logged_in_admin.post(
            self._url(existing_assembly, member), data={"role": "CONFIRMATION_CALLER"}, headers=HTMX
        )

        assert response.status_code == 200
        html = response.data.decode()
        assert 'role="dialog"' not in html
        assert '<div id="team" hx-swap-oob="true">' in html
        assert "Test User is now Confirmation caller" in html
        with FakeUnitOfWork(store=fake_store) as uow:
            role = uow.users.get(member.id).get_assembly_role(existing_assembly.id)
        assert role == AssemblyRole.CONFIRMATION_CALLER

    def test_someone_with_no_role_cannot_be_given_one_this_way(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly, organiser_user
    ) -> None:
        """Changing a role never adds anyone: that is what Add a team member is for, with its email."""
        response = logged_in_admin.post(
            self._url(existing_assembly, organiser_user), data={"role": "READ_ONLY"}, headers=HTMX
        )

        assert response.status_code == 404
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.users.get(organiser_user.id).get_assembly_role(existing_assembly.id) is None

    def test_a_non_admin_cannot_demote_the_only_manager(
        self, fake_store: FakeStore, logged_in_organiser: FlaskClient, organiser_user
    ) -> None:
        """The pencil is hidden for this row; the route refuses all the same."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = create_assembly(uow=uow, title="Organiser's own", created_by_user_id=organiser_user.id)
            assembly = assembly.create_detached_copy()

        response = logged_in_organiser.post(
            self._url(assembly, organiser_user), data={"role": "READ_ONLY"}, headers=HTMX
        )

        assert response.status_code == 422
        assert "must keep at least one Project Manager" in response.data.decode()
        with FakeUnitOfWork(store=fake_store) as uow:
            role = uow.users.get(organiser_user.id).get_assembly_role(assembly.id)
        assert role == AssemblyRole.ASSEMBLY_MANAGER

    def test_a_reader_cannot_change_a_role(self, reader: FlaskClient, existing_assembly: Assembly, admin_user) -> None:
        response = reader.post(self._url(existing_assembly, admin_user), data={"role": "READ_ONLY"}, headers=HTMX)

        assert response.status_code == 403


class TestRemovingATeamMember:
    def test_a_removal_comes_back_to_the_team_card(
        self, fake_store: FakeStore, logged_in_admin: FlaskClient, existing_assembly: Assembly, regular_user
    ) -> None:
        with FakeUnitOfWork(store=fake_store) as uow:
            assign_assembly_role(uow, regular_user.id, existing_assembly.id, AssemblyRole.READ_ONLY)

        response = logged_in_admin.post(f"{_details(existing_assembly)}/members/{regular_user.id}/remove")

        assert response.status_code == 302
        assert response.location.endswith(f"{_details(existing_assembly)}#team")

    def test_someone_who_removes_themselves_goes_to_their_projects(
        self, fake_store: FakeStore, logged_in_user: FlaskClient, regular_user, existing_assembly: Assembly
    ) -> None:
        """They can no longer open the project, so sending them back to it would only bounce them."""
        with FakeUnitOfWork(store=fake_store) as uow:
            assign_assembly_role(uow, regular_user.id, existing_assembly.id, AssemblyRole.ASSEMBLY_MANAGER)

        response = logged_in_user.post(f"{_details(existing_assembly)}/members/{regular_user.id}/remove")

        assert response.status_code == 302
        assert response.location.endswith("/backoffice/dashboard")


class TestProjectTabs:
    @staticmethod
    def _tab_bar(html: str) -> str:
        start = html.index('aria-label="Project sections"')
        return html[start : html.index("</nav>", start)]

    def test_data_source_and_team_members_are_not_tabs(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """They are cards on the Project Details tab."""
        tabs = self._tab_bar(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert "Project Details" in tabs
        assert "Targets" in tabs
        assert "Data Source" not in tabs
        assert "Team Members" not in tabs
        assert f"{_details(existing_assembly)}/data" not in tabs
        assert f"{_details(existing_assembly)}/members" not in tabs

    def test_tab_links_carry_no_source_parameter(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Where the data is managed is stored on the project, not passed from page to page."""
        tabs = self._tab_bar(logged_in_admin.get(f"{_details(existing_assembly)}?source=gsheet").data.decode())

        assert "source=" not in tabs

    def test_a_new_project_has_its_targets_tab_open(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Held in OpenDLP until someone says otherwise, so targets can be made straight away."""
        tabs = self._tab_bar(logged_in_admin.get(_details(existing_assembly)).data.decode())

        assert f'href="{_details(existing_assembly)}/targets"' in tabs
