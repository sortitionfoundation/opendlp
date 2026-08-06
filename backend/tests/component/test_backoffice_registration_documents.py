# ABOUTME: Component tests for the backoffice registration document helpers and JSON routes
# ABOUTME: Drives the real POST/PATCH/DELETE endpoints + services over a FakeUnitOfWork via the test client

import uuid
from io import BytesIO

import pytest
from flask import has_request_context
from werkzeug.datastructures import FileStorage

from opendlp.domain.registration_document import RegistrationDocument
from opendlp.entrypoints.blueprints.backoffice_registration import _document_to_dict
from opendlp.service_layer.document_processing import validate_pdf
from opendlp.service_layer.registration_page_service import create_registration_page_with_slugs
from tests.fakes import FakeUnitOfWork

_MAX_BYTES = 10 * 1024 * 1024


def _pdf(marker: bytes = b"body") -> bytes:
    return b"%PDF-1.4\n" + marker + b"\n%%EOF"


def _document(*, label: str = "Info pack", sha256: str = "a" * 64, original_filename: str = "") -> RegistrationDocument:
    return RegistrationDocument(
        assembly_id=uuid.uuid4(),
        byte_size=123,
        sha256=sha256,
        data=_pdf(),
        label=label,
        original_filename=original_filename,
        created_by=uuid.uuid4(),
    )


@pytest.fixture
def registration_page(fake_store, admin_user, existing_assembly):
    with FakeUnitOfWork(store=fake_store) as uow:
        return create_registration_page_with_slugs(uow, admin_user.id, existing_assembly.id, name="Registration page")


def _seed_document(fake_store, page, *, label: str = "Info pack", marker: bytes = b"body") -> RegistrationDocument:
    validated = validate_pdf(_pdf(marker), max_bytes=_MAX_BYTES)
    document = RegistrationDocument.from_validated(page.assembly_id, validated, label=label)
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.registration_documents.add(document)
        uow.commit()
    return document.create_detached_copy()


def _stored_documents(fake_store, page) -> list[RegistrationDocument]:
    with FakeUnitOfWork(store=fake_store) as uow:
        return uow.registration_documents.list_by_assembly_id(page.assembly_id)


class TestDocumentToDict:
    def test_builds_public_url_and_snippet_when_slug_present(self, app):
        document = _document(label="Assembly info pack", sha256="b" * 64)
        with app.test_request_context():
            result = _document_to_dict(document, url_slug="my-slug")

        assert result["id"] == str(document.id)
        assert result["label"] == "Assembly info pack"
        assert result["file_name"] == f"{'b' * 64}.pdf"
        assert result["display_name"] == "Assembly info pack"
        assert "/register/my-slug/documents/" in result["public_url"]
        assert result["public_url"].endswith(f"{'b' * 64}.pdf")
        # Domain helper html-escapes both href and link text
        assert result["a_snippet"].startswith('<a href="')
        assert "Assembly info pack (PDF," in result["a_snippet"]
        assert result["byte_size"] == 123

    def test_includes_original_filename(self, app):
        document = _document(label="Assembly info pack", original_filename="info-pack.pdf")
        with app.test_request_context():
            result = _document_to_dict(document, url_slug="my-slug")
        assert result["original_filename"] == "info-pack.pdf"

    def test_falls_back_to_original_filename_when_label_blank(self, app):
        document = _document(label="   ", sha256="c" * 64, original_filename="info pack.pdf")
        with app.test_request_context():
            result = _document_to_dict(document, url_slug="my-slug")
        assert result["display_name"] == "info pack.pdf"

    def test_falls_back_to_short_sha_when_label_and_filename_blank(self, app):
        document = _document(label="   ", sha256="c" * 64)
        with app.test_request_context():
            result = _document_to_dict(document, url_slug="my-slug")
        assert result["display_name"] == f"{'c' * 8}.pdf"

    def test_omits_public_url_and_snippet_when_no_slug(self, app):
        document = _document(sha256="d" * 64)
        with app.test_request_context():
            result = _document_to_dict(document, url_slug="")
        assert result["public_url"] == ""
        assert result["a_snippet"] == ""


