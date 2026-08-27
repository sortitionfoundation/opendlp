# ABOUTME: Component tests for the backoffice targets blueprint over a FakeUnitOfWork
# ABOUTME: Drives the real targets routes + services (render, validation, HTMX fragments, auth, permissions)

import io
import re

import pytest

from opendlp.adapters import database
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, RespondentStatus
from opendlp.service_layer.assembly_service import add_assembly_gsheet
from opendlp.service_layer.target_service import (
    add_target_value,
    create_target_category,
    get_targets_for_assembly,
    import_targets_from_csv,
    update_target_value,
)
from tests.fakes import FakeUnitOfWork


@pytest.fixture(autouse=True)
def _mapped_domain_objects():
    """Target value services call SQLAlchemy flag_modified, which needs mapped classes."""
    database.start_mappers()


VALID_TARGETS_CSV = b"feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"

INVALID_TARGETS_CSV = b"feature,value,min,max\nGender,Male,15,5\n"

PREFIX = "/backoffice/assembly"


def _targets_url(assembly_id, suffix=""):
    return f"{PREFIX}/{assembly_id}/targets{suffix}"


def _add_respondents(fake_store, assembly_id, respondents_data, status=RespondentStatus.POOL):
    """Seed respondents with the given attributes into the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        for ext_id, attributes in respondents_data:
            uow.respondents.add(
                Respondent(
                    assembly_id=assembly_id,
                    external_id=ext_id,
                    attributes=attributes,
                    selection_status=status,
                )
            )
        uow.commit()


def _import_targets(fake_store, admin_user, assembly_id, csv_content):
    with FakeUnitOfWork(store=fake_store) as uow:
        import_targets_from_csv(uow=uow, user_id=admin_user.id, assembly_id=assembly_id, csv_content=csv_content)


def _create_category(fake_store, admin_user, assembly_id, name):
    with FakeUnitOfWork(store=fake_store) as uow:
        return create_target_category(uow, admin_user.id, assembly_id, name)


def _set_number_to_select(fake_store, assembly_id, number_to_select):
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.assemblies.get(assembly_id).number_to_select = number_to_select
        uow.commit()


def _add_value(fake_store, admin_user, assembly_id, category_id, value, min_count, max_count):
    with FakeUnitOfWork(store=fake_store) as uow:
        return add_target_value(uow, admin_user.id, assembly_id, category_id, value, min_count, max_count)


class TestViewTargetsPage:
    def test_get_targets_page_renders(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(_targets_url(existing_assembly.id))
        assert response.status_code == 200
        assert b"Targets" in response.data

    def test_get_targets_page_shows_empty_state(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(_targets_url(existing_assembly.id))
        assert response.status_code == 200
        assert b"No target categories defined yet" in response.data

    def test_get_targets_page_requires_login(self, client, existing_assembly):
        response = client.get(_targets_url(existing_assembly.id))
        assert response.status_code == 302
        assert "login" in response.location

    def test_get_targets_page_nonexistent_assembly(self, logged_in_admin):
        response = logged_in_admin.get(_targets_url("00000000-0000-0000-0000-000000000099"))
        assert response.status_code == 302


class TestUploadTargetsCsv:
    def test_upload_always_replaces_existing(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _import_targets(
            fake_store, admin_user, existing_assembly.id, "feature,value,min,max\nAge,Young,2,5\nAge,Old,2,5\n"
        )

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/upload"),
            data={"csv_file": (io.BytesIO(VALID_TARGETS_CSV), "new_targets.csv")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        page_response = logged_in_admin.get(_targets_url(existing_assembly.id))
        assert b"Gender" in page_response.data
        assert b"Age" not in page_response.data

    def test_upload_invalid_csv_shows_error(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/upload"),
            data={"csv_file": (io.BytesIO(INVALID_TARGETS_CSV), "bad.csv")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"There is a problem" in response.data

    def test_upload_no_file_shows_validation_error(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/upload"),
            data={},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"There is a problem" in response.data

    def test_upload_non_csv_file_shows_validation_error(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/upload"),
            data={"csv_file": (io.BytesIO(b"not a csv"), "targets.txt")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Only CSV files are allowed" in response.data


class TestDeleteCategory:
    def test_delete_category_htmx_returns_empty(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/delete"),
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert response.data == b""


class TestAddValue:
    def test_add_value_htmx_returns_fragment(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values"),
            data={"value": "Male", "min_count": "5", "max_count": "10"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Male" in response.data
        assert b"<!DOCTYPE" not in response.data

    def test_add_value_invalid_min_max(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values"),
            data={"value": "Male", "min_count": "10", "max_count": "5"},
            follow_redirects=True,
        )
        assert response.status_code == 200


class TestEditValue:
    def test_edit_value_htmx_returns_fragment(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}"),
            data={"value": "Female", "min_count": "6", "max_count": "12"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Female" in response.data
        assert b"<!DOCTYPE" not in response.data


class TestDeleteValue:
    def test_delete_value_htmx_returns_fragment(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 5, 10)
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Female", 3, 7)
        male_value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{male_value_id}/delete"),
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Female" in response.data
        assert b"<!DOCTYPE" not in response.data


class TestEditCategory:
    def test_rename_category_htmx_returns_fragment(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}"),
            data={"name": "Sex"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Sex" in response.data
        assert b"<!DOCTYPE" not in response.data


class TestAddMissingValues:
    def test_add_missing_values_htmx_returns_fragment(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """HTMX request returns a category block fragment instead of redirecting."""
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("1", {"Gender": "Male"}), ("2", {"Gender": "Female"})],
        )

        # Use a name that doesn't match a respondent column to avoid auto-populate
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Sex")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/add-missing"),
            data={"missing_values": ["Male", "Female"]},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Male" in response.data
        assert b"Female" in response.data
        assert b"<!DOCTYPE" not in response.data

    def test_add_missing_values_no_values_redirects(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """Posting with no missing values shows a warning and redirects."""
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{existing_assembly.id}/values/add-missing"),
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestAddCategoriesFromColumns:
    def test_creates_single_category_from_column(self, logged_in_admin, existing_assembly, fake_store):
        """Selecting a single column creates one target category."""
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("1", {"Age": "18-25"}), ("2", {"Age": "26-35"})],
        )

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/categories/add-from-columns"),
            data={"columns": ["Age"]},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Created 1 categories" in msg for msg in flash_messages)

    def test_no_columns_selected_shows_warning(self, logged_in_admin, existing_assembly):
        """Posting with no columns selected shows a warning."""
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/categories/add-from-columns"),
            data={},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("No columns selected" in msg for msg in flash_messages)


class TestCheckTargets:
    def test_the_page_offers_no_check_button(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """Saving runs the check, so there is nothing left for a button to do."""
        _import_targets(
            fake_store, admin_user, existing_assembly.id, "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        )

        response = logged_in_admin.get(_targets_url(existing_assembly.id))
        assert response.status_code == 200
        assert b"Check targets in detail" not in response.data

    def test_check_with_insufficient_respondents_shows_error(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _import_targets(
            fake_store, admin_user, existing_assembly.id, "feature,value,min,max\nGender,Male,5,7\nGender,Female,5,7\n"
        )

        # Only 1 female, but min is 5
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("p0", {"Gender": "Female"})] + [(f"p{i}", {"Gender": "Male"}) for i in range(1, 20)],
        )

        with FakeUnitOfWork(store=fake_store) as uow:
            assembly = uow.assemblies.get(existing_assembly.id)
            assembly.number_to_select = 10
            assembly.csv = AssemblyCSV(assembly_id=assembly.id)
            assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
            uow.commit()

        response = logged_in_admin.get(
            _targets_url(existing_assembly.id, "/check"),
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Target check found problems" in response.data
        # Should have inline error annotation for "female"
        assert b"respondents match" in response.data

    def test_check_requires_login(self, client, existing_assembly):
        response = client.get(_targets_url(existing_assembly.id, "/check"))
        assert response.status_code == 302
        assert "login" in response.location


class TestViewerPermissions:
    def test_viewer_sees_targets_without_edit_controls(self, logged_in_user, existing_assembly, admin_user, fake_store):
        _import_targets(
            fake_store, admin_user, existing_assembly.id, "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        )

        with FakeUnitOfWork(store=fake_store) as uow:
            regular = uow.users.get_by_email("user@example.com")
            if regular:
                role = UserAssemblyRole(
                    user_id=regular.id,
                    assembly_id=existing_assembly.id,
                    role=AssemblyRole.CONFIRMATION_CALLER,
                )
                regular.assembly_roles.append(role)
                uow.commit()

        response = logged_in_user.get(_targets_url(existing_assembly.id))
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Male" in response.data
        assert b"Add target" not in response.data
        assert b"Add value" not in response.data


class TestPercentageColumn:
    def test_page_shows_the_percentage_and_its_total(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=48.5)
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Female", percentage=51.5)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert response.status_code == 200
        assert b"48.5%" in response.data
        assert b"100.0%" in response.data

    def test_a_hand_set_value_keeps_its_note_and_offers_relinking(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            cat = add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=50.0)
        value_id = cat.values[0].value_id
        with FakeUnitOfWork(store=fake_store) as uow:
            update_target_value(
                uow,
                admin_user.id,
                existing_assembly.id,
                category.id,
                value_id,
                value="Male",
                min_count=1,
                max_count=2,
                comment="boosted by 2",
            )

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"boosted by 2" in response.data
        relink = _edit_form_button(_edit_form_html(response.data.decode()), "Male", "Use percentage")
        assert not _is_disabled(relink)

    def test_the_column_heading_reads_population(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """The heading is escaped as `%%` for gettext, so check what actually reaches the page."""
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"Population (%)" in response.data
        assert b"Population (%%)" not in response.data

    def test_a_linked_value_is_offered_relinking_only_as_a_dead_control(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Greyed out, not gone: a control that vanishes is harder to find than one plainly unavailable."""
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=50.0)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        relink = _edit_form_button(_edit_form_html(response.data.decode()), "Male", "Use percentage")
        assert _is_disabled(relink)


