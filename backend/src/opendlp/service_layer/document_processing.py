"""ABOUTME: Document validation for registration PDFs
ABOUTME: Size cap and %PDF- magic-byte gate; stores bytes as-uploaded, no re-encode"""

import hashlib

from opendlp.domain.registration_document import PDF_MAGIC, DocumentValidationError, ValidatedDocument
from opendlp.translations import gettext as _


def validate_pdf(raw: bytes, *, max_bytes: int) -> ValidatedDocument:
    if len(raw) > max_bytes:
        raise DocumentValidationError("too_large", _("The PDF file is too large"))
    if not raw.startswith(PDF_MAGIC):
        raise DocumentValidationError("unsupported_format", _("The file must be a PDF"))
    return ValidatedDocument(
        data=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
    )
