"""ABOUTME: Unit tests for Flask context processors
ABOUTME: Tests context processors that inject variables into template context"""

import hashlib
from pathlib import Path
from unittest.mock import patch

from opendlp.entrypoints.context_processors import get_css_hash, static_versioning_context_processor


class TestGetCssHash:
    """Test the get_css_hash function."""

    def test_get_css_hash_returns_short_hash(self, tmp_path: Path):
        """Test that get_css_hash returns a short hash of the file contents."""
        # Clear cache to ensure clean state
        get_css_hash.cache_clear()

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

        # Cleanup
        get_css_hash.cache_clear()

    def test_get_css_hash_changes_when_content_changes(self, tmp_path: Path):
        """Test that the hash changes when file content changes."""
        # Clear cache to ensure clean state
        get_css_hash.cache_clear()

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

        # Cleanup
        get_css_hash.cache_clear()

    def test_get_css_hash_returns_empty_string_when_file_missing(self, tmp_path: Path):
        """Test that get_css_hash returns empty string when CSS file doesn't exist."""
        # Clear cache to ensure we're not using cached results
        get_css_hash.cache_clear()

        # tmp_path is empty, no application.css file
        with patch("opendlp.entrypoints.context_processors.config.get_static_path", return_value=tmp_path):
            result = get_css_hash()

        assert result == ""

        # Cleanup
        get_css_hash.cache_clear()

    def test_get_css_hash_is_cached(self, tmp_path: Path):
        """Test that get_css_hash uses functools.cache and returns cached value."""
        # Clear cache to ensure clean state
        get_css_hash.cache_clear()

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

        # Clear cache for other tests
        get_css_hash.cache_clear()


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
