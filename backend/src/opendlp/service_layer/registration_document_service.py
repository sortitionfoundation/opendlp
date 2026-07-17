"""ABOUTME: Service layer for registration document upload, listing, deletion and serving
ABOUTME: Validates and stores PDFs, builds <a> download snippets, resolves documents for the public route"""

import uuid
from collections.abc import Callable

from opendlp.config import get_max_documents_per_registration_page, get_max_pdf_upload_bytes
from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_document import RegistrationDocument, generate_document_html
from opendlp.domain.registration_page import RegistrationPage
from opendlp.domain.uploads import human_size, sanitise_original_filename
from opendlp.domain.users import User

from .document_processing import validate_pdf
from .exceptions import (
    AssemblyNotFoundError,
    DocumentQuotaExceeded,
    InsufficientPermissions,
    RegistrationDocumentNotFoundError,
    RegistrationPageNotFoundError,
    UserNotFoundError,
)
from .permissions import can_manage_assembly, can_view_assembly
from .unit_of_work import AbstractUnitOfWork

_MANAGE_ROLE = "assembly-manager, global-organiser or admin"
_VIEW_ROLE = "assembly role or global privileges"


def _load_user_and_assembly(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> tuple[User, Assembly]:
    user = uow.users.get(user_id)
    if not user:
        raise UserNotFoundError(f"User {user_id} not found")
    assembly = uow.assemblies.get(assembly_id)
    if not assembly:
        raise AssemblyNotFoundError(f"Assembly {assembly_id} not found")
    return user, assembly


def _load_page(uow: AbstractUnitOfWork, assembly_id: uuid.UUID) -> RegistrationPage:
    page = uow.registration_pages.get_by_assembly_id(assembly_id)
    if not page:
        raise RegistrationPageNotFoundError(f"Assembly {assembly_id} does not have a registration page")
    return page


def add_registration_document(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    raw: bytes,
    original_filename: str = "",
    label: str = "",
) -> RegistrationDocument:
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="add registration document", required_role=_MANAGE_ROLE)
        page = _load_page(uow, assembly_id)

        validated = validate_pdf(raw, max_bytes=get_max_pdf_upload_bytes())
        clean_filename = sanitise_original_filename(original_filename)
        # Label defaults to the filename; a future editor lets organisers change it.
        effective_label = label or clean_filename
        # Content-addressed dedup: identical bytes on a page collapse to one row.
        # The original filename is kept; the caller's label always wins on re-upload.
        existing = uow.registration_documents.get_by_page_and_sha(page.id, validated.sha256)
        if existing is not None:
            if existing.label != effective_label:
                existing.label = effective_label
                page.record_edit(user.id, "Updated a registration document label")
                uow.commit()
            return existing.create_detached_copy()

        limit = get_max_documents_per_registration_page()
        if uow.registration_documents.count_by_page_id(page.id) >= limit:
            raise DocumentQuotaExceeded(limit)

        document = RegistrationDocument.from_validated(
            page.id,
            validated,
            created_by=user.id,
            label=effective_label,
            original_filename=clean_filename,
        )
        uow.registration_documents.add(document)
        page.record_edit(user.id, "Added a registration document")
        uow.commit()
        return document.create_detached_copy()


def list_registration_documents(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID
) -> list[RegistrationDocument]:
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_view_assembly(user, assembly):
            raise InsufficientPermissions(action="view registration documents", required_role=_VIEW_ROLE)
        page = uow.registration_pages.get_by_assembly_id(assembly_id)
        if not page:
            return []
        return [document.create_detached_copy() for document in uow.registration_documents.list_by_page_id(page.id)]


def delete_registration_document(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, document_id: uuid.UUID
) -> None:
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="delete registration document", required_role=_MANAGE_ROLE)
        page = _load_page(uow, assembly_id)
        document = uow.registration_documents.get(document_id)
        if document is None or document.registration_page_id != page.id:
            raise RegistrationDocumentNotFoundError(f"Document {document_id} not found for this registration page")
        uow.registration_documents.delete(document)
        page.record_edit(user.id, "Deleted a registration document")
        uow.commit()


def set_registration_document_label(
    uow: AbstractUnitOfWork, user_id: uuid.UUID, assembly_id: uuid.UUID, document_id: uuid.UUID, label: str
) -> RegistrationDocument:
    with uow:
        user, assembly = _load_user_and_assembly(uow, user_id, assembly_id)
        if not can_manage_assembly(user, assembly):
            raise InsufficientPermissions(action="edit registration document", required_role=_MANAGE_ROLE)
        page = _load_page(uow, assembly_id)
        document: RegistrationDocument | None = uow.registration_documents.get(document_id)
        if document is None or document.registration_page_id != page.id:
            raise RegistrationDocumentNotFoundError(f"Document {document_id} not found for this registration page")
        document.label = label
        page.record_edit(user.id, "Updated a registration document label")
        uow.commit()
        return document.create_detached_copy()


def list_document_snippets(
    uow: AbstractUnitOfWork,
    user_id: uuid.UUID,
    assembly_id: uuid.UUID,
    url_for_document: Callable[[RegistrationDocument], str],
) -> list[tuple[RegistrationDocument, str]]:
    documents = list_registration_documents(uow, user_id, assembly_id)
    return [
        (document, generate_document_html(url_for_document(document), _snippet_text(document)))
        for document in documents
    ]


def _snippet_text(document: RegistrationDocument) -> str:
    return f"{document.label} (PDF, {human_size(document.byte_size)})"


def get_registration_document_for_serving(
    uow: AbstractUnitOfWork, url_slug: str, document_name: str
) -> RegistrationDocument | None:
    sha256 = document_name.rsplit(".", 1)[0]
    with uow:
        page = uow.registration_pages.get_by_url_slug(url_slug)
        if page is None or not page.is_publicly_loadable():
            return None
        document = uow.registration_documents.get_by_page_and_sha(page.id, sha256)
        return document.create_detached_copy() if document else None
