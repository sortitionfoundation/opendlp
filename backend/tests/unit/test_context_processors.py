"""ABOUTME: Unit tests for Flask context processors
ABOUTME: Tests context processors that inject variables into template context"""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from opendlp.entrypoints.context_processors import (
    _get_file_hash,
    get_opendlp_version,
    get_service_account_email,
    static_hashes,
    static_versioning_context_processor,
)


class TestStaticHashes:
    """Test the static_hashes function for cache-busting."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        _get_file_hash.cache_clear()
        yield
        _get_file_hash.cache_clear()

    def test_returns_short_hash_for_css(self, tmp_path: Path):
        """Test that static_hashes returns a short hash of the file contents."""
        css_dir = tmp_path / "css"
        css_dir.mkdir()
        css_file = css_dir / "application.css"
        css_content = "body { color: red; }"
        css_file.write_text(css_content)

        expected_hash = hashlib.sha256(css_content.encode()).hexdigest()[:8]

        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            result = static_hashes("css/application.css")

        assert result == expected_hash
        assert len(result) == 8

    def test_returns_short_hash_for_js(self, tmp_path: Path):
        """Test that static_hashes works for JavaScript files too."""
        js_dir = tmp_path / "js"
        js_dir.mkdir()
        js_file = js_dir / "utilities.js"
        js_content = "function foo() { return 42; }"
        js_file.write_text(js_content)

        expected_hash = hashlib.sha256(js_content.encode()).hexdigest()[:8]

        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            result = static_hashes("js/utilities.js")

        assert result == expected_hash

    def test_returns_empty_string_when_file_missing(self, tmp_path: Path):
        """Test that static_hashes returns empty string when file doesn't exist."""
        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            result = static_hashes("css/nonexistent.css")

        assert result == ""

    def test_different_files_get_different_hashes(self, tmp_path: Path):
        """Test that different files produce different hashes."""
        css_dir = tmp_path / "css"
        css_dir.mkdir()
        js_dir = tmp_path / "js"
        js_dir.mkdir()

        (css_dir / "application.css").write_text("body { color: red; }")
        (js_dir / "utilities.js").write_text("function foo() {}")

        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            css_hash = static_hashes("css/application.css")
            js_hash = static_hashes("js/utilities.js")

        assert css_hash != js_hash

    def test_works_with_nested_paths(self, tmp_path: Path):
        """Test that static_hashes works with deeply nested paths."""
        nested_dir = tmp_path / "backoffice" / "js"
        nested_dir.mkdir(parents=True)
        js_file = nested_dir / "alpine-components.js"
        js_content = "Alpine.data('foo', () => ({}))"
        js_file.write_text(js_content)

        expected_hash = hashlib.sha256(js_content.encode()).hexdigest()[:8]

        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            result = static_hashes("backoffice/js/alpine-components.js")

        assert result == expected_hash

    def test_underlying_hash_is_cached(self, tmp_path: Path):
        """Test that _get_file_hash uses functools.cache."""
        css_dir = tmp_path / "css"
        css_dir.mkdir()
        (css_dir / "application.css").write_text("body { color: red; }")

        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            hash1 = static_hashes("css/application.css")
            hash2 = static_hashes("css/application.css")

        assert hash1 == hash2
        assert hasattr(_get_file_hash, "cache_clear")
        assert hasattr(_get_file_hash, "cache_info")


class TestStaticVersioningContextProcessor:
    """Test the Flask context processor for static file versioning."""

    def test_context_processor_includes_static_hashes(self):
        """Test that the context processor includes static_hashes callable."""
        context = static_versioning_context_processor()

        assert isinstance(context, dict)
        assert "static_hashes" in context
        assert callable(context["static_hashes"])

    def test_context_processor_does_not_include_old_hash_keys(self):
        """Test that the old per-file hash keys have been removed."""
        context = static_versioning_context_processor()

        assert "css_hash" not in context
        assert "util_js_hash" not in context
        assert "alpine_js_hash" not in context
        assert "backoffice_alpine_js_hash" not in context


