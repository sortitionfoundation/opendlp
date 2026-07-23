"""ABOUTME: Unit tests for the registration document service layer
ABOUTME: Covers add/list/delete, quota, dedup, label editing, snippet building and public serving"""

import uuid

import pytest

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_document import DocumentValidationError, RegistrationDocument
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageAction, RegistrationPageStatus
from opendlp.domain.users import User, UserAssemblyRole
from opendlp.domain.value_objects import AssemblyRole, AssemblyStatus, GlobalRole
from opendlp.service_layer import registration_document_service as service
from opendlp.service_layer.document_processing import validate_pdf
from opendlp.service_layer.exceptions import (
    AssemblyNotFoundError,
    DocumentQuotaExceeded,
    InsufficientPermissions,
    RegistrationDocumentNotFoundError,
    RegistrationPageNotFoundError,
    UserNotFoundError,
)
from tests.fakes import FakeUnitOfWork

_BIG = 5 * 1024 * 1024


def _pdf(marker: bytes = b"body") -> bytes:
    return b"%PDF-1.7\n" + marker + b"\n%%EOF\n"


def _admin(uow: FakeUnitOfWork) -> User:
    user = User(email=f"admin-{uuid.uuid4()}@example.com", global_role=GlobalRole.ADMIN, password_hash="hash")
    uow.users.add(user)
    return user


def _assembly(uow: FakeUnitOfWork) -> Assembly:
    assembly = Assembly(title="Test Assembly", question="?", status=AssemblyStatus.ACTIVE)
    uow.assemblies.add(assembly)
    return assembly


