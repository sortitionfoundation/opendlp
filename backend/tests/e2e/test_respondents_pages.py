"""ABOUTME: End-to-end tests for the respondents blueprint CSV upload pages
ABOUTME: Tests viewing respondents tab, uploading CSV files, pagination, and error handling"""

import io

from opendlp.service_layer.assembly_service import update_csv_config
from opendlp.service_layer.respondent_service import import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token

VALID_RESPONDENTS_CSV = (
    b"external_id,email,name,age,gender,consent,eligible\n"
    b"R001,alice@example.com,Alice Smith,34,Female,true,true\n"
    b"R002,bob@example.com,Bob Jones,45,Male,true,true\n"
    b"R003,carol@example.com,Carol White,28,Non-binary,true,true\n"
)


def _import_many_respondents(postgres_session_factory, admin_user, assembly_id, count=60):
    """Helper to import many respondents for pagination testing."""
    rows = ["external_id,email,consent,eligible"]
    for i in range(count):
        rows.append(f"R{i:04d},user{i}@example.com,true,true")
    csv_content = "\n".join(rows)

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        respondents, errors = import_respondents_from_csv(
            uow=uow,
            user_id=admin_user.id,
            assembly_id=assembly_id,
            csv_content=csv_content,
        )
    return respondents


class TestViewRespondentsPage:
    def test_get_respondents_page_renders(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"Respondents" in response.data
        assert b"Import Respondents from CSV" in response.data

    def test_get_respondents_page_shows_empty_state(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"No respondents imported yet" in response.data

    def test_get_respondents_page_shows_summary_stats(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = (
            "external_id,email,consent,eligible\nR001,alice@example.com,true,true\nR002,bob@example.com,true,true\n"
        )
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"Total respondents" in response.data
        assert b"Available for selection" in response.data

    def test_get_respondents_page_shows_import_metadata(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "external_id,email\nR001,a@b.com\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            update_csv_config(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                last_import_filename="test_import.csv",
            )

        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"Last import file" in response.data
        assert b"test_import.csv" in response.data

    def test_get_respondents_page_shows_respondent_table(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "external_id,email,consent,eligible\nR001,alice@example.com,true,true\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"R001" in response.data
        assert b"alice@example.com" in response.data

    def test_get_respondents_page_pagination(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        _import_many_respondents(postgres_session_factory, admin_user, existing_assembly.id, count=60)

        response_page1 = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents?page=1")
        assert response_page1.status_code == 200
        assert b"Showing 1 to 50 of 60 respondents" in response_page1.data
        assert b"Next" in response_page1.data

        response_page2 = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents?page=2")
        assert response_page2.status_code == 200
        assert b"Showing 51 to 60 of 60 respondents" in response_page2.data
        assert b"Previous" in response_page2.data

    def test_get_respondents_page_requires_login(self, client, existing_assembly):
        response = client.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert response.status_code == 302
        assert "login" in response.location

    def test_get_respondents_page_prefills_id_column(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            update_csv_config(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                id_column="participant_id",
            )

        response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"participant_id" in response.data


class TestUploadRespondentsCsv:
    def test_upload_valid_csv_creates_respondents(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/respondents/upload",
            data={
                "csv_file": (io.BytesIO(VALID_RESPONDENTS_CSV), "respondents.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/respondents"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/assemblies/{existing_assembly.id}/respondents" in response.location

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Successfully imported" in msg for msg in flash_messages)

    def test_upload_with_replace_existing(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "external_id,email\nOLD001,old@example.com\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )

        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/respondents/upload",
            data={
                "csv_file": (io.BytesIO(VALID_RESPONDENTS_CSV), "new.csv"),
                "replace_existing": "y",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/respondents"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        page_response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert b"R001" in page_response.data
        assert b"OLD001" not in page_response.data

    def test_upload_with_duplicate_rows_shows_warning(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = "external_id,email\nDUP001,dup@example.com\n"
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow=uow,
                user_id=admin_user.id,
                assembly_id=existing_assembly.id,
                csv_content=csv_content,
            )

        csv_with_dup = b"external_id,email\nDUP001,dup@example.com\nNEW001,new@example.com\n"
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/respondents/upload",
            data={
                "csv_file": (io.BytesIO(csv_with_dup), "with_dups.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/respondents"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("rows were skipped" in msg for msg in flash_messages)

    def test_upload_updates_csv_config(self, logged_in_admin, existing_assembly, postgres_session_factory):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/respondents/upload",
            data={
                "csv_file": (io.BytesIO(VALID_RESPONDENTS_CSV), "my_data.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/respondents"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        page_response = logged_in_admin.get(f"/assemblies/{existing_assembly.id}/respondents")
        assert b"my_data.csv" in page_response.data

    def test_upload_no_file_shows_validation_error(self, logged_in_admin, existing_assembly):
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/respondents/upload",
            data={
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/respondents"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert b"There is a problem" in response.data

    def test_upload_with_custom_id_column(self, logged_in_admin, existing_assembly):
        csv_data = b"participant_id,email\nP001,alice@example.com\nP002,bob@example.com\n"
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/respondents/upload",
            data={
                "csv_file": (io.BytesIO(csv_data), "custom_id.csv"),
                "id_column": "participant_id",
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/respondents"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Successfully imported" in msg for msg in flash_messages)

    def test_upload_csv_missing_id_column_shows_error(self, logged_in_admin, existing_assembly):
        csv_data = b"name,email\nAlice,alice@example.com\n"
        response = logged_in_admin.post(
            f"/assemblies/{existing_assembly.id}/respondents/upload",
            data={
                "csv_file": (io.BytesIO(csv_data), "missing_id.csv"),
                "csrf_token": get_csrf_token(logged_in_admin, f"/assemblies/{existing_assembly.id}/respondents"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert response.status_code == 302

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("CSV import failed" in msg for msg in flash_messages)