class TestGetOpendlpVersion:
    """Test the get_opendlp_version context processor"""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        # Clear cache to ensure clean state
        get_opendlp_version.cache_clear()
        yield
        # Cleanup
        get_opendlp_version.cache_clear()

    def test_get_opendlp_version_with_version_file(self, tmp_path):
        expected_version = "2000-01-02 1a2b3c4d"
        version_file = tmp_path / "generated_version.txt"
        version_file.write_text(f"{expected_version}\n")

        with patch("opendlp.entrypoints.context_processors.config.get_opendlp_version_path", return_value=version_file):
            assert get_opendlp_version() == expected_version

    def test_get_opendlp_version_with_empty_version_file_no_git_dir(self, tmp_path):
        version_file = tmp_path / "generated_version.txt"
        version_file.write_text("\n")

        with (
            patch("opendlp.entrypoints.context_processors.config.get_opendlp_version_path", return_value=version_file),
            patch("opendlp.entrypoints.context_processors.config.get_git_dir_path", return_value=tmp_path),
        ):
            assert get_opendlp_version() == "UNKNOWN"

    def test_get_opendlp_version_with_head_version_file_no_git_dir(self, tmp_path):
        version_file = tmp_path / "generated_version.txt"
        version_file.write_text("HEAD\n")

        with (
            patch("opendlp.entrypoints.context_processors.config.get_opendlp_version_path", return_value=version_file),
            patch("opendlp.entrypoints.context_processors.config.get_git_dir_path", return_value=tmp_path),
        ):
            assert get_opendlp_version() == "UNKNOWN"

    def test_get_opendlp_version_with_no_version_file_no_git_dir(self, tmp_path):
        version_file = tmp_path / "generated_version.txt"

        with (
            patch("opendlp.entrypoints.context_processors.config.get_opendlp_version_path", return_value=version_file),
            patch("opendlp.entrypoints.context_processors.config.get_git_dir_path", return_value=tmp_path),
        ):
            assert get_opendlp_version() == "UNKNOWN"

    def test_get_opendlp_version_with_no_version_file_git_dir(self, tmp_path, fake_process):
        expected_version = "2000-01-02 1a2b3c4d"
        version_file = tmp_path / "generated_version.txt"
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        fake_process.register(
            ["git", "show", "--no-patch", "--format=%cd %h", "--date=format:%Y-%m-%d", "HEAD"],
            stdout=f"{expected_version}\n",
        )

        with (
            patch("opendlp.entrypoints.context_processors.config.get_opendlp_version_path", return_value=version_file),
            patch("opendlp.entrypoints.context_processors.config.get_git_dir_path", return_value=git_dir),
        ):
            assert get_opendlp_version() == expected_version

    def test_get_opendlp_version_with_no_version_file_failed_git_cmd(self, tmp_path, fake_process):
        version_file = tmp_path / "generated_version.txt"
        git_dir = tmp_path / ".git"
        git_dir.mkdir()

        fake_process.register(
            ["git", "show", "--no-patch", "--format=%cd %h", "--date=format:%Y-%m-%d", "HEAD"],
            returncode=1,
        )

        with (
            patch("opendlp.entrypoints.context_processors.config.get_opendlp_version_path", return_value=version_file),
            patch("opendlp.entrypoints.context_processors.config.get_git_dir_path", return_value=git_dir),
        ):
            assert get_opendlp_version() == "UNKNOWN"


class TestGetServiceAccountEmail:
    """tests for get_service_account_email()"""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        # Clear cache to ensure clean state
        get_service_account_email.cache_clear()
        yield
        # Cleanup
        get_service_account_email.cache_clear()

    def test_get_service_account_email_with_no_auth_file(self, tmp_path):
        private_dir = tmp_path / "private"
        auth_file = private_dir / "auth.json"
        private_dir.mkdir()

        with patch("opendlp.entrypoints.context_processors.config.get_google_auth_json_path", return_value=auth_file):
            email = get_service_account_email()

        assert email == "UNKNOWN"

    @pytest.mark.parametrize(
        "contents",
        [
            "",
            "not a json file.]",
            '{"json": "but no matching key"}',
        ],
    )
    def test_get_service_account_email_with_invalid_auth_file(self, tmp_path, contents):
        private_dir = tmp_path / "private"
        auth_file = private_dir / "auth.json"
        private_dir.mkdir()
        auth_file.write_text(contents)

        with patch("opendlp.entrypoints.context_processors.config.get_google_auth_json_path", return_value=auth_file):
            email = get_service_account_email()

        assert email == "UNKNOWN"

    def test_get_service_account_email_with_valid_auth_file(self, tmp_path):
        private_dir = tmp_path / "private"
        auth_file = private_dir / "auth.json"
        private_dir.mkdir()
        auth_file.write_text("""
        {
        "key1": "value1",
        "key2": "value2",
        "client_email": "test@test.iam.gserviceaccount.com"
        }
        """)

        with patch("opendlp.entrypoints.context_processors.config.get_google_auth_json_path", return_value=auth_file):
            email = get_service_account_email()

        assert email == "test@test.iam.gserviceaccount.com"
