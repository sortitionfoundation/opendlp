"""ABOUTME: End-to-end tests for the targets blueprint pages
ABOUTME: Tests viewing targets, adding/editing/deleting categories and values, and CSV upload"""

import io

from opendlp.domain.respondents import Respondent
from opendlp.domain.users import UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole
from opendlp.service_layer.assembly_service import (
    add_target_value,
    create_target_category,
    import_targets_from_csv,
)
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token

VALID_TARGETS_CSV = b"feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"

INVALID_TARGETS_CSV = b"feature,value,min,max\nGender,Male,15,5\n"


class TestViewTargetsPage:
    def test_get_targets_page_renders(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/targets")
        assert response.status_code == 200
        assert b"Targets" in response.data
        assert b"Import from CSV" in response.data

    def test_get_targets_page_shows_empty_state(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/targets")
        assert response.status_code == 200
        assert b"No target categories defined yet" in response.data

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

        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/targets")
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Male" in response.data
        assert b"Female" in response.data
        assert b"1 categories defined" in response.data

    def test_get_targets_page_requires_login(self, client, existing_assembly):
        response = client.get(f"/assemblies/{existing_assembly.id}/targets")
        assert response.status_code == 302
        assert "login" in response.location

    def test_get_targets_page_nonexistent_assembly(self, logged_in_admin):
        response = logged_in_admin.get("/assemblies/00000000-0000-0000-0000-000000000099/targets")
        assert response.status_code == 302


class TestUploadTargetsCsv:
    def test_upload_valid_csv_creates_targets(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/upload",
            data={
                "csv_file": (io.BytesIO(VALID_TARGETS_CSV), "targets.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}/targets" in response.location

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Successfully imported" in msg for msg in flash_messages)

    def test_upload_always_replaces_existing(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "feature,value,min,max\nAge,Young,2,5\nAge,Old,2,5\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_targets_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/upload",
            data={
                "csv_file": (io.BytesIO(VALID_TARGETS_CSV), "new_targets.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        page_response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/targets")
        assert b"Gender" in page_response.data
        assert b"Age" not in page_response.data

    def test_upload_replaces_existing_with_same_feature_names(
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

        new_csv = b"feature,value,min,max\nGender,Male,4,8\nGender,Female,2,6\n"
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/upload",
            data={
                "csv_file": (io.BytesIO(new_csv), "new_targets.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Successfully imported" in msg for msg in flash_messages)

    def test_warning_shown_when_targets_exist(
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

        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/targets")
        assert response.status_code == 200
        assert b"will replace all existing target categories" in response.data

    def test_upload_invalid_csv_shows_error(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/upload",
            data={
                "csv_file": (io.BytesIO(INVALID_TARGETS_CSV), "bad.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("CSV import failed" in msg for msg in flash_messages)

    def test_upload_no_file_shows_validation_error(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/upload",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"There is a problem" in response.data

    def test_upload_non_csv_file_shows_validation_error(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/upload",
            data={
                "csv_file": (io.BytesIO(b"not a csv"), "targets.txt"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"Only CSV files are allowed" in response.data


class TestAddCategory:
    def test_add_category_creates_and_redirects(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories",
            data={
                "name": "Gender",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Gender" in response.data

    def test_add_category_htmx_returns_fragment(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories",
            data={
                "name": "Age",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Age" in response.data
        assert b"<!DOCTYPE" not in response.data


class TestDeleteCategory:
    def test_delete_category_redirects(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/delete",
            data={"csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets")},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_delete_category_htmx_returns_empty(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/delete",
            data={"csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets")},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert response.data == b""


class TestAddValue:
    def test_add_value_to_category(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values",
            data={
                "value": "Male",
                "min_count": "5",
                "max_count": "10",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Male" in response.data

    def test_add_value_htmx_returns_fragment(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values",
            data={
                "value": "Male",
                "min_count": "5",
                "max_count": "10",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Male" in response.data
        assert b"<!DOCTYPE" not in response.data

    def test_add_value_invalid_min_max(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values",
            data={
                "value": "Male",
                "min_count": "10",
                "max_count": "5",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200


class TestEditValue:
    def test_edit_value(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values/{value_id}",
            data={
                "value": "Female",
                "min_count": "6",
                "max_count": "12",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Female" in response.data

    def test_edit_value_htmx_returns_fragment(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values/{value_id}",
            data={
                "value": "Female",
                "min_count": "6",
                "max_count": "12",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Female" in response.data
        assert b"<!DOCTYPE" not in response.data


class TestDeleteValue:
    def test_delete_value(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 5, 10)
        value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values/{value_id}/delete",
            data={"csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets")},
            follow_redirects=True,
        )
        assert response.status_code == 200

    def test_delete_value_htmx_returns_fragment(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 5, 10)
        uow3 = SqlAlchemyUnitOfWork(postgres_session_factory)
        cat = add_target_value(uow3, admin_user.id, existing_assembly.id, category.id, "Female", 3, 7)
        male_value_id = cat.values[0].value_id

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values/{male_value_id}/delete",
            data={"csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets")},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Female" in response.data
        assert b"<!DOCTYPE" not in response.data


class TestEditCategory:
    def test_rename_category(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}",
            data={
                "name": "Sex",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Sex" in response.data

    def test_rename_category_htmx_returns_fragment(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}",
            data={
                "name": "Sex",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Sex" in response.data
        assert b"<!DOCTYPE" not in response.data


def _add_respondents(postgres_session_factory, assembly_id, respondents_data):
    """Helper to add respondents with given attributes to an assembly."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        for ext_id, attributes in respondents_data:
            uow.respondents.add(Respondent(assembly_id=assembly_id, external_id=ext_id, attributes=attributes))
        uow.commit()


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

        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")
        # Add one value so the others are "missing"
        uow2 = SqlAlchemyUnitOfWork(postgres_session_factory)
        add_target_value(uow2, admin_user.id, existing_assembly.id, category.id, "Male", 3, 7)

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values/add-missing",
            data={
                "missing_values": ["Female", "Non-binary"],
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Female" in response.data
        assert b"Non-binary" in response.data

    def test_add_missing_values_htmx_returns_fragment(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """HTMX request returns a category block fragment instead of redirecting."""
        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [
                ("1", {"Gender": "Male"}),
                ("2", {"Gender": "Female"}),
            ],
        )

        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        category = create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{category.id}/values/add-missing",
            data={
                "missing_values": ["Male", "Female"],
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200
        assert b"Male" in response.data
        assert b"Female" in response.data
        assert b"<!DOCTYPE" not in response.data

    def test_add_missing_values_no_values_redirects(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """Posting with no missing values shows a warning and redirects."""
        uow = SqlAlchemyUnitOfWork(postgres_session_factory)
        create_target_category(uow, admin_user.id, existing_assembly.id, "Gender")

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/{existing_assembly.id}/values/add-missing",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302


class TestAddCategoriesFromColumns:
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
            f"/assemblies/{existing_assembly.id}/targets/categories/add-from-columns",
            data={
                "columns": ["Gender", "Region"],
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
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

    def test_creates_single_category_from_column(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """Selecting a single column creates one target category."""
        _add_respondents(
            postgres_session_factory,
            existing_assembly.id,
            [
                ("1", {"Age": "18-25"}),
                ("2", {"Age": "26-35"}),
            ],
        )

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/add-from-columns",
            data={
                "columns": ["Age"],
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Created 1 categories" in msg for msg in flash_messages)

    def test_no_columns_selected_shows_warning(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        """Posting with no columns selected shows a warning."""
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/targets/categories/add-from-columns",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/targets"),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("No columns selected" in msg for msg in flash_messages)


class TestViewerPermissions:
    def test_viewer_sees_targets_without_edit_controls(
        self, logged_in_user, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_targets_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            regular = uow.users.get_by_email("user@example.com")
            if regular:
                role = UserAssemblyRole(
                    user_id=regular.id,
                    assembly_id=existing_assembly.id,
                    role=AssemblyRole.CONFIRMATION_CALLER,
                )
                regular.assembly_roles.append(role)
                uow.commit()

        response = logged_in_user.get(f"/assemblies/{existing_assembly.id}/targets")
        assert response.status_code == 200
        assert b"Gender" in response.data
        assert b"Male" in response.data
        assert b"Add category" not in response.data
        assert b"Add value" not in response.data
