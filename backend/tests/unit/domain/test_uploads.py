"""ABOUTME: Unit tests for shared upload helpers
ABOUTME: Covers filename sanitising and human-readable byte sizes"""

from opendlp.domain.uploads import MAX_ORIGINAL_FILENAME_LENGTH, human_size, sanitise_original_filename


class TestSanitiseOriginalFilename:
    def test_keeps_a_plain_readable_name(self):
        assert sanitise_original_filename("info pack.PDF") == "info pack.PDF"

    def test_strips_unix_path_components(self):
        assert sanitise_original_filename("/home/user/docs/pack.pdf") == "pack.pdf"

    def test_strips_windows_path_components(self):
        assert sanitise_original_filename(r"C:\\Users\\me\\pack.pdf") == "pack.pdf"

    def test_strips_control_characters(self):
        assert sanitise_original_filename("pa\x00ck\x1f.pdf") == "pack.pdf"

    def test_truncates_to_max_length(self):
        long_name = "a" * (MAX_ORIGINAL_FILENAME_LENGTH + 50)
        assert len(sanitise_original_filename(long_name)) == MAX_ORIGINAL_FILENAME_LENGTH

    def test_empty_stays_empty(self):
        assert sanitise_original_filename("") == ""


class TestHumanSize:
    def test_bytes(self):
        assert human_size(512) == "512 bytes"

    def test_kilobytes(self):
        assert human_size(319488) == "312 KB"

    def test_one_kibibyte_boundary(self):
        assert human_size(1024) == "1 KB"

    def test_megabytes(self):
        assert human_size(2 * 1024 * 1024) == "2.0 MB"
