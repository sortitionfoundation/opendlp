"""ABOUTME: Unit tests for the RegistrationImage domain model
ABOUTME: Covers the value object, entity, and pure <img> HTML generation"""

import uuid

from opendlp.domain.registration_image import (
    IMAGE_CONTENT_TYPE,
    MAX_ORIGINAL_FILENAME_LENGTH,
    ProcessedImage,
    RegistrationImage,
    generate_image_html,
    sanitise_original_filename,
)


def _processed() -> ProcessedImage:
    return ProcessedImage(data=b"pngbytes", width=120, height=80, sha256="abc123", byte_size=8)


class TestProcessedImage:
    def test_carries_dimensions_and_hash(self):
        p = _processed()
        assert p.data == b"pngbytes"
        assert p.width == 120
        assert p.height == 80
        assert p.sha256 == "abc123"
        assert p.byte_size == 8

    def test_content_type_constant_is_png(self):
        assert IMAGE_CONTENT_TYPE == "image/png"


class TestRegistrationImage:
    def test_from_processed_copies_fields(self):
        page_id = uuid.uuid4()
        author = uuid.uuid4()
        img = RegistrationImage.from_processed(page_id, _processed(), created_by=author)

        assert img.registration_page_id == page_id
        assert img.created_by == author
        assert img.data == b"pngbytes"
        assert img.width == 120
        assert img.height == 80
        assert img.sha256 == "abc123"
        assert img.byte_size == 8
        assert isinstance(img.id, uuid.UUID)

    def test_alt_defaults_to_empty_string(self):
        img = RegistrationImage.from_processed(uuid.uuid4(), _processed())
        assert img.alt == ""

    def test_from_processed_keeps_alt(self):
        img = RegistrationImage.from_processed(uuid.uuid4(), _processed(), alt="A red square")
        assert img.alt == "A red square"

    def test_detached_copy_preserves_alt(self):
        img = RegistrationImage.from_processed(uuid.uuid4(), _processed(), alt="A red square")
        assert img.create_detached_copy().alt == "A red square"

    def test_original_filename_defaults_to_empty_string(self):
        img = RegistrationImage.from_processed(uuid.uuid4(), _processed())
        assert img.original_filename == ""

    def test_from_processed_keeps_original_filename(self):
        img = RegistrationImage.from_processed(uuid.uuid4(), _processed(), original_filename="holiday photo.jpg")
        assert img.original_filename == "holiday photo.jpg"

    def test_detached_copy_preserves_original_filename(self):
        img = RegistrationImage.from_processed(uuid.uuid4(), _processed(), original_filename="holiday photo.jpg")
        assert img.create_detached_copy().original_filename == "holiday photo.jpg"

    def test_detached_copy_equal_by_id(self):
        img = RegistrationImage.from_processed(uuid.uuid4(), _processed())
        copy = img.create_detached_copy()
        assert copy == img
        assert copy.id == img.id
        assert hash(copy) == hash(img)

    def test_not_equal_to_other_type(self):
        img = RegistrationImage.from_processed(uuid.uuid4(), _processed())
        assert img != "not an image"


class TestSanitiseOriginalFilename:
    def test_keeps_a_plain_readable_name(self):
        assert sanitise_original_filename("holiday photo.JPG") == "holiday photo.JPG"

    def test_strips_unix_path_components(self):
        assert sanitise_original_filename("/home/user/photos/cat.png") == "cat.png"

    def test_strips_windows_path_components(self):
        assert sanitise_original_filename(r"C:\\Users\\me\\cat.png") == "cat.png"

    def test_strips_control_characters(self):
        assert sanitise_original_filename("ca\x00t\x1f.png") == "cat.png"

    def test_truncates_to_max_length(self):
        long_name = "a" * (MAX_ORIGINAL_FILENAME_LENGTH + 50)
        result = sanitise_original_filename(long_name)
        assert len(result) == MAX_ORIGINAL_FILENAME_LENGTH

    def test_empty_stays_empty(self):
        assert sanitise_original_filename("") == ""


class TestGenerateImageHtml:
    def test_structure(self):
        html = generate_image_html("/register/my-page/assets/abc.png", alt="Our logo")
        assert html == '<img src="/register/my-page/assets/abc.png" alt="Our logo">'

    def test_escapes_alt(self):
        html = generate_image_html("/x.png", alt='"><script>alert(1)</script>')
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_escapes_src(self):
        html = generate_image_html('/x.png" onerror="alert(1)')
        assert 'onerror="alert(1)"' not in html
        assert "&quot;" in html
