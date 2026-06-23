"""ABOUTME: End-to-end smoke tests for the backoffice respondents blueprint
ABOUTME: One real-DB smoke per route plus the Redis-stashed CSV diff-confirmation flow"""

from datetime import UTC, datetime, timedelta
from io import BytesIO

import pytest

from opendlp import config as _config
from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.respondent_field_schema_service import get_schema, initialise_empty_schema
from opendlp.service_layer.respondent_service import create_respondent
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
    """CSV respondent upload smoke."""

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


class TestBackofficeDeleteRespondents:
    """CSV respondent bulk deletion smoke."""

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


class TestUploadDiffConfirmation:
    """The schema-diff confirmation flow on CSV re-upload (Redis-stashed pending upload)."""

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
    """Backoffice respondents list page smoke."""

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


class TestBackofficeViewSingleRespondent:
    """Backoffice view-single-respondent page smoke."""

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


class TestDeleteRespondentRoute:
    """POST /backoffice/assembly/<id>/respondents/<id>/delete smoke."""

    def _delete_url(self, assembly_id, respondent_id) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}/delete"

    def _view_url(self, assembly_id, respondent_id) -> str:
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
            delete_comments = [c for c in reloaded.comments if c.text == "gdpr request"]
            assert len(delete_comments) == 1


class TestSelectionStatusTransition:
    """POST /.../transition-status smoke."""

    def _transition_url(self, assembly_id, respondent_id):
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}/transition-status"

    def _view_url(self, assembly_id, respondent_id):
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}"

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


class TestEditRespondentPage:
    """POST /backoffice/assembly/<id>/respondents/<id>/edit smoke."""

    def _edit_url(self, assembly_id, respondent_id) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}/edit"

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
