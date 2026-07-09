# ABOUTME: Component tests for the backoffice respondents blueprint over a FakeUnitOfWork
# ABOUTME: Drives the real respondents Flask routes + services against a seeded fake store, no PostgreSQL

import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO

from flask.testing import FlaskClient

from opendlp.domain.assembly import Assembly
from opendlp.domain.respondents import Respondent
from opendlp.domain.value_objects import RespondentStatus
from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.respondent_field_schema_service import initialise_empty_schema
from opendlp.service_layer.respondent_service import (
    create_respondent,
    delete_respondent,
    import_respondents_from_csv,
)
from tests.fakes import FakeStore, FakeUnitOfWork


def _upload(client, assembly_id, csv_text, id_column="", filename="respondents.csv"):
    """POST a CSV upload to the respondents upload route."""
    return client.post(
        f"/backoffice/assembly/{assembly_id}/data/upload-respondents",
        data={
            "file": (BytesIO(csv_text.encode()), filename),
            "id_column": id_column,
        },
        content_type="multipart/form-data",
        follow_redirects=False,
    )


class TestBackofficeUploadRespondents:
    """CSV respondent upload branches."""

    def test_upload_without_id_column_uses_first_column(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """An empty id_column means the first CSV column is used as external_id."""
        response = _upload(
            logged_in_admin,
            existing_assembly.id,
            "participant_id,name,city\nID001,Charlie,London\nID002,Diana,Paris",
        )
        assert response.status_code == 302

        with FakeUnitOfWork(store=fake_store) as uow:
            respondents = uow.respondents.get_by_assembly_id(existing_assembly.id)
            assert {r.external_id for r in respondents} == {"ID001", "ID002"}
            for r in respondents:
                assert "participant_id" not in r.attributes
                assert "name" in r.attributes
                assert "city" in r.attributes

    def test_upload_with_invalid_id_column_shows_error(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """A non-existent id_column shows an error and imports nothing."""
        response = _upload(
            logged_in_admin,
            existing_assembly.id,
            "name,email,age\nAlice,alice@example.com,30",
            id_column="nonexistent_column",
        )
        assert response.status_code == 302

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondents.count_by_assembly_id(existing_assembly.id) == 0

    def test_upload_shows_success_message(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """A successful upload flashes a success message."""
        _upload(logged_in_admin, existing_assembly.id, "id,name\n1,Test User")
        with logged_in_admin.session_transaction() as session:
            messages = [msg[1].lower() for msg in session.get("_flashes", [])]
        assert any("success" in m or "uploaded" in m for m in messages)

    def test_upload_with_warnings_lists_each_error_in_flash(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """A partial import flashes the summary plus one line per skipped row."""
        _upload(
            logged_in_admin,
            existing_assembly.id,
            "id,name\nID001,Alice\nID001,Bob\n,Carol",
        )
        with logged_in_admin.session_transaction() as session:
            warnings = [msg[1] for msg in session.get("_flashes", []) if msg[0] == "warning"]
        assert len(warnings) == 1
        message = warnings[0]
        # Row 3 is the duplicate ID001 (row 2 is the first ID001); row 4 is empty.
        assert "Row 3: skipped duplicate id: ID001" in message
        assert "Row 4: skipped, empty id" in message
        # Each error sits on its own line, separated from the summary by <br>.
        assert message.count("<br>") == 2

    def test_upload_with_many_warnings_caps_flash_lines(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """The flash lists at most 20 errors plus an 'and N more' line."""
        # One valid row followed by 25 duplicates of it, so 25 rows are skipped.
        rows = "\n".join(["id,name", "ID001,Alice"] + [f"ID001,Dup{i}" for i in range(25)])
        _upload(logged_in_admin, existing_assembly.id, rows)
        with logged_in_admin.session_transaction() as session:
            warnings = [msg[1] for msg in session.get("_flashes", []) if msg[0] == "warning"]
        assert len(warnings) == 1
        message = warnings[0]
        # Summary + 20 capped error lines + the "and N more" line = 21 <br> separators.
        assert message.count("<br>") == 21
        assert "and 5 more" in message

    def test_upload_redirects_when_not_logged_in(self, client: FlaskClient, existing_assembly: Assembly) -> None:
        """Unauthenticated users are redirected to login."""
        response = client.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/upload-respondents",
            data={"file": (BytesIO(b"id,name\n1,Test"), "respondents.csv")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 302
        assert "login" in response.location


class TestBackofficeDeleteRespondents:
    """Bulk delete-respondents branches."""

    def test_delete_respondents_shows_success_message(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """Deleting respondents flashes a success message."""
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.respondents.bulk_add([
                Respondent(assembly_id=existing_assembly.id, external_id=f"R-{i}", attributes={}) for i in range(3)
            ])
            uow.commit()

        logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/data/delete-respondents",
            follow_redirects=False,
        )
        with logged_in_admin.session_transaction() as session:
            messages = [msg[1].lower() for msg in session.get("_flashes", [])]
        assert any("deleted" in m or "success" in m for m in messages)

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondents.count_by_assembly_id(existing_assembly.id) == 0


class TestUploadDiffConfirmation:
    """Schema-diff confirmation flow on CSV re-upload."""

    def test_first_upload_imports_directly_no_diff_page(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """An assembly with no schema yet skips the diff page."""
        response = _upload(logged_in_admin, existing_assembly.id, "external_id,first_name\nR001,Alice\n")
        assert response.status_code == 302
        assert "confirm-diff" not in response.location
        assert "source=csv" in response.location

    def test_re_upload_with_unchanged_columns_skips_diff(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Identical columns mean an empty diff so no confirmation page."""
        _upload(logged_in_admin, existing_assembly.id, "external_id,first_name\nR001,Alice\n")
        response = _upload(logged_in_admin, existing_assembly.id, "external_id,first_name\nR002,Bob\n")
        assert response.status_code == 302
        assert "confirm-diff" not in response.location


class TestBackofficeViewRespondentsPage:
    """The respondents list page render variants."""

    def test_view_respondents_page_redirects_when_not_logged_in(
        self, client: FlaskClient, existing_assembly: Assembly
    ) -> None:
        """Unauthenticated users are redirected to login."""
        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_respondents_page_lists_each_respondent(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """The table shows external_id, email, and display name for each respondent."""
        with FakeUnitOfWork(store=fake_store) as uow:
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
            uow.assemblies.get(existing_assembly.id).respondents = respondents
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        body = response.data
        for i in range(3):
            assert f"R-{i:03d}".encode() in body
            assert f"person{i}@example.com".encode() in body
            assert f"First{i} Last{i}".encode() in body

    def test_view_respondents_page_has_view_link_per_respondent(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """Each row links to the single-respondent page."""
        with FakeUnitOfWork(store=fake_store) as uow:
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
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, fake_store: FakeStore
    ) -> None:
        """The display name falls back to the email local-part with no name attributes."""
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.respondents.bulk_add([
                Respondent(
                    assembly_id=existing_assembly.id,
                    external_id="R-EMAIL",
                    email="jane.doe@example.com",
                    attributes={"age": "42"},
                )
            ])
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"jane.doe" in response.data


class TestBackofficeViewSingleRespondent:
    """The single-respondent page name-derivation, grouping, and not-found branches."""

    def test_view_respondent_requires_login(
        self, client: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """Unauthenticated users are redirected to login."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(
                uow, admin_user.id, existing_assembly.id, external_id="R001", attributes={}, email="alice@example.com"
            )

        response = client.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 302
        assert "login" in response.location

    def test_view_respondent_not_found(self, logged_in_admin: FlaskClient, existing_assembly: Assembly) -> None:
        """An unknown respondent flashes not-found and redirects."""
        response = logged_in_admin.get(
            f"/backoffice/assembly/{existing_assembly.id}/respondents/{uuid.uuid4()}",
            follow_redirects=False,
        )
        assert response.status_code == 302
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
        assert any("Respondent not found" in msg for msg in flash_messages)

    def test_view_respondent_shows_generated_name_from_attributes(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """The h1/title use the generated name from name attributes."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R001",
                attributes={"first_name": "Sarah", "last_name": "Jones"},
                email="sarah@example.com",
            )
            uow.assemblies.get(existing_assembly.id).respondents = [respondent]
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 200
        assert b"Sarah Jones" in response.data
        assert b"R001" in response.data

    def test_view_respondent_falls_back_to_email_local_part(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """With no name attributes the h1 uses the email local-part."""
        with FakeUnitOfWork(store=fake_store) as uow:
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
        assert b"sarah.jones" in response.data

    def test_view_respondent_renders_grouped_sections_after_csv_import(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """Schema-driven group headings and attribute values render after a CSV import."""
        csv_content = (
            "external_id,first_name,last_name,gender,postcode,custom_notes\n"
            "R001,Alice,Jones,Female,SW1A 1AA,extra-info\n"
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            import_respondents_from_csv(uow, admin_user.id, existing_assembly.id, csv_content)
            respondent = uow.respondents.get_by_external_id(existing_assembly.id, "R001")
            assert respondent is not None
            respondent_id = respondent.id

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent_id}")
        assert response.status_code == 200
        body = response.data
        assert b"R001" in body
        assert b"govuk-tag" in body
        assert b"Name and contact" in body
        assert b"About you" in body
        assert b"Address" in body
        assert b"Alice" in body
        assert b"Jones" in body
        assert b"Female" in body
        assert b"SW1A 1AA" in body
        assert b"extra-info" in body
        assert b"Activity" in body
        assert b"<details" in body

    def test_view_respondent_wrong_assembly(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """A respondent in a different assembly flashes not-found."""
        with FakeUnitOfWork(store=fake_store) as uow:
            other_assembly = create_assembly(
                uow=uow,
                title="Other Assembly",
                created_by_user_id=admin_user.id,
                question="Other?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            other_id = other_assembly.id
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(uow, admin_user.id, other_id, external_id="R-OTHER", attributes={})

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

    def test_admin_sees_delete_form(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """Admins see the delete-personal-data form."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(
                uow, admin_user.id, existing_assembly.id, external_id="R-DEL", attributes={}, email="x@example.com"
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 200
        assert b"Delete personal data" in response.data

    def test_deleted_respondent_shows_banner_and_comment_list(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """A DELETED respondent shows the banner and comment, and hides the form."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-DEAD",
                attributes={"Gender": "Female"},
                email="x@example.com",
            )
        with FakeUnitOfWork(store=fake_store) as uow:
            delete_respondent(uow, admin_user.id, existing_assembly.id, respondent.id, comment="gdpr")

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents/{respondent.id}")
        assert response.status_code == 200
        assert b"Personal data deleted" in response.data
        assert b"gdpr" in response.data
        assert b"Confirm delete" not in response.data


class TestDeleteRespondentRoute:
    """POST /backoffice/assembly/<id>/respondents/<id>/delete branches."""

    def _delete_url(self, assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}/delete"

    def test_missing_comment_rejected(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """A blank comment is rejected and the respondent stays in POOL."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(
                uow, admin_user.id, existing_assembly.id, external_id="R-KEEP", attributes={}, email="keep@example.com"
            )

        response = logged_in_admin.post(
            self._delete_url(existing_assembly.id, respondent.id),
            data={"comment": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with FakeUnitOfWork(store=fake_store) as uow:
            reloaded = uow.respondents.get(respondent.id)
            assert reloaded is not None
            assert reloaded.selection_status == RespondentStatus.POOL
            assert reloaded.email == "keep@example.com"
            assert all(c.action.value != "DELETE" for c in reloaded.comments)

        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
        assert any("comment is required" in msg.lower() for msg in flash_messages)

    def test_requires_login(
        self, client: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """Unauthenticated delete is redirected to login."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(
                uow, admin_user.id, existing_assembly.id, external_id="R-NOLOGIN", attributes={}
            )

        response = client.post(
            self._delete_url(existing_assembly.id, respondent.id),
            data={"comment": "gdpr"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "login" in response.location

    def test_respondent_in_other_assembly(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """Deleting a respondent from another assembly flashes not-found."""
        with FakeUnitOfWork(store=fake_store) as uow:
            other_assembly = create_assembly(
                uow=uow,
                title="Other Assembly",
                created_by_user_id=admin_user.id,
                question="Other?",
                first_assembly_date=(datetime.now(UTC).date() + timedelta(days=30)),
            )
            other_id = other_assembly.id
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(uow, admin_user.id, other_id, external_id="R-OTHER", attributes={})

        response = logged_in_admin.post(
            self._delete_url(existing_assembly.id, respondent.id),
            data={"comment": "gdpr"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with logged_in_admin.session_transaction() as session:
            flash_messages = [msg[1] for msg in session.get("_flashes", [])]
        assert any("Respondent not found" in msg for msg in flash_messages)


class TestSelectionStatusTransition:
    """Transition button render + POST validation branches."""

    def _transition_url(self, assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}/transition-status"

    def _view_url(self, assembly_id: uuid.UUID, respondent_id: uuid.UUID) -> str:
        return f"/backoffice/assembly/{assembly_id}/respondents/{respondent_id}"

    def test_view_page_shows_buttons_for_each_allowed_transition(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """An active status shows its allowed transition buttons."""
        with FakeUnitOfWork(store=fake_store) as uow:
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
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """A DELETED (terminal) status renders no transition buttons."""
        with FakeUnitOfWork(store=fake_store) as uow:
            resp = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-T2",
                attributes={},
                selection_status=RespondentStatus.DELETED,
            )

        response = logged_in_admin.get(self._view_url(existing_assembly.id, resp.id))
        assert response.status_code == 200
        assert b"Change to" not in response.data

    def test_post_blank_comment_rejected(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """A blank comment leaves the status unchanged."""
        with FakeUnitOfWork(store=fake_store) as uow:
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
            data={"new_status": RespondentStatus.CONFIRMED.value, "comment": ""},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondents.get(resp.id).selection_status == RespondentStatus.SELECTED

    def test_post_illegal_transition_rejected(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """An illegal transition (into DELETED) leaves the status unchanged."""
        with FakeUnitOfWork(store=fake_store) as uow:
            resp = create_respondent(
                uow,
                admin_user.id,
                existing_assembly.id,
                external_id="R-T5",
                attributes={},
                selection_status=RespondentStatus.SELECTED,
            )

        response = logged_in_admin.post(
            self._transition_url(existing_assembly.id, resp.id),
            data={"new_status": RespondentStatus.DELETED.value, "comment": "try"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondents.get(resp.id).selection_status == RespondentStatus.SELECTED


class TestEditRespondentPage:
    """GET/POST edit form and validation branches."""

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
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """The edit form renders schema-grouped fields and the status form."""
        with FakeUnitOfWork(store=fake_store) as uow:
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
        assert b"Selection status" in response.data
        assert b"Change to" in response.data

    def test_get_with_uninitialised_schema_shows_init_prompt(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """With no schema the form is replaced by a Fields-tab prompt."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = create_respondent(
                uow, admin_user.id, existing_assembly.id, external_id="R-NOSCHEMA", attributes={}
            )
            resp_id = respondent.id

        response = logged_in_admin.get(self._edit_url(existing_assembly.id, resp_id))
        assert response.status_code == 200
        assert b"This assembly has no respondent fields configured yet." in response.data
        assert f"/assembly/{existing_assembly.id}/respondent-schema".encode() in response.data
        assert b"Save changes" not in response.data
        assert b"Change note" not in response.data

    def test_post_blank_comment_rerenders_with_error(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """A blank comment re-renders the form and leaves the email unchanged."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = self._make_respondent(uow, admin_user.id, existing_assembly.id)
            resp_id = respondent.id

        response = logged_in_admin.post(
            self._edit_url(existing_assembly.id, resp_id),
            data={"email": "other@example.com", "comment": ""},
            follow_redirects=False,
        )
        assert response.status_code == 200
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.respondents.get(resp_id).email == "r@example.com"

    def test_refused_for_deleted_respondent(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """Editing a DELETED respondent redirects to the view page."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = self._make_respondent(uow, admin_user.id, existing_assembly.id)
            resp_id = respondent.id
        with FakeUnitOfWork(store=fake_store) as uow:
            delete_respondent(uow, admin_user.id, existing_assembly.id, resp_id, comment="gdpr")

        response = logged_in_admin.get(self._edit_url(existing_assembly.id, resp_id), follow_redirects=False)
        assert response.status_code == 302
        assert self._view_url(existing_assembly.id, resp_id) in response.location

    def test_view_page_shows_edit_button(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """The view page links to the edit form."""
        with FakeUnitOfWork(store=fake_store) as uow:
            respondent = self._make_respondent(uow, admin_user.id, existing_assembly.id)
            resp_id = respondent.id

        response = logged_in_admin.get(self._view_url(existing_assembly.id, resp_id))
        assert response.status_code == 200
        assert b"/edit" in response.data

    def test_list_page_shows_edit_link_for_each_row(
        self, logged_in_admin: FlaskClient, existing_assembly: Assembly, admin_user, fake_store: FakeStore
    ) -> None:
        """The list page shows an edit link per row."""
        with FakeUnitOfWork(store=fake_store) as uow:
            self._make_respondent(uow, admin_user.id, existing_assembly.id)

        response = logged_in_admin.get(f"/backoffice/assembly/{existing_assembly.id}/respondents")
        assert response.status_code == 200
        assert b"Edit" in response.data
