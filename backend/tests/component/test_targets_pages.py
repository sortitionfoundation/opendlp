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
from opendlp.service_layer.assembly_service import (
    add_target_value,
    create_target_category,
    import_targets_from_csv,
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
    return create_target_category(FakeUnitOfWork(store=fake_store), admin_user.id, assembly_id, name)


def _add_value(fake_store, admin_user, assembly_id, category_id, value, min_count, max_count):
    return add_target_value(
        FakeUnitOfWork(store=fake_store), admin_user.id, assembly_id, category_id, value, min_count, max_count
    )


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
