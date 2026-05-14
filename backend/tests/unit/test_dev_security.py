"""ABOUTME: Unit tests for dev.py security functions
ABOUTME: Tests URL validation to prevent open redirect attacks"""

from opendlp.entrypoints.blueprints.dev import _is_safe_redirect_url


class TestIsSafeRedirectUrl:
    def test_relative_url_is_safe(self) -> None:
        """Relative URLs starting with / are safe."""
        assert _is_safe_redirect_url("/some/path") is True
        assert _is_safe_redirect_url("/") is True
        assert _is_safe_redirect_url("/backoffice/dev/patterns") is True

    def test_relative_url_with_query_string_is_safe(self) -> None:
        """Relative URLs with query strings are safe."""
        assert _is_safe_redirect_url("/path?tab=floating-alerts") is True
        assert _is_safe_redirect_url("/path?foo=bar&baz=qux") is True

    def test_protocol_relative_url_is_not_safe(self) -> None:
        """Protocol-relative URLs (//example.com) are not safe."""
        assert _is_safe_redirect_url("//evil.com/path") is False
        assert _is_safe_redirect_url("//example.com") is False

    def test_absolute_url_is_not_safe(self) -> None:
        """Absolute URLs with protocol are not safe."""
        assert _is_safe_redirect_url("https://evil.com/path") is False
        assert _is_safe_redirect_url("http://example.com") is False

    def test_javascript_url_is_not_safe(self) -> None:
        """JavaScript URLs are not safe."""
        assert _is_safe_redirect_url("javascript:alert(1)") is False

    def test_empty_url_is_not_safe(self) -> None:
        """Empty URL is not safe."""
        assert _is_safe_redirect_url("") is False

    def test_relative_path_without_leading_slash_is_not_safe(self) -> None:
        """Relative paths without leading slash are not safe."""
        assert _is_safe_redirect_url("path/to/page") is False
        assert _is_safe_redirect_url("../evil") is False
