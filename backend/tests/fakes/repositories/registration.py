"""ABOUTME: In-memory repositories for registration pages, their content, email templates and send records
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

import uuid

from opendlp.domain.email_send_record import RespondentEmailSendRecord
from opendlp.domain.email_template import EmailTemplate
from opendlp.domain.registration_content_block import RegistrationContentBlock
from opendlp.domain.registration_document import RegistrationDocument
from opendlp.domain.registration_image import RegistrationImage
from opendlp.domain.registration_page import RegistrationPage, RegistrationPageHtml
from opendlp.service_layer.repositories import (
    EmailTemplateRepository,
    RegistrationContentBlockRepository,
    RegistrationDocumentRepository,
    RegistrationImageRepository,
    RegistrationPageHtmlRepository,
    RegistrationPageRepository,
    RespondentEmailSendRecordRepository,
)
from tests.fakes.repositories.base import FakeRepository


class FakeRegistrationPageRepository(FakeRepository, RegistrationPageRepository):
    """Fake implementation of RegistrationPageRepository."""

    def list_by_assembly_id(self, assembly_id: uuid.UUID) -> list[RegistrationPage]:
        """Get every registration page for an assembly, oldest first."""
        pages = [item for item in self._items if item.assembly_id == assembly_id]
        return sorted(pages, key=lambda page: page.created_at)

    def get_by_url_slug(self, url_slug: str) -> RegistrationPage | None:
        """Get a registration page by its url_slug. Empty input returns None."""
        if not url_slug:
            return None
        for item in self._items:
            if item.url_slug == url_slug:
                return item
        return None

    def get_by_short_url_slug(self, short_url_slug: str) -> RegistrationPage | None:
        """Get a registration page by its short_url_slug. Empty input returns None."""
        if not short_url_slug:
            return None
        for item in self._items:
            if item.short_url_slug == short_url_slug:
                return item
        return None

    def delete(self, item: RegistrationPage) -> None:
        """Delete a RegistrationPage from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeRegistrationPageHtmlRepository(FakeRepository, RegistrationPageHtmlRepository):
    """Fake implementation of RegistrationPageHtmlRepository."""

    def get_by_page_id(self, registration_page_id: uuid.UUID) -> RegistrationPageHtml | None:
        """Get the HTML source for a registration page, or None if it has none."""
        for item in self._items:
            if item.registration_page_id == registration_page_id:
                return item
        return None

    def delete(self, item: RegistrationPageHtml) -> None:
        """Delete a RegistrationPageHtml from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeRegistrationImageRepository(FakeRepository, RegistrationImageRepository):
    """Fake implementation of RegistrationImageRepository."""

    def get_by_assembly_and_sha(self, assembly_id: uuid.UUID, sha256: str) -> RegistrationImage | None:
        """Get an image for a page by its content hash, or None."""
        for item in self._items:
            if item.assembly_id == assembly_id and item.sha256 == sha256:
                return item
        return None

    def list_by_assembly_id(self, assembly_id: uuid.UUID) -> list[RegistrationImage]:
        """Get all images for a registration page, oldest first."""
        items = [item for item in self._items if item.assembly_id == assembly_id]
        return sorted(items, key=lambda item: item.created_at)

    def count_by_assembly_id(self, assembly_id: uuid.UUID) -> int:
        """Count images for a registration page."""
        return sum(1 for item in self._items if item.assembly_id == assembly_id)

    def delete(self, item: RegistrationImage) -> None:
        """Delete a RegistrationImage from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeRegistrationDocumentRepository(FakeRepository, RegistrationDocumentRepository):
    """Fake implementation of RegistrationDocumentRepository."""

    def get_by_assembly_and_sha(self, assembly_id: uuid.UUID, sha256: str) -> RegistrationDocument | None:
        """Get a document for a page by its content hash, or None."""
        for item in self._items:
            if item.assembly_id == assembly_id and item.sha256 == sha256:
                return item
        return None

    def list_by_assembly_id(self, assembly_id: uuid.UUID) -> list[RegistrationDocument]:
        """Get all documents for a registration page, oldest first."""
        items = [item for item in self._items if item.assembly_id == assembly_id]
        return sorted(items, key=lambda item: item.created_at)

    def count_by_assembly_id(self, assembly_id: uuid.UUID) -> int:
        """Count documents for a registration page."""
        return sum(1 for item in self._items if item.assembly_id == assembly_id)

    def delete(self, item: RegistrationDocument) -> None:
        """Delete a RegistrationDocument from the repository."""
        if item in self._items:
            self._items.remove(item)


class FakeRegistrationContentBlockRepository(FakeRepository, RegistrationContentBlockRepository):
    """Fake in-memory RegistrationContentBlockRepository."""

    def list_by_assembly(self, assembly_id: uuid.UUID) -> list[RegistrationContentBlock]:
        blocks = [b for b in self._items if b.assembly_id == assembly_id]
        return sorted(blocks, key=lambda b: (b.sort_order, str(b.id)))

    def delete(self, item: RegistrationContentBlock) -> None:
        self._items = [b for b in self._items if b.id != item.id]


class FakeEmailTemplateRepository(FakeRepository, EmailTemplateRepository):
    """Fake implementation of EmailTemplateRepository."""

    def list_by_assembly(self, assembly_id: uuid.UUID) -> list[EmailTemplate]:
        templates = [t for t in self._items if t.assembly_id == assembly_id]
        return sorted(templates, key=lambda t: t.created_at)

    def delete(self, item: EmailTemplate) -> None:
        self._items = [t for t in self._items if t.id != item.id]


class FakeRespondentEmailSendRecordRepository(FakeRepository, RespondentEmailSendRecordRepository):
    """Fake implementation of RespondentEmailSendRecordRepository."""

    def list_by_respondent(self, respondent_id: uuid.UUID) -> list[RespondentEmailSendRecord]:
        records = [r for r in self._items if r.respondent_id == respondent_id]
        return sorted(records, key=lambda r: r.created_at)
