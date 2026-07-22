"""ABOUTME: Component tests for the dev /service-docs document-service handlers
ABOUTME: Drives the six _handle_* functions through real services over a FakeUnitOfWork, asserting on real outcomes"""

import base64
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_document import RegistrationDocument
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageStatus
from opendlp.domain.users import User
from opendlp.domain.value_objects import AssemblyStatus, GlobalRole
from opendlp.entrypoints.blueprints.dev import (
    _handle_add_registration_document,
    _handle_delete_registration_document,
    _handle_get_registration_document_for_serving,
    _handle_list_document_snippets,
    _handle_list_registration_documents,
    _handle_set_registration_document_label,
    _serialise_document,
)
from opendlp.service_layer.document_processing import validate_pdf
from tests.fakes import FakeStore, FakeUnitOfWork

_MAX_BYTES = 10 * 1024 * 1024


def _pdf(payload: bytes = b"hello") -> bytes:
    return b"%PDF-1.4\n" + payload


def _seed_admin(store: FakeStore) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    with FakeUnitOfWork(store=store) as uow:
        uow.users.add(user)
        uow.commit()
    return user


def _seed_page(store: FakeStore, *, url_slug: str = "my-slug") -> RegistrationPage:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    page = RegistrationPage(assembly_id=assembly.id, url_slug=url_slug, status=RegistrationPageStatus.PUBLISHED)
    with FakeUnitOfWork(store=store) as uow:
        uow.assemblies.add(assembly)
        uow.registration_pages.add(page)
        uow.commit()
    return page


def _seed_document(store: FakeStore, page: RegistrationPage, payload: bytes = b"hello") -> RegistrationDocument:
    validated = validate_pdf(_pdf(payload), max_bytes=_MAX_BYTES)
    document = RegistrationDocument.from_validated(page.id, validated, label="Info pack", original_filename="info.pdf")
    with FakeUnitOfWork(store=store) as uow:
        uow.registration_documents.add(document)
        uow.commit()
    return document


@pytest.fixture
def fake_store():
    return FakeStore()


@pytest.fixture
def admin(fake_store):
    return _seed_admin(fake_store)


@pytest.fixture
def page(fake_store):
    return _seed_page(fake_store)


@pytest.fixture
def app(fake_store):
    from opendlp.entrypoints.flask_app import create_app  # noqa: PLC0415

    return create_app("testing_component", uow_factory=lambda: FakeUnitOfWork(store=fake_store))


@pytest.fixture
def as_admin(app, admin):
    """Push a request context with current_user set to the seeded admin."""
    with (
        app.test_request_context(),
        patch("opendlp.entrypoints.blueprints.dev.current_user", SimpleNamespace(id=admin.id)),
    ):
        yield


def _uow(fake_store) -> FakeUnitOfWork:
    return FakeUnitOfWork(store=fake_store)


class TestSerialiseDocument:
    def test_emits_expected_fields(self):
        document = RegistrationDocument(
            registration_page_id=uuid.uuid4(),
            byte_size=321,
            sha256="e" * 64,
            data=b"%PDF-bytes",
            label="Info pack",
            original_filename="info.pdf",
            created_by=uuid.uuid4(),
        )
        result = _serialise_document(document)
        assert result["id"] == str(document.id)
        assert result["label"] == "Info pack"
        assert result["sha256"] == "e" * 64
        assert result["file_name"] == f"{'e' * 64}.pdf"
        assert result["original_filename"] == "info.pdf"
        assert result["byte_size"] == 321