class TestDocumentRoutesRequireLogin:
    def test_upload_redirects_anonymous_to_login(self, client):
        assembly_id = uuid.uuid4()
        response = client.post(f"/backoffice/assembly/{assembly_id}/registration/documents")
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_patch_redirects_anonymous_to_login(self, client):
        assembly_id = uuid.uuid4()
        document_id = uuid.uuid4()
        response = client.patch(
            f"/backoffice/assembly/{assembly_id}/registration/documents/{document_id}",
            json={"label": "x"},
        )
        assert response.status_code == 302
        assert "/auth/login" in response.location

    def test_delete_redirects_anonymous_to_login(self, client):
        assembly_id = uuid.uuid4()
        document_id = uuid.uuid4()
        response = client.delete(f"/backoffice/assembly/{assembly_id}/registration/documents/{document_id}")
        assert response.status_code == 302
        assert "/auth/login" in response.location


class TestUploadRoute:
    def test_upload_with_file_and_label_returns_201_and_stores_document(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={
                "document": (BytesIO(_pdf()), "info-pack.pdf"),
                "label": "Assembly info pack",
            },
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        body = response.get_json()
        assert body["document"]["label"] == "Assembly info pack"
        assert body["document"]["original_filename"] == "info-pack.pdf"
        assert registration_page.url_slug in body["document"]["public_url"]

        stored = _stored_documents(fake_store, registration_page)
        assert len(stored) == 1
        assert stored[0].label == "Assembly info pack"
        assert stored[0].original_filename == "info-pack.pdf"
        assert body["document"]["id"] == str(stored[0].id)

    def test_upload_without_label_defaults_to_filename(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"document": (BytesIO(_pdf()), "info-pack.pdf")},
            content_type="multipart/form-data",
        )

        assert response.status_code == 201
        body = response.get_json()
        assert body["document"]["label"] == "info-pack.pdf"

        stored = _stored_documents(fake_store, registration_page)
        assert len(stored) == 1
        assert stored[0].label == "info-pack.pdf"

    def test_upload_rejects_non_pdf_bytes(self, logged_in_admin, existing_assembly, registration_page):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"document": (BytesIO(b"not a pdf"), "info-pack.pdf")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400
        assert response.get_json()["reason"] == "unsupported_format"

    def test_upload_rejects_missing_file(self, logged_in_admin, existing_assembly, registration_page):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"label": "Info pack"},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400


