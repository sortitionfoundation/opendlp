"""ABOUTME: End-to-end tests for the targets blueprint CSV upload pages
ABOUTME: Tests viewing targets tab, uploading CSV files, and error handling"""

import io

from opendlp.service_layer.assembly_service import import_targets_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token

VALID_TARGETS_CSV = b"feature,value,min,max\nGender,Male,3,7\nGender,Female,3,7\n"

INVALID_TARGETS_CSV = b"feature,value,min,max\nGender,Male,15,5\n"


class TestViewTargetsPage:
    def test_get_targets_page_renders(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/targets")
        assert response.status_code == 200
        assert b"Targets" in response.data
        assert b"Import Target Categories from CSV" in response.data

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

        # Verify old targets were replaced automatically
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

        # Re-upload with the same feature name — exercises the unique constraint
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