class TestHandleAddRegistrationDocument:
    def test_decodes_base64_and_stores_document(self, fake_store, page, as_admin):
        b64 = base64.b64encode(_pdf()).decode()
        result = _handle_add_registration_document(
            uow=_uow(fake_store),
            params={
                "assembly_id": str(page.assembly_id),
                "pdf_base64": b64,
                "label": "Decoded",
                "original_filename": "pack.pdf",
            },
        )

        assert result["status"] == "success"
        assert result["document"]["label"] == "Decoded"
        assert result["document"]["original_filename"] == "pack.pdf"
        with _uow(fake_store) as uow:
            stored = uow.registration_documents.list_by_page_id(page.id)
        assert len(stored) == 1
        assert stored[0].label == "Decoded"

    def test_strips_data_url_prefix(self, fake_store, page, as_admin):
        b64 = base64.b64encode(_pdf()).decode()
        result = _handle_add_registration_document(
            uow=_uow(fake_store),
            params={
                "assembly_id": str(page.assembly_id),
                "pdf_base64": f"data:application/pdf;base64,{b64}",
                "label": "Prefixed",
            },
        )

        assert result["status"] == "success"
        with _uow(fake_store) as uow:
            assert len(uow.registration_documents.list_by_page_id(page.id)) == 1

    def test_invalid_base64_returns_error(self, fake_store, page, as_admin):
        result = _handle_add_registration_document(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id), "pdf_base64": "not!base64!", "label": "x"},
        )
        assert result["status"] == "error"
        assert result["error_type"] == "ValidationError"

    def test_non_pdf_bytes_return_validation_error(self, fake_store, page, as_admin):
        b64 = base64.b64encode(b"plain text, not a pdf").decode()
        result = _handle_add_registration_document(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id), "pdf_base64": b64, "label": "x"},
        )
        assert result["status"] == "error"
        assert result["error_type"] == "DocumentValidationError"
        assert result["reason"] == "unsupported_format"


class TestHandleListRegistrationDocuments:
    def test_returns_serialised_list(self, fake_store, page, as_admin):
        _seed_document(fake_store, page, payload=b"one")
        _seed_document(fake_store, page, payload=b"two")

        result = _handle_list_registration_documents(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id)},
        )

        assert result["status"] == "success"
        assert result["total_count"] == 2
        assert len(result["documents"]) == 2


class TestHandleDeleteRegistrationDocument:
    def test_deletes_and_returns_id(self, fake_store, page, as_admin):
        document = _seed_document(fake_store, page)

        result = _handle_delete_registration_document(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id), "document_id": str(document.id)},
        )

        assert result == {"status": "success", "deleted_document_id": str(document.id)}
        with _uow(fake_store) as uow:
            assert uow.registration_documents.list_by_page_id(page.id) == []


class TestHandleSetRegistrationDocumentLabel:
    def test_updates_label_and_returns_serialised_document(self, fake_store, page, as_admin):
        document = _seed_document(fake_store, page)

        result = _handle_set_registration_document_label(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id), "document_id": str(document.id), "label": "Renamed"},
        )

        assert result["status"] == "success"
        assert result["document"]["label"] == "Renamed"
        with _uow(fake_store) as uow:
            assert uow.registration_documents.get(document.id).label == "Renamed"


class TestHandleListDocumentSnippets:
    def test_pairs_document_with_html_snippet(self, fake_store, page, as_admin):
        _seed_document(fake_store, page)

        result = _handle_list_document_snippets(
            uow=_uow(fake_store),
            params={"assembly_id": str(page.assembly_id)},
        )

        assert result["status"] == "success"
        assert result["total_count"] == 1
        assert page.url_slug in result["snippets"][0]["html"]


class TestHandleGetRegistrationDocumentForServing:
    def test_found_returns_serialised_document(self, fake_store, page, as_admin):
        document = _seed_document(fake_store, page)

        result = _handle_get_registration_document_for_serving(
            uow=_uow(fake_store),
            params={"url_slug": page.url_slug, "document_name": f"{document.sha256}.pdf"},
        )

        assert result["status"] == "success"
        assert result["found"] is True
        assert result["document"]["id"] == str(document.id)

    def test_not_found_returns_none(self, fake_store, page, as_admin):
        result = _handle_get_registration_document_for_serving(
            uow=_uow(fake_store),
            params={"url_slug": "bad-slug", "document_name": "x.pdf"},
        )

        assert result == {"status": "success", "found": False, "document": None}
