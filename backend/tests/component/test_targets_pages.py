# ABOUTME: Component tests for the backoffice targets blueprint over a FakeUnitOfWork
# ABOUTME: Drives the real targets routes + services (render, validation, HTMX fragments, auth, permissions)

import io

import pytest

from opendlp.adapters import database
from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole
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


def _add_respondents(fake_store, assembly_id, respondents_data):
    """Seed respondents with the given attributes into the shared store."""
    with FakeUnitOfWork(store=fake_store) as uow:
        for ext_id, attributes in respondents_data:
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=ext_id, attributes=attributes))
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


class TestAddCategory:
    def test_add_category_htmx_returns_fragment(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/categories"),
            data={"name": "Age"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Age" in response.data
        assert b"<!DOCTYPE" not in response.data

    def test_add_category_htmx_auto_populates_values_from_respondent_column(
        self, logged_in_admin, existing_assembly, fake_store
    ):
        """Adding a category whose name matches a respondent column auto-adds its values."""
        _add_respondents(
            fake_store,
            existing_assembly.id,
            [("1", {"Gender": "Male"}), ("2", {"Gender": "Female"}), ("3", {"Gender": "Non-binary"})],
        )

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/categories"),
            data={"name": "Gender"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Male" in response.data
        assert b"Female" in response.data
        assert b"Non-binary" in response.data
        assert b"<!DOCTYPE" not in response.data


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
    def test_check_button_visible_when_targets_exist(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _import_targets(
            fake_store, admin_user, existing_assembly.id, "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        )

        response = logged_in_admin.get(_targets_url(existing_assembly.id))
        assert response.status_code == 200
        assert b"Check targets in detail" in response.data

    def test_check_button_hidden_when_no_targets(self, logged_in_admin, existing_assembly):
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
        assert b"Add category" not in response.data
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

    def test_a_hand_set_value_is_marked_and_offers_relinking(
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

        assert b"Set by hand" in response.data
        assert b"boosted by 2" in response.data
        assert b"Use percentage" in response.data

    def test_a_linked_value_is_not_marked(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=50.0)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"Set by hand" not in response.data
        assert b"Use percentage" not in response.data


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
    def test_the_page_shows_the_number_to_select(self, logged_in_admin, existing_assembly, fake_store):
        _set_number_to_select(fake_store, existing_assembly.id, 42)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"Number to select: 42" in response.data

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

    def test_the_page_offers_editing_and_adding_a_category(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"Edit targets" in response.data
        assert b"Add category" in response.data

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
        assert "Check targets in detail" in heading_section

    def test_the_heading_says_targets(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()
        heading = html[html.index("<h2") : html.index("</h2>")]

        assert ">Targets" in heading
        assert "Target Categories" not in heading

    def test_a_google_sheet_assembly_gets_no_target_actions(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """Its targets live in the spreadsheet, so there is nothing here to edit or check."""
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
        assert b"Check targets in detail" not in response.data


class TestBulkEditForm:
    def test_offers_adding_and_deleting_rows(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        response = logged_in_admin.get(_targets_url(existing_assembly.id))

        assert b"Add value" in response.data
        assert b"Delete value" in response.data
        assert b"Delete target" in response.data

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

    def test_save_and_cancel_come_before_the_categories(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        """At the top of the form, so a long page need not be scrolled to save."""
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert html.index("Save all") < html.index('id="bulk-categories"')
        assert html.index("Cancel") < html.index("Save all")

    def test_add_value_sits_between_the_last_value_and_the_total(
        self, logged_in_admin, existing_assembly, admin_user, fake_store
    ):
        category = _create_category(fake_store, admin_user, existing_assembly.id, "Gender")
        with FakeUnitOfWork(store=fake_store) as uow:
            add_target_value(uow, admin_user.id, existing_assembly.id, category.id, "Male", percentage=100.0)

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert html.index("Add value") < html.index("<tfoot>")
        assert html.index("</tbody>") < html.index("Add value")

    def test_offers_a_box_for_adding_a_target(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert 'x-model="newCategoryName"' in html
        assert "Add target" in html

    def test_carries_a_blank_category_template(self, logged_in_admin, existing_assembly, admin_user, fake_store):
        """Cloned client-side; __CAT__ becomes new-<n> on the way in."""
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        html = logged_in_admin.get(_targets_url(existing_assembly.id)).data.decode()

        assert 'x-ref="categoryTemplate"' in html
        assert "cat[__CAT__][name]" in html
        assert "cat[__CAT__][values][__ID__][value]" in html

    def test_a_viewer_is_not_given_the_form_at_all(self, logged_in_user, existing_assembly, admin_user, fake_store):
        _create_category(fake_store, admin_user, existing_assembly.id, "Gender")

        response = logged_in_user.get(_targets_url(existing_assembly.id))

        assert b"save-all-form" not in response.data
        assert b"Edit targets" not in response.data
