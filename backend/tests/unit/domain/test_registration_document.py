"""ABOUTME: Unit tests for the RegistrationDocument domain model
ABOUTME: Covers the value object, entity, and pure <a> download-link HTML generation"""

import uuid

from opendlp.domain.registration_document import (
    PDF_CONTENT_TYPE,
    PDF_FILE_EXTENSION,
    PDF_MAGIC,
    RegistrationDocument,
    ValidatedDocument,
    generate_document_html,
)


def _validated() -> ValidatedDocument:
    return ValidatedDocument(data=b"%PDF-1.7 body", sha256="abc123", byte_size=13)


class TestValidatedDocument:
    def test_carries_bytes_and_hash(self):
        v = _validated()
        assert v.data == b"%PDF-1.7 body"
        assert v.sha256 == "abc123"
        assert v.byte_size == 13


class TestModuleConstants:
    def test_content_type_is_pdf(self):
        assert PDF_CONTENT_TYPE == "application/pdf"

    def test_file_extension_is_pdf(self):
        assert PDF_FILE_EXTENSION == "pdf"

    def test_magic_prefix(self):
        assert PDF_MAGIC == b"%PDF-"


class TestRegistrationDocument:
    def test_from_validated_copies_fields(self):
        page_id = uuid.uuid4()
        author = uuid.uuid4()
        doc = RegistrationDocument.from_validated(page_id, _validated(), created_by=author)

        assert doc.registration_page_id == page_id
        assert doc.created_by == author
        assert doc.data == b"%PDF-1.7 body"
        assert doc.sha256 == "abc123"
        assert doc.byte_size == 13
        assert isinstance(doc.id, uuid.UUID)

    def test_label_defaults_to_empty_string(self):
        doc = RegistrationDocument.from_validated(uuid.uuid4(), _validated())
        assert doc.label == ""

    def test_from_validated_keeps_label(self):
        doc = RegistrationDocument.from_validated(uuid.uuid4(), _validated(), label="Information pack")
        assert doc.label == "Information pack"

    def test_detached_copy_preserves_label(self):
        doc = RegistrationDocument.from_validated(uuid.uuid4(), _validated(), label="Information pack")
        assert doc.create_detached_copy().label == "Information pack"

    def test_original_filename_defaults_to_empty_string(self):
        doc = RegistrationDocument.from_validated(uuid.uuid4(), _validated())
        assert doc.original_filename == ""

    def test_from_validated_keeps_original_filename(self):
        doc = RegistrationDocument.from_validated(uuid.uuid4(), _validated(), original_filename="pack.pdf")
        assert doc.original_filename == "pack.pdf"

    def test_detached_copy_preserves_original_filename(self):
        doc = RegistrationDocument.from_validated(uuid.uuid4(), _validated(), original_filename="pack.pdf")
        assert doc.create_detached_copy().original_filename == "pack.pdf"

    def test_detached_copy_equal_by_id(self):
        doc = RegistrationDocument.from_validated(uuid.uuid4(), _validated())
        copy = doc.create_detached_copy()

        assert copy == doc
        assert copy.id == doc.id
        assert hash(copy) == hash(doc)

    def test_not_equal_to_other_type(self):
        doc = RegistrationDocument.from_validated(uuid.uuid4(), _validated())
        assert doc != "not a document"


class TestGenerateDocumentHtml:
    def test_structure(self):
        html = generate_document_html("/register/my-page/documents/abc.pdf", "Information pack (PDF, 312 KB)")
        assert html == '<a href="/register/my-page/documents/abc.pdf">Information pack (PDF, 312 KB)</a>'

    def test_escapes_text(self):
        html = generate_document_html("/x.pdf", '"><script>alert(1)</script>')
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_href(self):
        html = generate_document_html('/x.pdf" onclick="alert(1)', "label")
        assert 'onclick="alert(1)"' not in html
        assert "&quot;" in html
