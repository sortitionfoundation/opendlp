"""ABOUTME: End-to-end tests for the backoffice respondents blueprint
ABOUTME: Tests uploading/deleting respondents, viewing the respondents page, and viewing a single respondent"""

import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.respondent_service import create_respondent, import_respondents_from_csv
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork
from tests.e2e.helpers import get_csrf_token


@pytest.fixture
def assembly_with_respondents(postgres_session_factory, admin_user):
    """Create an assembly with respondents for testing."""
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = create_assembly(
            uow=uow,
            title="Assembly with Respondents",
            created_by_user_id=admin_user.id,
            question="What is the question?",
            first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
        )
        assembly_id = assembly.id

    # Add respondents
    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        respondents = []
        for i in range(5):
            respondent = Respondent(
                assembly_id=assembly_id,
                external_id=f"test-{i}",
                attributes={"name": f"Test Person {i}", "Gender": "Male" if i % 2 == 0 else "Female"},
            )
            respondents.append(respondent)
        uow.respondents.bulk_add(respondents)
        uow.commit()

    with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
        assembly = uow.assemblies.get(assembly_id)
        return assembly.create_detached_copy()


class TestBackofficeUploadRespondents:
    """Test CSV respondent upload in backoffice respondents blueprint."""

    def test_upload_respondents_with_id_column(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Test uploading respondents CSV with a specified id_column."""
        csv_content = "name,person_id,age\nAlice,P001,30\nBob,P002,25"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents",
            data={
                "file": (BytesIO(csv_content.encode()), "respondents.csv"),
                "id_column": "person_id",
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=csv"
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "source=csv" in response.location

        # Verify respondents were created with correct external_id
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(existing_assembly.id)
            assert len(respondents) == 2
            external_ids = {r.external_id for r in respondents}
            assert external_ids == {"P001", "P002"}
            # Verify other columns became attributes
            for r in respondents:
                assert "name" in r.attributes
                assert "age" in r.attributes
                assert "person_id" not in r.attributes  # id_column should not be in attributes

    def test_upload_respondents_without_id_column_uses_first_column(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Test uploading respondents CSV without id_column uses first column as ID."""
        csv_content = "participant_id,name,city\nID001,Charlie,London\nID002,Diana,Paris"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents",
            data={
                "file": (BytesIO(csv_content.encode()), "respondents.csv"),
                "id_column": "",  # Empty means use first column
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=csv"
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

        assert response.status_code == 302

        # Verify respondents were created using first column as external_id
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(existing_assembly.id)
            assert len(respondents) == 2
            external_ids = {r.external_id for r in respondents}
            assert external_ids == {"ID001", "ID002"}
            # First column should not be in attributes
            for r in respondents:
                assert "participant_id" not in r.attributes
                assert "name" in r.attributes
                assert "city" in r.attributes

    def test_upload_respondents_with_invalid_id_column_shows_error(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
    ):
        """Test uploading respondents CSV with non-existent id_column shows error."""
        csv_content = "name,email,age\nAlice,alice@example.com,30"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents",
            data={
                "file": (BytesIO(csv_content.encode()), "respondents.csv"),
                "id_column": "nonexistent_column",
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=csv"
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert response.status_code == 200
        # Should show error message about invalid column
        assert b"nonexistent_column" in response.data or b"Invalid CSV" in response.data

    def test_upload_respondents_shows_success_message(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
    ):
        """Test that successful upload shows success flash message."""
        csv_content = "id,name\n1,Test User"

        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents",
            data={
                "file": (BytesIO(csv_content.encode()), "respondents.csv"),
                "id_column": "",
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}/data?source=csv"
                ),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"success" in response.data.lower() or b"uploaded" in response.data.lower()

    def test_upload_respondents_redirects_when_not_logged_in(
        self,
        client,
        existing_assembly: Assembly,
    ):
        """Test that unauthenticated users are redirected to login."""
        csv_content = "id,name\n1,Test"

        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents",
            data={
                "file": (BytesIO(csv_content.encode()), "respondents.csv"),
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 302
        assert "login" in response.location


class TestBackofficeDeleteRespondents:
    """Test CSV respondent deletion in backoffice respondents blueprint."""

    def test_delete_respondents_success(
        self,
        logged_in_admin,
        assembly_with_respondents: Assembly,
        postgres_session_factory,
    ):
        """Test successfully deleting respondents for an assembly."""
        # Verify respondents exist before deletion
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(assembly_with_respondents.id)
            assert len(respondents) > 0

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_respondents.id}/data/delete-respondents",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{assembly_with_respondents.id}/data?source=csv"
                ),
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert "source=csv" in response.location

        # Verify respondents were deleted
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(assembly_with_respondents.id)
            assert len(respondents) == 0

    def test_delete_respondents_shows_success_message(
        self,
        logged_in_admin,
        assembly_with_respondents: Assembly,
    ):
        """Test that successful respondents deletion shows success flash message."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_with_respondents.id}/data/delete-respondents",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin, f"/backoffice/assembly/{assembly_with_respondents.id}/data?source=csv"
                ),
            },
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert b"deleted" in response.data.lower() or b"success" in response.data.lower()


class TestBackofficeViewRespondentsPage:
    """Test backoffice respondents list page."""

    def test_view_respondents_page_with_csv_source(
        self,
        logged_in_admin,
        assembly_with_respondents: Assembly,
    ):
        """Test that respondents page loads successfully for CSV data source."""
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_with_respondents.id}/respondents")

        assert response.status_code == 200
        # Should see the page content
        assert b"Respondents" in response.data or b"respondents" in response.data.lower()

    def test_view_respondents_page_redirects_when_not_logged_in(
        self,
        client,
        assembly_with_respondents: Assembly,
    ):
        """Test that unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{assembly_with_respondents.id}/respondents")

        assert response.status_code == 302
        assert "login" in response.location

    def test_view_respondents_page_lists_each_respondent(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
        admin_user,
        postgres_session_factory,
    ):
        """Table should show external_id, email, and display name for every respondent."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = [
                Respondent(
                    assembly_id=existing_assembly.id,
                    external_id=f"R-{i:03d}",
                    email=f"person{i}@example.com",
                    attributes={"first_name": f"First{i}", "last_name": f"Last{i}"},
                )
                for i in range(3)
            ]
            uow.respondents.bulk_add(respondents)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")

        assert response.status_code == 200
        body = response.data
        for i in range(3):
            assert f"R-{i:03d}".encode() in body
            assert f"person{i}@example.com".encode() in body
            assert f"First{i} Last{i}".encode() in body

    def test_view_respondents_page_has_view_link_per_respondent(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Each row should link to the single-respondent page."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = [
                Respondent(
                    assembly_id=existing_assembly.id,
                    external_id=f"R-{i}",
                    email=f"p{i}@example.com",
                    attributes={"name": f"Person {i}"},
                )
                for i in range(2)
            ]
            uow.respondents.bulk_add(respondents)
            uow.commit()
            respondent_ids = [r.id for r in respondents]

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")

        assert response.status_code == 200
        for respondent_id in respondent_ids:
            expected = f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent_id}"
            assert expected.encode() in response.data

    def test_view_respondents_page_falls_back_to_email_local_part_when_no_name_fields(
        self,
        logged_in_admin,
        existing_assembly: Assembly,
        postgres_session_factory,
    ):
        """Display name column should show email local-part when no recognisable name attributes exist."""
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = Respondent(
                assembly_id=existing_assembly.id,
                external_id="R-EMAIL",
                email="jane.doe@example.com",
                attributes={"age": "42"},
            )
            uow.respondents.bulk_add([respondent])
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")

        assert response.status_code == 200
        assert b"jane.doe" in response.data


class TestBackofficeViewSingleRespondent:
    """Test backoffice view-single-respondent page."""

    def test_view_respondent_renders_for_admin(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R001",
                attributes={},
                email="alice@example.com",
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 200
        assert b"R001" in response.data
        assert b"alice@example.com" in response.data
        assert b"Pool" in response.data

    def test_view_respondent_requires_login(self, client, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R001",
                attributes={},
                email="alice@example.com",
            )

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_respondent_not_found(self, logged_in_admin, existing_assembly):
        bogus_id = uuid.uuid4()
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/{bogus_id}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Respondent not found" in msg for msg in flash_messages)

    def test_view_respondent_shows_generated_name_from_attributes(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R001",
                attributes={"first_name": "Sarah", "last_name": "Jones"},
                email="sarah@example.com",
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 200
        # Generated name appears in h1 and title
        assert b"Sarah Jones" in response.data
        # External id still present in the details table
        assert b"R001" in response.data

    def test_view_respondent_falls_back_to_email_local_part(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R001",
                attributes={},
                email="sarah.jones@example.com",
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 200
        # No name attributes → h1 uses email local-part
        assert b"sarah.jones" in response.data

    def test_view_respondent_renders_grouped_sections_after_csv_import(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        csv_content = (
            "external_id,first_name,last_name,gender,postcode,custom_notes\n"
            "R001,Alice,Jones,Female,SW1A 1AA,extra-info\n"
        )
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(uow, admin_user.id, existing_assembly.id, csv_content)
            respondent = uow.respondents.get_by_external_id(existing_assembly.id, "R001")
            assert respondent is not None
            respondent_id = respondent.id

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent_id}")
        assert response.status_code == 200
        body = response.data
        # Status block: external_id and selection status tag.
        assert b"R001" in body
        assert b"govuk-tag" in body
        # Schema-driven group headings are present.
        assert b"Name and contact" in body
        assert b"About you" in body
        assert b"Address" in body
        # Non-fixed values render via attributes lookup.
        assert b"Alice" in body
        assert b"Jones" in body
        assert b"Female" in body
        assert b"SW1A 1AA" in body
        assert b"extra-info" in body
        # Audit block sits in a collapsed details element.
        assert b"Record metadata" in body
        assert b"<details" in body

    def test_view_respondent_wrong_assembly(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            other_assembly = create_assembly(
                uow=uow,
                title="Other Assembly",
                created_by_user_id=admin_user.id,
                question="Other?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            other_id = other_assembly.id

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                other_id,
                external_id="R-OTHER",
                attributes={},
            )

        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Respondent not found" in msg for msg in flash_messages)
