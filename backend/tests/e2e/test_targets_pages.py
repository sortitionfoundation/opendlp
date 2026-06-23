"""ABOUTME: End-to-end PostgreSQL happy-path smokes for the backoffice targets blueprint
ABOUTME: Behavioural coverage (HTMX fragments, validation, auth, permissions) lives in tests/component/"""

import io

import pytest

from opendlp.domain.assembly_csv import AssemblyCSV
from opendlp.domain.respondents import Respondent
from opendlp.domain.selection_settings import SelectionSettings
from opendlp.service_layer.assembly_service import (
    add_target_value,
    create_target_category,
    import_targets_from_csv,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token

VALID_TARGETS_CSV = b"feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"

# Base URL prefix for backoffice targets
PREFIX = "/backoffice/assembly"


def _targets_url(assembly_id, suffix=""):
    return f"{PREFIX}/{assembly_id}/targets{suffix}"


def _csrf(client, assembly_id):
    return get_csrf_token(client, _targets_url(assembly_id))


def _add_respondents(postgres_session_factory, assembly_id, respondents_data):
    """Helper to add respondents with given attributes to an assembly."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        for ext_id, attributes in respondents_data:
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=ext_id, attributes=attributes))
        uow.commit()


class TestViewTargetsPage:
    def test_get_targets_page_shows_existing_categories(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_targets_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.get(_targets_url(existing_assembly.id))
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Male" in response.data
        assert b"Female" in response.data
        assert b"1 categories defined" in response.data


class TestUploadTargetsCsv:
    def test_upload_valid_csv_creates_targets(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/upload"),
            data={
                "csv_file": (io.BytesIO(VALID_TARGETS_CSV), "targets.csv"),
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/backoffice/assembly/{existing_assembly.id}/targets" in response.location

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Successfully imported" in msg for msg in flash_messages)


class TestAddCategory:
    def test_add_category_creates_and_redirects(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/categories"),
            data={
                "name": "Gender",
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Gender" in response.data


class TestDeleteCategory:
    def test_delete_category_redirects(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/delete"),
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )
        assert response.status_code == 200


class TestAddValue:
    def test_add_value_to_category(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values"),
            data={
                "value": "Male",
                "min_count": "5",
                "max_count": "10",
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Male" in response.data


class TestEditValue:
    def test_edit_value(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}"),
            data={
                "value": "Female",
                "min_count": "6",
                "max_count": "12",
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Female" in response.data


class TestDeleteValue:
    def test_delete_value(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/{value_id}/delete"),
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )
        assert response.status_code == 200


class TestEditCategory:
    def test_rename_category(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}"),
            data={
                "name": "Sex",
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Sex" in response.data


class TestAddMissingValues:
    def test_add_missing_values_creates_values(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """Adding missing respondent values bulk-creates them with min=0, max=0."""
        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [
                ("1", {"Gender": "Male"}),
                ("2", {"Gender": "Female"}),
                ("3", {"Gender": "Non-binary"}),
            ],
        )

        # Use a name that doesn't match a respondent column to avoid auto-populate
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Sex")
        # Add one value so the others are "missing"
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 3, 7)

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, f"/categories/{category.id}/values/add-missing"),
            data={
                "missing_values": ["Female", "Non-binary"],
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Female" in response.data
        assert b"Non-binary" in response.data


class TestAddCategoriesFromColumns:
    @pytest.mark.db_semantics
    def test_creates_categories_from_selected_columns(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """Selecting respondent columns creates target categories with auto-added values."""
        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [
                ("1", {"Gender": "Male", "Region": "North"}),
                ("2", {"Gender": "Female", "Region": "South"}),
                ("3", {"Gender": "Female", "Region": "East"}),
            ],
        )

        response = logged_in_admin.post(
            _targets_url(existing_assembly.id, "/categories/add-from-columns"),
            data={
                "columns": ["Gender", "Region"],
                "csrf_token": _csrf(logged_in_admin, existing_assembly.id),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Region" in response.data
        # Values should have been auto-added for low-cardinality columns
        assert b"Male" in response.data
        assert b"Female" in response.data
        assert b"North" in response.data


class TestCheckTargets:
    @pytest.mark.db_semantics
    def test_check_with_valid_data_shows_success(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_targets_from_csv(
                uow=uow, user_id=admin_user.id, assembly_id=existing_assembly.id, csv_content=csv_content
            )

        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [(f"p{i}", {"Gender": "Male" if i % 2 == 0 else "Female"}) for i in range(20)],
        )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            assembly = uow.assemblies.get(existing_assembly.id)
            assembly.number_to_select = 10
            assembly.csv = AssemblyCSV(assembly_id=assembly.id)
            assembly.selection_settings = SelectionSettings(assembly_id=assembly.id, check_same_address=False)
            uow.commit()

        response = logged_in_admin.get(
            _targets_url(existing_assembly.id, "/check"),
            data={"csrf_token": _csrf(logged_in_admin, existing_assembly.id)},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"All checks passed" in response.data


class TestRespondentColumns:
    def test_respondent_columns_returns_fragment(self, logged_in_admin, existing_assembly, postgres_session_factory):
        """The respondent-columns HTMX partial renders the assembly's attribute columns."""
        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [
                ("1", {"Gender": "Male"}),
                ("2", {"Gender": "Female"}),
            ],
        )

        response = logged_in_admin.get(_targets_url(existing_assembly.id, "/respondent-columns"))

        assert response.status_code == 200
        assert b"Gender" in response.data
