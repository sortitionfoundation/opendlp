"""ABOUTME: Unit tests for the registration document validation pipeline
ABOUTME: Exercises size and PDF magic-byte gating with no re-encode step"""

import hashlib

import pytest

from opendlp.domain.registration_document import DocumentValidationError
from opendlp.service_layer.document_processing import validate_pdf

_BIG = 5 * 1024 * 1024
_PDF = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj body\n%%EOF\n"


class TestValidatePdf:
    def test_accepts_valid_pdf_and_hashes(self):
        result = validate_pdf(_PDF, max_bytes=_BIG)
        assert result.data == _PDF
        assert result.byte_size == len(_PDF)
        assert result.sha256 == hashlib.sha256(_PDF).hexdigest()

    def test_rejects_oversized_bytes(self):
        with pytest.raises(DocumentValidationError) as exc:
            validate_pdf(_PDF, max_bytes=5)
        assert exc.value.reason == "too_large"

    def test_rejects_non_pdf_bytes(self):
        with pytest.raises(DocumentValidationError) as exc:
            validate_pdf(b"not a pdf at all", max_bytes=_BIG)
        assert exc.value.reason == "unsupported_format"

    def test_rejects_empty_input(self):
        with pytest.raises(DocumentValidationError) as exc:
            validate_pdf(b"", max_bytes=_BIG)
        assert exc.value.reason == "unsupported_format"

    def test_same_input_same_sha(self):
        assert validate_pdf(_PDF, max_bytes=_BIG).sha256 == validate_pdf(_PDF, max_bytes=_BIG).sha256

    def test_different_input_different_sha(self):
        other = b"%PDF-1.4\n other body \n%%EOF\n"
        assert validate_pdf(_PDF, max_bytes=_BIG).sha256 != validate_pdf(other, max_bytes=_BIG).sha256
