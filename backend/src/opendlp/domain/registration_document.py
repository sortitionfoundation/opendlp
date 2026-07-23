"""ABOUTME: RegistrationDocument domain model and document value objects
ABOUTME: Holds a stored registration PDF plus pure <a> download-link HTML generation"""

import html as html_lib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

PDF_CONTENT_TYPE = "application/pdf"
PDF_FILE_EXTENSION = "pdf"
PDF_MAGIC = b"%PDF-"


class DocumentValidationError(Exception):
    """Raised when an uploaded document fails validation."""

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ValidatedDocument:
    data: bytes
    sha256: str
    byte_size: int


class RegistrationDocument:
    def __init__(
        self,
        registration_page_id: uuid.UUID,
        byte_size: int,
        sha256: str,
        data: bytes,
        original_filename: str = "",
        label: str = "",
        created_by: uuid.UUID | None = None,
        document_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = document_id or uuid.uuid4()
        self.registration_page_id = registration_page_id
        self.byte_size = byte_size
        self.sha256 = sha256
        self.data = data
        self.original_filename = original_filename
        self.label = label
        self.created_by = created_by
        self.created_at = created_at or datetime.now(UTC)

    @classmethod
    def from_validated(
        cls,
        registration_page_id: uuid.UUID,
        validated: ValidatedDocument,
        created_by: uuid.UUID | None = None,
        original_filename: str = "",
        label: str = "",
    ) -> "RegistrationDocument":
        return cls(
            registration_page_id=registration_page_id,
            byte_size=validated.byte_size,
            sha256=validated.sha256,
            data=validated.data,
            original_filename=original_filename,
            label=label,
            created_by=created_by,
        )

    def create_detached_copy(self) -> "RegistrationDocument":
        return RegistrationDocument(
            registration_page_id=self.registration_page_id,
            byte_size=self.byte_size,
            sha256=self.sha256,
            data=self.data,
            original_filename=self.original_filename,
            label=self.label,
            created_by=self.created_by,
            document_id=self.id,
            created_at=self.created_at,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RegistrationDocument):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


def generate_document_html(href: str, text: str) -> str:
    href_attr = html_lib.escape(href, quote=True)
    text_attr = html_lib.escape(text, quote=True)
    return f'<a href="{href_attr}">{text_attr}</a>'
