"""ABOUTME: RegistrationImage domain model and image value objects
ABOUTME: Holds a stored registration image plus pure <img> HTML generation"""

import html as html_lib
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

IMAGE_CONTENT_TYPE = "image/png"
IMAGE_FILE_EXTENSION = "png"
ALLOWED_INPUT_FORMATS = {"PNG", "JPEG", "WEBP"}

# Bound on the stored original filename to stop an oversized name bloating the row.
MAX_ORIGINAL_FILENAME_LENGTH = 255

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


def sanitise_original_filename(name: str) -> str:
    """Reduce an uploaded filename to a safe, readable, bounded basename.

    Strips any directory components (handling both ``/`` and ``\\`` separators) and
    control characters, then truncates to ``MAX_ORIGINAL_FILENAME_LENGTH``. Spaces,
    unicode and case are preserved so the name still reflects what the user called
    the file.
    """
    # Take the basename relative to either separator so a Windows path doesn't slip through.
    basename = re.split(r"[\\/]", name)[-1]
    cleaned = _CONTROL_CHARS.sub("", basename).strip()
    return cleaned[:MAX_ORIGINAL_FILENAME_LENGTH]


class ImageValidationError(Exception):
    """Raised when an uploaded image fails validation or processing."""

    def __init__(self, reason: str, message: str):
        self.reason = reason
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    width: int
    height: int
    sha256: str
    byte_size: int


class RegistrationImage:
    def __init__(
        self,
        registration_page_id: uuid.UUID,
        byte_size: int,
        width: int,
        height: int,
        sha256: str,
        data: bytes,
        alt: str = "",
        original_filename: str = "",
        created_by: uuid.UUID | None = None,
        image_id: uuid.UUID | None = None,
        created_at: datetime | None = None,
    ):
        self.id = image_id or uuid.uuid4()
        self.registration_page_id = registration_page_id
        self.byte_size = byte_size
        self.width = width
        self.height = height
        self.sha256 = sha256
        self.data = data
        self.alt = alt
        self.original_filename = original_filename
        self.created_by = created_by
        self.created_at = created_at or datetime.now(UTC)

    @classmethod
    def from_processed(
        cls,
        registration_page_id: uuid.UUID,
        processed: ProcessedImage,
        created_by: uuid.UUID | None = None,
        alt: str = "",
        original_filename: str = "",
    ) -> "RegistrationImage":
        return cls(
            registration_page_id=registration_page_id,
            byte_size=processed.byte_size,
            width=processed.width,
            height=processed.height,
            sha256=processed.sha256,
            data=processed.data,
            alt=alt,
            original_filename=original_filename,
            created_by=created_by,
        )

    def create_detached_copy(self) -> "RegistrationImage":
        return RegistrationImage(
            registration_page_id=self.registration_page_id,
            byte_size=self.byte_size,
            width=self.width,
            height=self.height,
            sha256=self.sha256,
            data=self.data,
            alt=self.alt,
            original_filename=self.original_filename,
            created_by=self.created_by,
            image_id=self.id,
            created_at=self.created_at,
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, RegistrationImage):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)


def generate_image_html(src_url: str, alt: str = "") -> str:
    src = html_lib.escape(src_url, quote=True)
    alt_attr = html_lib.escape(alt, quote=True)
    return f'<img src="{src}" alt="{alt_attr}">'