class TestCategorySourceAndComment:
    def test_source_url_renders_as_a_link(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _import_targets(
            fake_store,
            admin_user,
            existing_assembly.id,
            "feature,value,min,max,source_url,category_comment\n"
            "Gender,Male,3,7,https://www.ons.gov.uk/dataset,see https://example.com/notes\n",
        )

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b'href="https://www.ons.gov.uk/dataset"' in response.data
        assert b'rel="noopener noreferrer"' in response.data
        # The comment's own URL is linkified too.
        assert b'href="https://example.com/notes"' in response.data


def _read_only_row_cells(html_text, value):
    """The cells of the read-only value row for `value`, in column order."""
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.DOTALL)
    row = next(r for r in rows if re.search(rf">\s*{re.escape(value)}\s*<", r))
    return re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)


class TestValueCommentColumn:
    def test_a_value_comment_renders_in_its_own_column(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _import_targets(
            fake_store,
            admin_user,
            existing_assembly.id,
            "feature,value,min,max,comment\nGender,Woman,3,7,boosted by 2\n",
        )

        html_text = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert _column_headings(_read_only_html(html_text))[-1] == "Comment"
        cells = _read_only_row_cells(html_text, "Woman")
        # Value, Population (%), Min, Max, Comment
        assert len(cells) == 5
        assert "boosted by 2" not in cells[0]
        assert "boosted by 2" in cells[4]


def _edit_form_html(html_text):
    """The half of the targets page holding the bulk edit form."""
    return html_text.split('id="target-categories"')[0]


def _read_only_html(html_text):
    """The half of the targets page holding the read-only category blocks."""
    return html_text.split('id="target-categories"')[1]


def _column_headings(html_text):
    """The column headings of the first values table in `html_text`.

    A heading's hover note is written out for screen readers as well, so drop
    that before reading the label off the cell.
    """
    head = re.search(r"<thead>(.*?)</thead>", html_text, re.DOTALL).group(1)
    cells = re.findall(r"<th[^>]*>(.*?)</th>", head, re.DOTALL)
    cells = [re.sub(r'<span class="sr-only">.*?</span>', "", cell, flags=re.DOTALL) for cell in cells]
    return [re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", cell)).strip() for cell in cells]


def _edit_form_button(html_text, value, label):
    """The bulk edit form's button named `label`, on the row for `value`."""
    actions = _edit_form_row_cells(html_text, value)[-1]
    buttons = re.findall(r"<button\b.*?</button>", actions, re.DOTALL)
    return next(b for b in buttons if f'aria-label="{label}"' in b)


def _is_disabled(button_html):
    """Whether a rendered button carries the `disabled` attribute.

    Matched with the space in front of it: an enabled button can still carry
    Alpine's `:disabled` binding, which is not the same claim.
    """
    return re.search(r"\sdisabled[\s>]", button_html) is not None


def _edit_form_row_cells(html_text, value):
    """The cells of the bulk edit form row for `value`, in column order."""
    rows = re.findall(r'<tr data-value-row="true".*?</tr>', html_text, re.DOTALL)
    row = next(r for r in rows if re.search(rf'value="{re.escape(value)}"', r))
    return [re.sub(r"\s+", " ", cell).strip() for cell in re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)]


def _edit_form_category_header(html_text):
    """The header row of the first category block in the bulk edit form.

    Sliced rather than parsed: the row holds nested divs of its own, and
    everything between it and the values table belongs to it.
    """
    edit_form = _edit_form_html(html_text)
    start = edit_form.index('class="mb-4 flex flex-wrap items-end gap-3"')
    return edit_form[start : edit_form.index("<table", start)]


def _named_button(html_text, label):
    """The button in `html_text` whose accessible name is `label`.

    An icon button carries its name in aria-label; one with a visible label
    carries it in the text.
    """
    buttons = re.findall(r"<button\b.*?</button>", html_text, re.DOTALL)
    return next(b for b in buttons if f'aria-label="{label}"' in b or f">{label}<" in b)


class TestRespondentCountColumns:
    """How many respondents hold each value, next to the percentage it is judged against.

    Both counts sit between "Population (%)" and "Min" - on the read-only page
    and in the edit form alike, so a column means the same thing on either.
    """

    def _gender_targets(self, fake_store, admin_user, assembly_id):
        _import_targets(
            fake_store,
            admin_user,
            assembly_id,
            "feature,value,min,max\nGender,Woman,3,7\nGender,Man,3,7\n",
        )

    def _gender_respondents(self, fake_store, assembly_id):
        _add_respondents(
            fake_store,
            assembly_id,
            [("r1", {"Gender": "Woman"}), ("r2", {"Gender": "Woman"}), ("r3", {"Gender": "Man"})],
        )

    def test_the_read_only_table_counts_respondents_before_min(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        self._gender_targets(fake_store, admin_user, existing_assembly.id)
        self._gender_respondents(fake_store, existing_assembly.id)

        html_text = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        read_only = _read_only_html(html_text)
        assert _column_headings(read_only) == ["Value", "Population (%)", "Respondents", "Min", "Max", "Comment"]
        cells = _read_only_row_cells(read_only, "Woman")
        assert cells[2].strip() == "2"

    def test_the_edit_form_counts_respondents_before_min(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        self._gender_targets(fake_store, admin_user, existing_assembly.id)
        self._gender_respondents(fake_store, existing_assembly.id)

        html_text = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        edit_form = _edit_form_html(html_text)
        assert _column_headings(edit_form) == [
            "Value",
            "Population (%)",
            "Respondents",
            "Min",
            "Max",
            "Comment",
            "Actions",
        ]
        assert _edit_form_row_cells(edit_form, "Woman")[2] == "2"

    def test_the_edit_form_counts_read_from_the_left(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """They sit in a row of form fields, and every one of those starts at its left edge.

        Right-aligned numbers read well in a table of numbers. This is not one:
        the eye running down the row meets a boxed input either side of them.
        """
        self._gender_targets(fake_store, admin_user, existing_assembly.id)
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("r1", {"Gender": "Woman"})],
            status=RespondentStatus.SELECTED,
        )

        edit_form = _edit_form_html(logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode())

        head = re.search(r"<thead>(.*?)</thead>", edit_form, re.DOTALL).group(1)
        for column in ("Respondents", "Selected"):
            heading = next(th for th in re.findall(r"<th[^>]*>.*?</th>", head, re.DOTALL) if column in th)
            assert "text-left" in heading.split(">")[0], f"{column} is not left aligned"
        row = re.findall(r'<tr data-value-row="true".*?</tr>', edit_form, re.DOTALL)[0]
        assert all("text-left" in cell for cell in re.findall(r"<td[^>]*>", row)[2:4])

    @pytest.mark.parametrize(
        ("column", "note"),
        [
            (
                "Respondents",
                (
                    "Counts people in the pool, and those selected or confirmed. "
                    "Withdrawn people and test submissions are not counted."
                ),
            ),
            (
                "Selected",
                "Counts people who have been selected, including those who have since confirmed their place.",
            ),
        ],
    )
    def test_each_count_heading_says_who_is_counted(
        self, column, note, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Which people a column counts is not something one word at the top of it can say."""
        self._gender_targets(fake_store, admin_user, existing_assembly.id)
        self._gender_respondents(fake_store, existing_assembly.id)
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("r4", {"Gender": "Woman"})],
            status=RespondentStatus.CONFIRMED,
        )

        html_text = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        for view in (_read_only_html(html_text), _edit_form_html(html_text)):
            head = re.search(r"<thead>(.*?)</thead>", view, re.DOTALL).group(1)
            heading = next(th for th in re.findall(r"<th[^>]*>(.*?)</th>", head, re.DOTALL) if column in th)
            assert f'title="{note}"' in heading, "the icon has no hover text"
            assert f'<span class="sr-only">{note}</span>' in heading, "the note is there for a mouse only"

    def test_selected_respondents_get_their_own_column(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """A confirmed respondent has been selected too, so both statuses count."""
        self._gender_targets(fake_store, admin_user, existing_assembly.id)
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("r1", {"Gender": "Woman"})],
            status=RespondentStatus.SELECTED,
        )
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("r2", {"Gender": "Woman"}), ("r3", {"Gender": "Man"})],
            status=RespondentStatus.CONFIRMED,
        )

        html_text = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        expected = ["Value", "Population (%)", "Respondents", "Selected", "Min", "Max", "Comment"]
        assert _column_headings(_read_only_html(html_text)) == expected
        assert _column_headings(_edit_form_html(html_text)) == [*expected, "Actions"]
        assert _read_only_row_cells(_read_only_html(html_text), "Woman")[3].strip() == "2"
        assert _edit_form_row_cells(_edit_form_html(html_text), "Woman")[3] == "2"

    def test_a_value_no_respondent_holds_is_counted_as_a_dash(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Zero would claim the value was asked about and nobody chose it."""
        self._gender_targets(fake_store, admin_user, existing_assembly.id)
        _add_respondents(fake_store, existing_assembly.id, [("r1", {"Gender": "Woman"})])

        html_text = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        count_cell = _edit_form_row_cells(_edit_form_html(html_text), "Man")[2]
        assert "&mdash;" in count_cell
        assert "0" not in count_cell

    def test_a_category_with_no_respondent_data_gets_no_count_columns(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        self._gender_targets(fake_store, admin_user, existing_assembly.id)

        html_text = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert _column_headings(_read_only_html(html_text)) == ["Value", "Population (%)", "Min", "Max", "Comment"]
        assert _column_headings(_edit_form_html(html_text)) == [
            "Value",
            "Population (%)",
            "Min",
            "Max",
            "Comment",
            "Actions",
        ]


class TestMinMaxProvenance:
    """Min and max say where they came from, in the cells themselves.

    The read-only row is what these assert against: the bulk edit form is on the
    same page, hidden, and carries its own copy of every value.
    """

    def _hand_set_row(self, admin_user, existing_assembly, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            cat = add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=50.0)
        value_id = cat.values[0].value_id
        with FakeUnitOfWork(store=fake_store) as uow:
            update_target_value(
                uow,
                admin_user.id,
                existing_assembly.id,
                category.id,
                value_id,
                value="Male",
                min_count=1,
                max_count=2,
            )

    def test_hand_set_min_and_max_are_marked_as_manual(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        self._hand_set_row(admin_user, existing_assembly, fake_store)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        min_cell, max_cell = _read_only_row_cells(response.data.decode(), "Male")[2:4]
        for cell in (min_cell, max_cell):
            assert "var(--color-warning-100)" in cell
            assert "Manually modified" in cell
            assert "Auto calculated" not in cell

    def test_the_value_cell_carries_no_badge_of_its_own(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        self._hand_set_row(admin_user, existing_assembly, fake_store)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert "Set by hand" not in _read_only_row_cells(response.data.decode(), "Male")[0]

    def test_calculated_min_and_max_are_marked_as_automatic(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=50.0)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        min_cell, max_cell = _read_only_row_cells(response.data.decode(), "Male")[2:4]
        for cell in (min_cell, max_cell):
            assert "var(--color-info-100)" in cell
            assert "Auto calculated" in cell
            assert "Manually modified" not in cell

    def test_a_value_with_no_percentage_is_left_plain(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """With nothing to calculate from, neither reading applies."""
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 3, 7)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        min_cell, max_cell = _read_only_row_cells(response.data.decode(), "Male")[2:4]
        for cell in (min_cell, max_cell):
            assert "background-color: transparent" in cell
            assert "Auto calculated" not in cell
            assert "Manually modified" not in cell


class TestEditValueWithPercentage:
    def test_editing_the_percentage_recalculates_min_and_max(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _set_number_to_select(fake_store, existing_assembly.id, 10)
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 0, 0)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}"),
            data={"value": "Male", "percentage": "50", "min_count": "0", "max_count": "0"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        with FakeUnitOfWork(store=fake_store) as uow:
            value = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values[0]
        assert value.percentage_target == 50.0
        assert (value.min, value.max) == (5, 6)

    def test_a_percentage_with_no_seat_count_leaves_min_and_max_at_zero(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Zero is the honest answer while number_to_select is unknown."""
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 0, 0)
        value_id = cat.values[0].value_id

        logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}"),
            data={"value": "Male", "percentage": "50", "min_count": "0", "max_count": "0"},
            headers={"HX-Request": "true"},
        )

        with FakeUnitOfWork(store=fake_store) as uow:
            value = get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].values[0]
        assert value.percentage_target == 50.0
        assert (value.min, value.max) == (0, 0)

    def test_an_invalid_percentage_is_a_422_not_a_500(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 0, 0)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}"),
            data={"value": "Male", "percentage": "150"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 422


class TestEditCategorySourceUrl:
    def test_an_invalid_source_url_is_a_422_not_a_500(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}"),
            data={"name": "Gender", "source_url": "javascript:alert(1)"},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 422


class TestMoveCategoryPermissions:
    def test_a_viewer_cannot_reorder(self, logged_in_user, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_user.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/move"),
            data={"direction": "down"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        with FakeUnitOfWork(store=fake_store) as uow:
            assert get_targets_for_assembly(uow, admin_user.id, existing_assembly.id)[0].name == "Gender"


class TestViewIsReadOnly:
    def test_the_page_shows_the_number_to_select(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """Under the heading, where a tally of the categories used to be.

        Every min and max on the page is a share of the seat count, and the
        categories are listed right below - so one number is worth reading and
        the other is worth counting for yourself.
        """
        _set_number_to_select(fake_store, existing_assembly.id, 42)
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"Number to select: 42" in response.data
        assert b"categories defined" not in response.data

    def test_the_category_block_offers_no_way_to_change_anything(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Every change goes through "Edit targets", so the read-only block has no controls.

        Asserted against the HTMX partial rather than the whole page, because the
        page also carries the bulk edit form, where all of these do belong.
        """
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values"),
            data={"value": "Male", "min_count": 1, "max_count": 2},
            headers={"HX-Request": "true"},
        )

        assert response.status_code == 200
        assert b"Male" in response.data
        for control in (b"Add value", b"Delete", b"Move up", b"Move down", b"Rename", b"Use percentage"):
            assert control not in response.data, control

    def test_the_page_offers_editing_and_adding_a_target(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"Edit targets" in response.data
        assert b"Add target" in response.data

    def test_an_assembly_with_no_targets_can_still_add_one(self, logged_in_admin, existing_assembly):
        """ "Add target" clones into the bulk form, so the form has to be there first."""
        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert "Add target" in html
        assert 'id="save-all-form"' in html
        assert 'x-ref="categoryTemplate"' in html
        # Nothing to edit yet, so nothing offers to.
        assert "Edit targets" not in html

    def test_the_page_guards_against_leaving_with_unsaved_edits(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert "leave-modal" in html
        assert "Discard changes?" in html
        # Typing, and the structural changes that fire no input event of their own.
        assert 'x-data="targetsPage(' in html
        assert '@input="markEditDirty()"' in html
        assert '@targets-changed="markEditDirty()"' in html
        # Saving is the one way out that keeps the edits.
        assert '@submit="allowLeave()"' in html

    def test_save_and_discard_sit_in_the_sticky_bar_not_the_heading_cluster(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The form is long, so the way out of it follows the viewport down the page."""
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()
        heading_section = html[html.index("<h2") : html.index("</section>", html.index("<h2"))]
        save_bar = html[html.index('class="wizard-footer"') :]

        assert "Save" not in heading_section
        assert "Discard changes" not in heading_section
        assert "Discard changes" in save_bar
        # Outside the form it submits, so it needs the form attribute.
        assert 'form="save-all-form"' in save_bar

    def test_the_edit_targets_button_is_the_primary_action(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()
        heading_section = html[html.index("<h2") : html.index("</section>", html.index("<h2"))]
        edit_button = heading_section[: heading_section.index("Edit targets")].rsplit("<button", 1)[-1]

        assert "btn--primary" in edit_button

    def test_the_page_actions_sit_level_with_the_targets_heading(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Beside the <h2>, not stacked in a band beneath it."""
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()
        heading_section = html[html.index("<h2") : html.index("</section>", html.index("<h2"))]

        assert "Edit targets" in heading_section

    def test_the_heading_says_targets(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()
        heading = html[html.index("<h2") : html.index("</h2>")]

        assert ">Targets" in heading
        assert "Target Categories" not in heading

    def test_a_google_sheet_assembly_gets_no_target_actions(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Its targets live in the spreadsheet, so there is nothing here to edit."""
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_assembly_gsheet(
                uow=uow,
                assembly_id=existing_assembly.id,
                user_id=admin_user.id,
                url="https://docs.google.com/spreadsheets/d/1234567890abcdef/edit",
                team="uk",
            )

        response = logged_in_admin.get(_targets_url(existing_assembly.id) + "?source=gsheet")

        assert b"Edit targets" not in response.data


def _bulk_row_for(html_text, value):
    """The bulk-edit table row whose value input holds this target value."""
    rows = re.findall(r"<tr [^>]*data-value-row[^>]*>(.*?)</tr>", html_text, re.DOTALL)
    return next(r for r in rows if f'value="{value}"' in r)


class TestSaveAllValidationErrors:
    """A rejected save must come back as the form the user was filling in.

    Redirecting to the read-only page throws away every edit on it and leaves
    the message floating in a toast with nothing to point at.
    """

    def _post_min_above_max(self, client, assembly_id, category_id, value_id):
        prefix = f"cat[{category_id}]"
        return client.post(
            _targets_url(assembly_id, "/save-all"),
            data={
                f"{prefix}[name]": "Gender",
                f"{prefix}[comment]": "from the census",
                f"{prefix}[values][{value_id}][value]": "Male",
                f"{prefix}[values][{value_id}][min]": "9",
                f"{prefix}[values][{value_id}][max]": "2",
            },
        )

    def test_a_min_above_max_comes_back_as_the_form(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 3, 7)
        value_id = cat.values[0].value_id

        response = self._post_min_above_max(logged_in_admin, existing_assembly.id, category.id, value_id)

        assert response.status_code == 200, "a rejected save should re-render, not redirect"

    def test_the_submitted_values_are_still_in_the_form(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 3, 7)
        value_id = cat.values[0].value_id

        response = self._post_min_above_max(logged_in_admin, existing_assembly.id, category.id, value_id)

        html = response.data.decode()
        row = _bulk_row_for(html, "Male")
        assert 'value="9"' in row, "the min they typed is gone"
        assert 'value="2"' in row, "the max they typed is gone"
        assert 'value="from the census"' in html, "the category comment they typed is gone"

    def test_the_error_sits_on_the_field_that_caused_it(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 3, 7)
        value_id = cat.values[0].value_id

        response = self._post_min_above_max(logged_in_admin, existing_assembly.id, category.id, value_id)

        row = _bulk_row_for(response.data.decode(), "Male")
        assert "Max must be at least the min" in row

    def test_the_redisplayed_form_still_counts_the_respondents(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        cat = _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 3, 7)
        value_id = cat.values[0].value_id
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("r1", {"Gender": "Male"})],
            status=RespondentStatus.CONFIRMED,
        )

        response = self._post_min_above_max(logged_in_admin, existing_assembly.id, category.id, value_id)

        edit_form = _edit_form_html(response.data.decode())
        assert _column_headings(edit_form) == [
            "Value",
            "Population (%)",
            "Respondents",
            "Selected",
            "Min",
            "Max",
            "Comment",
            "Actions",
        ]

    # "nothing was saved" is asserted in tests/e2e: FakeUnitOfWork snapshots the
    # repository lists, not the objects in them, so it cannot roll back a field
    # written in place. Only a real transaction proves that claim.


class TestBulkEditForm:
    def test_offers_adding_and_deleting_rows(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"Add value" in response.data
        assert b"Delete value" in response.data
        assert b"Delete target" in response.data

    def test_the_row_controls_carry_live_click_handlers(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """An escaped @click looks fine on the page and does nothing when clicked."""
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        _add_value(fake_store, admin_user, existing_assembly.id, category.id, "Male", 1, 2)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        actions = _edit_form_row_cells(_edit_form_html(response.data.decode()), "Male")[-1]
        assert '@click="usePercentage()"' in actions
        assert '@click="remove()"' in actions
        assert "&#34;" not in actions, "an attribute was escaped on its way into the markup"

    def test_carries_a_totals_row_for_the_browser_to_fill_in(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b'x-text="percentageTotal"' in response.data
        assert b'x-text="minTotal"' in response.data
        assert b'x-text="maxTotal"' in response.data

    def test_carries_a_blank_row_template_for_adding_values(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """The template is cloned client-side; __ID__ becomes new-<n> on the way in."""
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b'x-ref="rowTemplate"' in response.data
        assert f"cat[{category.id}][values][__ID__][value]".encode() in response.data

    def test_offers_the_values_found_in_the_respondent_data(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("r1", {"Gender": "Male"}), ("r2", {"Gender": "Non-binary"})],
        )

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b'x-ref="missingTemplate"' in response.data
        assert b"Add values found in respondent data" in response.data
        assert b"Non-binary" in response.data

    def test_save_and_discard_come_after_everything_they_stick_over(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Sticky, so its containing block has to cover the page it follows down."""
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()
        save_bar = html.index('class="wizard-footer"')

        assert html.index('id="bulk-categories"') < save_bar
        assert html.index("Import from CSV") < save_bar
        assert html.index("Discard changes", save_bar) < html.index("Save", save_bar)

    def test_add_value_sits_between_the_last_value_and_the_total(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert html.index("Add value") < html.index("<tfoot>")
        assert html.index("</tbody>") < html.index("Add value")

    def test_offers_a_dialog_for_adding_a_target(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert "add-target-modal" in html
        assert 'x-model="newCategoryName"' in html
        assert 'x-show="editingAll"' in html

    def test_carries_a_blank_category_template(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """Cloned client-side; __CAT__ becomes new-<n> on the way in."""
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert 'x-ref="categoryTemplate"' in html
        assert "cat[__CAT__][name]" in html
        # It arrives with the one blank row the person adding it is about to fill in.
        assert "cat[__CAT__][values][__ROW__][value]" in html
        assert "cat[__CAT__][values][__ID__][value]" in html

    def test_a_viewer_is_not_given_the_form_at_all(self, logged_in_user, existing_assembly, admin_user, fake_store):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_user.get(_targets_url(existing_assembly.id))

        assert b"save-all-form" not in response.data
        assert b"Edit targets" not in response.data


class TestCategoryOrderControls:
    """Moving and deleting a target sit at the right edge of its header row.

    They reshape the page rather than fill anything in, so they are kept clear
    of the fields - and the two that only shuffle a block are icons, which is
    all a repeated control needs to be.
    """

    def _header(self, logged_in_admin, assembly_id):
        return _edit_form_category_header(logged_in_admin.get(_targets_url(assembly_id)).data.decode())

    @pytest.mark.parametrize(("label", "handler"), [("Move down", "moveDown()"), ("Move up", "moveUp()")])
    def test_moving_a_category_is_an_icon_button(
        self, label, handler, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """An escaped @click looks fine on the page and does nothing when clicked."""
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        control = _named_button(self._header(logged_in_admin, existing_assembly.id), label)

        assert "btn--icon" in control
        assert "<svg" in control, "the control is still spelled out in words"
        assert f'@click="{handler}"' in control

    def test_the_controls_follow_the_fields(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        header = self._header(logged_in_admin, existing_assembly.id)

        last_field = header.index(f"cat[{category.id}][comment]")
        assert header.index("ml-auto") > last_field, "the controls are not pushed to the right edge"
        for marker in ('aria-label="Move down"', 'aria-label="Move up"', "Delete target"):
            assert header.index(marker) > last_field, marker
