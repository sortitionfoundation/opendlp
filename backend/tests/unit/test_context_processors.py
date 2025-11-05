"""ABOUTME: Unit tests for Flask context processors
ABOUTME: Tests context processors that inject variables into template context"""

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from opendlp.entrypoints.context_processors import (
    get_css_hash,
    get_opendlp_version,
    static_versioning_context_processor,
)


class TestGetCssHash:
    """Test the get_css_hash function."""

    @pytest.fixture(autouse=True)
    def clear_cache(self):
        # Clear cache to ensure clean state
        get_css_hash.cache_clear()
        yield
        # Cleanup
        get_css_hash.cache_clear()

    def test_get_css_hash_returns_short_hash(self, tmp_path: Path):
        """Test that get_css_hash returns a short hash of the file contents."""
        # Create a temporary CSS file in css subdirectory
        css_dir = tmp_path / "css"
        css_dir.mkdir()
        css_file = css_dir / "application.css"
        css_content = "body { color: red; }"
        css_file.write_text(css_content)

        # Calculate expected hash
        expected_hash = hashlib.sha256(css_content.encode()).hexdigest()[:8]

        # Mock get_static_path to return our tmp_path
        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            result = get_css_hash()

        assert result == expected_hash
        assert len(result) == 8

    def test_get_css_hash_changes_when_content_changes(self, tmp_path: Path):
        """Test that the hash changes when file content changes."""
        css_dir = tmp_path / "css"
        css_dir.mkdir()
        css_file = css_dir / "application.css"

        # Write initial content
        css_file.write_text("body { color: red; }")
        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            hash1 = get_css_hash()

        # Clear the cache to force recalculation
        get_css_hash.cache_clear()

        # Write different content
        css_file.write_text("body { color: blue; }")
        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            hash2 = get_css_hash()

        assert hash1 != hash2

    def test_get_css_hash_returns_empty_string_when_file_missing(self, tmp_path: Path):
        """Test that get_css_hash returns empty string when CSS file doesn't exist."""
        # tmp_path is empty, no application.css file
        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            result = get_css_hash()

        assert result == ""

    def test_get_css_hash_is_cached(self, tmp_path: Path):
        """Test that get_css_hash uses functools.cache and returns cached value."""
        css_dir = tmp_path / "css"
        css_dir.mkdir()
        css_file = css_dir / "application.css"
        css_file.write_text("body { color: red; }")

        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            # First call
            hash1 = get_css_hash()
            # Second call - should be cached
            hash2 = get_css_hash()

        assert hash1 == hash2

        # Verify function has cache_clear method (indicating it's decorated with cache)
        assert hasattr(get_css_hash, "cache_clear")
        assert hasattr(get_css_hash, "cache_info")


class TestStaticVersioningContextProcessor:
    """Test the Flask context processor for static file versioning."""

    def test_context_processor_adds_css_hash(self):
        """Test that the context processor adds css_hash to template context."""
        # Call the context processor
        context = static_versioning_context_processor()

        # Should return a dict with css_hash key
        assert isinstance(context, dict)
        assert "css_hash" in context
        assert isinstance(context["css_hash"], str)

    def test_context_processor_uses_get_css_hash(self, tmp_path: Path):
        """Test that the context processor uses get_css_hash function."""
        # Setup test file
        css_dir = tmp_path / "css"
        css_dir.mkdir()
        css_file = css_dir / "application.css"
        css_content = "body { color: green; }"
        css_file.write_text(css_content)
        expected_hash = hashlib.sha256(css_content.encode()).hexdigest()[:8]

        # Clear cache and mock the path
        get_css_hash.cache_clear()
        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            context = static_versioning_context_processor()

        assert context["css_hash"] == expected_hash

        # Cleanup
        get_css_hash.cache_clear()


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
