"""ABOUTME: End-to-end tests for the backoffice respondents blueprint
ABOUTME: Tests uploading/deleting respondents, viewing the respondents page, and viewing a single respondent"""

import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest

from opendlp import config as _config
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.respondent_field_schema_service import get_schema, initialise_empty_schema
from opendlp.service_layer.respondent_service import create_respondent, delete_respondent, import_respondents_from_csv
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


class TestUploadDiffConfirmation:
    """Test the schema-diff confirmation flow on CSV re-upload."""

    def _upload(self, client, assembly_id, csv_text, filename="respondents.csv"):
        return client.post(
            f"/backoffice/assembly/{assembly_id}/data/upload-respondents",
            data={
                "file": (BytesIO(csv_text.encode()), filename),
                "id_column": "",
                "csrf_token": get_csrf_token(client, f"/backoffice/assembly/{assembly_id}/data?source=csv"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )

    def test_first_upload_imports_directly_no_diff_page(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        """An assembly with no schema yet skips the diff page entirely."""
        response = self._upload(
            logged_in_admin,
            existing_assembly.id,
            "external_id,first_name\nR001,Alice\n",
        )
        assert response.status_code == 302
        # Goes back to data tab, not the confirm-diff page.
        assert "confirm-diff" not in response.location
        assert "source=csv" in response.location

    def test_re_upload_with_unchanged_columns_skips_diff(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        """If the new CSV has identical columns the diff is empty so no confirmation."""
        self._upload(logged_in_admin, existing_assembly.id, "external_id,first_name\nR001,Alice\n")
        response = self._upload(logged_in_admin, existing_assembly.id, "external_id,first_name\nR002,Bob\n")
        assert response.status_code == 302
        assert "confirm-diff" not in response.location

    def test_re_upload_with_added_column_redirects_to_diff_page(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        self._upload(logged_in_admin, existing_assembly.id, "external_id,first_name\nR001,Alice\n")
        response = self._upload(
            logged_in_admin,
            existing_assembly.id,
            "external_id,first_name,postcode\nR002,Bob,SW1\n",
        )
        assert response.status_code == 303
        assert "confirm-diff" in response.location

    def test_diff_page_shows_added_and_absent_columns(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        self._upload(
            logged_in_admin,
            existing_assembly.id,
            "external_id,first_name,city\nR001,Alice,London\n",
        )
        # Re-upload: drop city, add postcode.
        self._upload(
            logged_in_admin,
            existing_assembly.id,
            "external_id,first_name,postcode\nR002,Bob,SW1\n",
        )
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents/confirm-diff"
        )
        assert response.status_code == 200
        body = response.data
        assert b"New columns" in body
        assert b"postcode" in body
        assert b"Columns no longer in CSV" in body
        assert b"city" in body

    def test_confirm_applies_import_and_extends_schema(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        self._upload(logged_in_admin, existing_assembly.id, "external_id,first_name\nR001,Alice\n")
        self._upload(
            logged_in_admin,
            existing_assembly.id,
            "external_id,first_name,postcode\nR002,Bob,SW1\n",
        )

        confirm_response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents/confirm-diff",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents/confirm-diff",
                ),
                "action": "confirm",
            },
            follow_redirects=False,
        )
        assert confirm_response.status_code == 302
        assert "source=csv" in confirm_response.location

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(existing_assembly.id)
            assert {r.external_id for r in respondents} == {"R002"}

            admin_id = next(u.id for u in uow.users.all() if u.global_role.value == "admin")
            schema = get_schema(uow, admin_id, existing_assembly.id)
            assert "postcode" in {f.field_key for f in schema}

    def test_cancel_discards_pending_upload_and_does_not_import(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        # Seed: one respondent in DB.
        self._upload(logged_in_admin, existing_assembly.id, "external_id,first_name\nR001,Alice\n")
        # Re-upload with a new column → pending diff.
        self._upload(
            logged_in_admin,
            existing_assembly.id,
            "external_id,first_name,postcode\nR999,Cancelled,XX\n",
        )

        cancel_response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents/confirm-diff",
            data={
                "csrf_token": get_csrf_token(
                    logged_in_admin,
                    f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents/confirm-diff",
                ),
                "action": "cancel",
            },
            follow_redirects=False,
        )
        assert cancel_response.status_code == 302
        assert "confirm-diff" not in cancel_response.location

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondents = uow.respondents.get_by_assembly_id(existing_assembly.id)
            assert {r.external_id for r in respondents} == {"R001"}

    def test_confirm_diff_after_session_expiry_redirects_with_warning(
        self, logged_in_admin, existing_assembly, postgres_session_factory
    ):
        # No prior upload — visiting the confirm page should redirect.
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents/confirm-diff",
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "source=csv" in response.location

    def test_oversized_upload_is_rejected_with_friendly_error(self, logged_in_admin, existing_assembly, monkeypatch):
        # Force the limit to 1 byte so a tiny CSV trips it.
        monkeypatch.setenv("MAX_CSV_UPLOAD_MB", "1")
        # Patch the per-request bytes lookup so the route enforces the override.
        monkeypatch.setattr(_config, "get_max_csv_upload_bytes", lambda: 1)
        monkeypatch.setattr(
            "opendlp.entrypoints.blueprints.respondents.get_max_csv_upload_bytes",
            lambda: 1,
        )

        response = self._upload(
            logged_in_admin,
            existing_assembly.id,
            "external_id,first_name\nR001,Alice\n",
        )
        # Friendly redirect-with-flash, not a raw 413.
        assert response.status_code == 302
        with logged_in_admin.session_transaction() as session:
            messages = [msg[1] for msg in session.get("_flashes", [])]
        assert any("too large" in m.lower() for m in messages)


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


class TestViewRespondentDeletionUI:
    """The delete form and DELETED banner on the single-respondent page."""

    def test_admin_sees_delete_form(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-DEL",
                attributes={},
                email="x@example.com",
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 200
        assert b"Delete personal data" in response.data

    def test_deleted_respondent_shows_banner_and_comment_list(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-DEAD",
                attributes={"Gender": "Female"},
                email="x@example.com",
            )

        # Delete it via the service so the comment is real
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            delete_respondent(uow, admin_user.id, existing_assembly.id, respondent.id, comment="gdpr")

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 200
        # Banner
        assert b"Personal data deleted" in response.data
        # Comment list row with text
        assert b"gdpr" in response.data
        # Form should not render for DELETED respondents
        assert b"Confirm delete" not in response.data


class TestDeleteRespondentRoute:
    """POST /backoffice/assembly/<id>/respondents/<id>/delete"""

    def _delete_url(self, assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}/delete"

    def _view_url(self, assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}"

    def test_admin_can_delete_with_comment(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-DEL",
                attributes={"Gender": "Female"},
                email="alice@example.com",
            )

        response = logged_in_admin.post(
            self._delete_url(existing_assembly.id, respondent.id),
            data={
                "comment": "gdpr request",
                "csrf_token": get_csrf_token(logged_in_admin, self._view_url(existing_assembly.id, respondent.id)),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert f"/backoffice/assembly/{existing_assembly.id}/respondents" in response.location

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            reloaded = uow.respondents.get(respondent.id)
            assert reloaded is not None
            assert reloaded.selection_status.value == "DELETED"
            assert reloaded.email == ""
            assert reloaded.attributes == {"Gender": ""}
            assert len(reloaded.comments) == 1
            assert reloaded.comments[0].text == "gdpr request"

    def test_missing_comment_rejected(self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-KEEP",
                attributes={},
                email="keep@example.com",
            )

        response = logged_in_admin.post(
            self._delete_url(existing_assembly.id, respondent.id),
            data={
                "comment": "",
                "csrf_token": get_csrf_token(logged_in_admin, self._view_url(existing_assembly.id, respondent.id)),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            reloaded = uow.respondents.get(respondent.id)
            assert reloaded is not None
            assert reloaded.selection_status.value == "POOL"
            assert reloaded.email == "keep@example.com"
            assert len(reloaded.comments) == 0

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("comment is required" in msg.lower() for msg in flash_messages)

    def test_requires_login(self, client, existing_assembly, admin_user, postgres_session_factory):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-NOLOGIN",
                attributes={},
            )

        response = client.post(
            self._delete_url(existing_assembly.id, respondent.id),
            data={"comment": "gdpr"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "login" in response.location

    def test_respondent_in_other_assembly(
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

        response = logged_in_admin.post(
            self._delete_url(existing_assembly.id, respondent.id),
            data={
                "comment": "gdpr",
                "csrf_token": get_csrf_token(logged_in_admin, f"/backoffice/assembly/{existing_assembly.id}"),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
            assert any("Respondent not found" in msg for msg in flash_messages)


class TestSelectionStatusTransition:
    """Transition buttons + POST /.../transition-status."""

    def _transition_url(self, assembly_id, respondent_id):
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}/transition-status"

    def _view_url(self, assembly_id, respondent_id):
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}"

    def test_view_page_shows_buttons_for_each_allowed_transition(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            resp = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-T1",
                attributes={},
                selection_status=RespondentStatus.SELECTED,
            )
        response = logged_in_admin.get(self._view_url(existing_assembly.id, resp.id))
        assert response.status_code == 200
        assert b"CONFIRMED" in response.data
        assert b"WITHDRAWN" in response.data

    def test_view_page_hides_buttons_on_terminal_status(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            resp = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-T2",
                attributes={},
                selection_status=RespondentStatus.WITHDRAWN,
            )
        response = logged_in_admin.get(self._view_url(existing_assembly.id, resp.id))
        assert response.status_code == 200
        # No "Change to" buttons (no allowed transitions)
        assert b"Change to" not in response.data

    def test_post_valid_transition_updates_and_flashes(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            resp = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-T3",
                attributes={},
                selection_status=RespondentStatus.SELECTED,
            )

        response = logged_in_admin.post(
            self._transition_url(existing_assembly.id, resp.id),
            data={
                "new_status": RespondentStatus.CONFIRMED.value,
                "comment": "confirmed on call",
                "csrf_token": get_csrf_token(logged_in_admin, self._view_url(existing_assembly.id, resp.id)),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            retrieved = uow.respondents.get(resp.id)
            assert retrieved.selection_status == RespondentStatus.CONFIRMED

    def test_post_blank_comment_rejected(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            resp = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-T4",
                attributes={},
                selection_status=RespondentStatus.SELECTED,
            )

        response = logged_in_admin.post(
            self._transition_url(existing_assembly.id, resp.id),
            data={
                "new_status": RespondentStatus.CONFIRMED.value,
                "comment": "",
                "csrf_token": get_csrf_token(logged_in_admin, self._view_url(existing_assembly.id, resp.id)),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            retrieved = uow.respondents.get(resp.id)
            assert retrieved.selection_status == RespondentStatus.SELECTED

    def test_post_illegal_transition_rejected(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):

        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            resp = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-T5",
                attributes={},
                selection_status=RespondentStatus.POOL,
            )

        response = logged_in_admin.post(
            self._transition_url(existing_assembly.id, resp.id),
            data={
                "new_status": RespondentStatus.CONFIRMED.value,
                "comment": "try",
                "csrf_token": get_csrf_token(logged_in_admin, self._view_url(existing_assembly.id, resp.id)),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            retrieved = uow.respondents.get(resp.id)
            assert retrieved.selection_status == RespondentStatus.POOL


class TestEditRespondentPage:
    """GET /backoffice/assembly/<id>/respondents/<id>/edit and POST handling."""

    def _edit_url(self, assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}/edit"

    def _view_url(self, assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}"

    def _make_respondent(self, uow, admin_user_id, assembly_id, **kwargs):
        initialise_empty_schema(uow, admin_user_id, assembly_id)
        return create_respondent(
            uow,
            admin_user_id,
            assembly_id,
            external_id=kwargs.pop("external_id", "R-EDIT"),
            attributes=kwargs.pop("attributes", {"note": "original"}),
            email=kwargs.pop("email", "r@example.com"),
            **kwargs,
        )

    def test_get_renders_form_grouped_by_schema(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            import_respondents_from_csv(
                uow,
                admin_user.id,
                existing_assembly.id,
                "external_id,first_name,note\nR1,Alice,orig\n",
                replace_existing=True,
            )
            resp = next(iter(uow.respondents.get_by_assembly_id(existing_assembly.id)))
            resp_id = resp.id

        response = logged_in_admin.get(self._edit_url(existing_assembly.id, resp_id))
        assert response.status_code == 200
        assert b"Edit respondent" in response.data
        assert b"Change note" in response.data
        assert b"first_name" in response.data or b"First name" in response.data

    def test_post_valid_updates_redirects_and_flashes(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = self._make_respondent(uow, admin_user.id, existing_assembly.id)
            resp_id = respondent.id

        response = logged_in_admin.post(
            self._edit_url(existing_assembly.id, resp_id),
            data={
                "email": "new@example.com",
                "comment": "corrected email",
                "csrf_token": get_csrf_token(logged_in_admin, self._edit_url(existing_assembly.id, resp_id)),
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            retrieved = uow.respondents.get(resp_id)
            assert retrieved is not None
            assert retrieved.email == "new@example.com"
            assert any(c.text == "corrected email" for c in retrieved.comments)

    def test_post_blank_comment_rerenders_with_error(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = self._make_respondent(uow, admin_user.id, existing_assembly.id)
            resp_id = respondent.id

        response = logged_in_admin.post(
            self._edit_url(existing_assembly.id, resp_id),
            data={
                "email": "other@example.com",
                "comment": "",
                "csrf_token": get_csrf_token(logged_in_admin, self._edit_url(existing_assembly.id, resp_id)),
            },
            follow_redirects=False,
        )
        # Re-renders form (200), email unchanged.
        assert response.status_code == 200
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            retrieved = uow.respondents.get(resp_id)
            assert retrieved is not None
            assert retrieved.email == "r@example.com"

    def test_refused_for_deleted_respondent(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = self._make_respondent(uow, admin_user.id, existing_assembly.id)
            resp_id = respondent.id
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            delete_respondent(uow, admin_user.id, existing_assembly.id, resp_id, comment="gdpr")

        response = logged_in_admin.get(self._edit_url(existing_assembly.id, resp_id), follow_redirects=False)
        assert response.status_code == 302
        assert self._view_url(existing_assembly.id, resp_id) in response.location

    def test_view_page_shows_edit_button(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            respondent = self._make_respondent(uow, admin_user.id, existing_assembly.id)
            resp_id = respondent.id
        response = logged_in_admin.get(self._view_url(existing_assembly.id, resp_id))
        assert response.status_code == 200
        assert b"/edit" in response.data

    def test_list_page_shows_edit_link_for_each_row(
        self, logged_in_admin, existing_assembly, admin_user, postgres_session_factory
    ):
        with SqlAlchemyUnitOfWork(postgres_session_factory) as uow:
            self._make_respondent(uow, admin_user.id, existing_assembly.id)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"Edit" in response.data