def _viewer(uow: FakeUnitOfWork, assembly: Assembly) -> User:
    user = User(email=f"viewer-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
    user.assembly_roles.append(
        UserAssemblyRole(user_id=user.id, assembly_id=assembly.id, role=AssemblyRole.CONFIRMATION_CALLER)
    )
    uow.users.add(user)
    return user


def _page(
    uow: FakeUnitOfWork,
    assembly: Assembly,
    *,
    url_slug: str = "a-page",
    status: RegistrationPageStatus = RegistrationPageStatus.PUBLISHED,
) -> RegistrationPage:
    page = RegistrationPage(assembly_id=assembly.id, url_slug=url_slug, status=status)
    uow.registration_pages.add(page)
    return page


def _stored_document(uow: FakeUnitOfWork, page: RegistrationPage, marker: bytes = b"body") -> RegistrationDocument:
    validated = validate_pdf(_pdf(marker), max_bytes=_BIG)
    document = RegistrationDocument.from_validated(page.id, validated)
    uow.registration_documents.add(document)
    return document


class TestAddRegistrationDocument:
    def test_stores_returns_and_records_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)

        document = service.add_registration_document(uow, admin.id, assembly.id, _pdf())

        assert isinstance(document, RegistrationDocument)
        assert uow.registration_documents.count_by_page_id(page.id) == 1
        assert uow.committed
        assert page.activity[-1].action == RegistrationPageAction.EDIT
        assert page.activity[-1].text == "Added a registration document"

    def test_permission_denied_for_viewer(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)
        _page(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.add_registration_document(uow, viewer.id, assembly.id, _pdf())

    def test_no_page_raises(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)

        with pytest.raises(RegistrationPageNotFoundError):
            service.add_registration_document(uow, admin.id, assembly.id, _pdf())

    def test_unknown_user_raises(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)

        with pytest.raises(UserNotFoundError):
            service.add_registration_document(uow, uuid.uuid4(), assembly.id, _pdf())

    def test_unknown_assembly_raises(self):
        uow = FakeUnitOfWork()
        admin = _admin(uow)

        with pytest.raises(AssemblyNotFoundError):
            service.add_registration_document(uow, admin.id, uuid.uuid4(), _pdf())

    def test_invalid_document_propagates(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        with pytest.raises(DocumentValidationError):
            service.add_registration_document(uow, admin.id, assembly.id, b"not a pdf")

    def test_stores_label(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        document = service.add_registration_document(uow, admin.id, assembly.id, _pdf(), label="Information pack")

        assert document.label == "Information pack"

    def test_label_defaults_to_filename(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        document = service.add_registration_document(
            uow, admin.id, assembly.id, _pdf(), original_filename="info pack.pdf"
        )

        assert document.label == "info pack.pdf"

    def test_dedup_updates_label(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        service.add_registration_document(uow, admin.id, assembly.id, _pdf(), label="First label")
        second = service.add_registration_document(uow, admin.id, assembly.id, _pdf(), label="Second label")

        assert second.label == "Second label"

    def test_stores_and_sanitises_original_filename(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        document = service.add_registration_document(
            uow, admin.id, assembly.id, _pdf(), original_filename="/home/user/info pack.pdf"
        )

        assert document.original_filename == "info pack.pdf"

    def test_dedup_keeps_first_original_filename(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        service.add_registration_document(uow, admin.id, assembly.id, _pdf(), original_filename="first.pdf")
        second = service.add_registration_document(uow, admin.id, assembly.id, _pdf(), original_filename="second.pdf")

        assert second.original_filename == "first.pdf"

    def test_dedup_returns_existing_without_new_row_or_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)

        first = service.add_registration_document(uow, admin.id, assembly.id, _pdf())
        activity_len = len(page.activity)
        second = service.add_registration_document(uow, admin.id, assembly.id, _pdf())

        assert second.id == first.id
        assert uow.registration_documents.count_by_page_id(page.id) == 1
        assert len(page.activity) == activity_len

    def test_quota_at_limit_raises(self, monkeypatch):
        monkeypatch.setenv("MAX_DOCUMENTS_PER_REGISTRATION_PAGE", "1")
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        service.add_registration_document(uow, admin.id, assembly.id, _pdf(b"one"))
        with pytest.raises(DocumentQuotaExceeded):
            service.add_registration_document(uow, admin.id, assembly.id, _pdf(b"two"))

    def test_dedup_at_limit_still_succeeds(self, monkeypatch):
        monkeypatch.setenv("MAX_DOCUMENTS_PER_REGISTRATION_PAGE", "1")
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)

        first = service.add_registration_document(uow, admin.id, assembly.id, _pdf())
        again = service.add_registration_document(uow, admin.id, assembly.id, _pdf())
        assert again.id == first.id
        assert uow.registration_documents.count_by_page_id(page.id) == 1


class TestListRegistrationDocuments:
    def test_lists_only_that_pages_documents(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)
        _stored_document(uow, page, b"one")
        _stored_document(uow, page, b"two")

        listed = service.list_registration_documents(uow, admin.id, assembly.id)
        assert len(listed) == 2

    def test_empty_when_no_page(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        assert service.list_registration_documents(uow, admin.id, assembly.id) == []

    def test_permission_denied_for_stranger(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        stranger = User(email=f"x-{uuid.uuid4()}@example.com", global_role=GlobalRole.USER, password_hash="hash")
        uow.users.add(stranger)
        _page(uow, assembly)

        with pytest.raises(InsufficientPermissions):
            service.list_registration_documents(uow, stranger.id, assembly.id)


class TestDeleteRegistrationDocument:
    def test_deletes_and_records_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)
        document = _stored_document(uow, page)

        service.delete_registration_document(uow, admin.id, assembly.id, document.id)

        assert uow.registration_documents.count_by_page_id(page.id) == 0
        assert page.activity[-1].text == "Deleted a registration document"

    def test_permission_denied_for_viewer(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)
        page = _page(uow, assembly)
        document = _stored_document(uow, page)

        with pytest.raises(InsufficientPermissions):
            service.delete_registration_document(uow, viewer.id, assembly.id, document.id)

    def test_missing_document_raises(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        with pytest.raises(RegistrationDocumentNotFoundError):
            service.delete_registration_document(uow, admin.id, assembly.id, uuid.uuid4())


class TestListDocumentSnippets:
    def test_builds_snippet_per_document_with_builder_url(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)
        service.add_registration_document(uow, admin.id, assembly.id, _pdf(), label="Information pack")

        snippets = service.list_document_snippets(uow, admin.id, assembly.id, lambda doc: f"/x/{doc.sha256}.pdf")
        assert len(snippets) == 1
        document, html = snippets[0]
        assert f'href="/x/{document.sha256}.pdf"' in html
        assert html.startswith("<a ")

    def test_snippet_text_includes_label_type_and_size(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)
        service.add_registration_document(uow, admin.id, assembly.id, _pdf(), label="Information pack")

        snippets = service.list_document_snippets(uow, admin.id, assembly.id, lambda doc: f"/x/{doc.sha256}.pdf")
        _, html = snippets[0]
        assert "Information pack (PDF, " in html


class TestSetRegistrationDocumentLabel:
    def test_updates_label_and_records_activity(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        page = _page(uow, assembly)
        document = _stored_document(uow, page)

        updated = service.set_registration_document_label(uow, admin.id, assembly.id, document.id, "New label")

        assert updated.label == "New label"
        assert uow.registration_documents.get(document.id).label == "New label"
        assert page.activity[-1].text == "Updated a registration document label"
        assert uow.committed

    def test_permission_denied_for_viewer(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        viewer = _viewer(uow, assembly)
        page = _page(uow, assembly)
        document = _stored_document(uow, page)

        with pytest.raises(InsufficientPermissions):
            service.set_registration_document_label(uow, viewer.id, assembly.id, document.id, "New label")

    def test_missing_document_raises(self):
        uow = FakeUnitOfWork()
        admin, assembly = _admin(uow), _assembly(uow)
        _page(uow, assembly)

        with pytest.raises(RegistrationDocumentNotFoundError):
            service.set_registration_document_label(uow, admin.id, assembly.id, uuid.uuid4(), "New label")


class TestGetRegistrationDocumentForServing:
    @pytest.mark.parametrize("status", [RegistrationPageStatus.TEST, RegistrationPageStatus.PUBLISHED])
    def test_serves_for_loadable_statuses(self, status):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        page = _page(uow, assembly, url_slug="live", status=status)
        document = _stored_document(uow, page)

        served = service.get_registration_document_for_serving(uow, "live", f"{document.sha256}.pdf")
        assert served is not None
        assert served.id == document.id

    def test_none_when_closed(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        page = _page(uow, assembly, url_slug="closed", status=RegistrationPageStatus.CLOSED)
        document = _stored_document(uow, page)

        assert service.get_registration_document_for_serving(uow, "closed", f"{document.sha256}.pdf") is None

    def test_none_for_unknown_slug(self):
        uow = FakeUnitOfWork()
        assert service.get_registration_document_for_serving(uow, "nope", "abc.pdf") is None

    def test_none_for_unknown_sha(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        _page(uow, assembly, url_slug="live")
        assert service.get_registration_document_for_serving(uow, "live", "deadbeef.pdf") is None

    def test_handles_missing_extension(self):
        uow = FakeUnitOfWork()
        assembly = _assembly(uow)
        page = _page(uow, assembly, url_slug="live")
        document = _stored_document(uow, page)

        served = service.get_registration_document_for_serving(uow, "live", document.sha256)
        assert served is not None