class TestUploadErrorBranches:
    def test_upload_read_failure_returns_400(self, logged_in_admin, existing_assembly, registration_page, monkeypatch):
        def _read(self, *args, **kwargs):
            # The test client also uses FileStorage.read while encoding the multipart
            # body — only fail server-side, inside the request context.
            if has_request_context():
                raise OSError("stream broke")
            return self.stream.read(*args, **kwargs)

        # FileStorage has no ``read`` class attribute (it proxies to the stream via
        # __getattr__), so create one — instance lookup finds it before __getattr__.
        monkeypatch.setattr(FileStorage, "read", _read, raising=False)
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"document": (BytesIO(_pdf()), "info-pack.pdf")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400
        assert "read" in response.get_json()["error"].lower()

    def test_upload_quota_exceeded_returns_400(
        self, logged_in_admin, existing_assembly, registration_page, monkeypatch
    ):
        monkeypatch.setattr(
            "opendlp.service_layer.registration_document_service.get_max_documents_per_assembly",
            lambda: 0,
        )
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"document": (BytesIO(_pdf()), "info-pack.pdf")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 400
        assert "maximum" in response.get_json()["error"].lower()

    def test_upload_without_registration_page_succeeds(self, logged_in_admin, existing_assembly):
        """Assets belong to the assembly, so they can be uploaded before any page exists."""
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"document": (BytesIO(_pdf()), "info-pack.pdf")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 201

    def test_upload_forbidden_for_regular_user_returns_403(self, logged_in_user, existing_assembly, registration_page):
        response = logged_in_user.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"document": (BytesIO(_pdf()), "info-pack.pdf")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 403

    def test_upload_unknown_assembly_returns_404(self, logged_in_admin):
        response = logged_in_admin.post(
            f"/backoffice/assembly/{uuid.uuid4()}/registration/documents",
            data={"document": (BytesIO(_pdf()), "info-pack.pdf")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 404

    def test_upload_unexpected_error_returns_500(
        self, logged_in_admin, existing_assembly, registration_page, monkeypatch
    ):
        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr("opendlp.entrypoints.blueprints.backoffice_registration.add_registration_document", _raise)
        response = logged_in_admin.post(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents",
            data={"document": (BytesIO(_pdf()), "info-pack.pdf")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 500


class TestPatchRoute:
    def test_patch_updates_label_and_returns_document(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        document = _seed_document(fake_store, registration_page, label="Original")

        response = logged_in_admin.patch(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{document.id}",
            json={"label": "Renamed"},
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body["document"]["label"] == "Renamed"
        assert body["document"]["id"] == str(document.id)

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_documents.get(document.id).label == "Renamed"

    def test_patch_rejects_missing_label(self, logged_in_admin, fake_store, existing_assembly, registration_page):
        document = _seed_document(fake_store, registration_page, label="Original")

        response = logged_in_admin.patch(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{document.id}",
            json={"label": "  "},
        )
        assert response.status_code == 400

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_documents.get(document.id).label == "Original"

    def test_patch_unknown_document_returns_404(self, logged_in_admin, existing_assembly, registration_page):
        response = logged_in_admin.patch(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{uuid.uuid4()}",
            json={"label": "Renamed"},
        )
        assert response.status_code == 404
        assert "document" in response.get_json()["error"].lower()

    def test_patch_forbidden_for_regular_user_returns_403(
        self, logged_in_user, fake_store, existing_assembly, registration_page
    ):
        document = _seed_document(fake_store, registration_page, label="Original")
        response = logged_in_user.patch(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{document.id}",
            json={"label": "Renamed"},
        )
        assert response.status_code == 403

        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_documents.get(document.id).label == "Original"

    def test_patch_unknown_assembly_returns_404(self, logged_in_admin):
        response = logged_in_admin.patch(
            f"/backoffice/assembly/{uuid.uuid4()}/registration/documents/{uuid.uuid4()}",
            json={"label": "Renamed"},
        )
        assert response.status_code == 404

    def test_patch_unexpected_error_returns_500(
        self, logged_in_admin, fake_store, existing_assembly, registration_page, monkeypatch
    ):
        document = _seed_document(fake_store, registration_page)

        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "opendlp.entrypoints.blueprints.backoffice_registration.set_registration_document_label", _raise
        )
        response = logged_in_admin.patch(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{document.id}",
            json={"label": "Renamed"},
        )
        assert response.status_code == 500


class TestDeleteRoute:
    def test_delete_returns_204_and_removes_document(
        self, logged_in_admin, fake_store, existing_assembly, registration_page
    ):
        document = _seed_document(fake_store, registration_page)

        response = logged_in_admin.delete(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{document.id}",
        )

        assert response.status_code == 204
        assert response.data == b""
        assert _stored_documents(fake_store, registration_page) == []

    def test_delete_unknown_document_returns_404(self, logged_in_admin, existing_assembly, registration_page):
        response = logged_in_admin.delete(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{uuid.uuid4()}",
        )
        assert response.status_code == 404

    def test_delete_forbidden_for_regular_user_returns_403(
        self, logged_in_user, fake_store, existing_assembly, registration_page
    ):
        document = _seed_document(fake_store, registration_page)
        response = logged_in_user.delete(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{document.id}",
        )
        assert response.status_code == 403
        assert len(_stored_documents(fake_store, registration_page)) == 1

    def test_delete_unknown_assembly_returns_404(self, logged_in_admin):
        response = logged_in_admin.delete(
            f"/backoffice/assembly/{uuid.uuid4()}/registration/documents/{uuid.uuid4()}",
        )
        assert response.status_code == 404

    def test_delete_unexpected_error_returns_500(
        self, logged_in_admin, fake_store, existing_assembly, registration_page, monkeypatch
    ):
        document = _seed_document(fake_store, registration_page)

        def _raise(*args, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "opendlp.entrypoints.blueprints.backoffice_registration.delete_registration_document", _raise
        )
        response = logged_in_admin.delete(
            f"/backoffice/assembly/{existing_assembly.id}/registration/documents/{document.id}",
        )
        assert response.status_code == 500
