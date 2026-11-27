"""ABOUTME: Fake template renderer and URL generator for service-layer tests
ABOUTME: Part of the tests.fakes package of in-memory test doubles"""

from typing import Any


class FakeTemplateRenderer:
    """Fake template renderer for testing without Flask."""

    def __init__(self, templates: dict[str, str] | None = None):
        """
        Initialize with optional template strings.

        Args:
            templates: Dict mapping template names to template strings
        """
        self.templates = templates or {}
        self.rendered_templates: list[tuple[str, dict[str, Any]]] = []

    def render_template(self, template_name: str, **context: Any) -> str:
        """
        Render a template by simple string formatting.

        Args:
            template_name: Name of template to render
            **context: Template context variables

        Returns:
            Rendered template string
        """
        # Track what was rendered for test assertions
        self.rendered_templates.append((template_name, context))

        # If we have a template string, use it; otherwise return a simple format
        if template_name in self.templates:
            return self.templates[template_name].format(**context)

        # Default: return a simple formatted string for testing
        return f"Rendered {template_name} with context: {context}"


class FakeURLGenerator:
    """Fake URL generator for testing without Flask."""

    def __init__(self, url_map: dict[str, str] | None = None):
        """
        Initialize with optional URL mappings.

        Args:
            url_map: Dict mapping endpoint names to URL patterns
        """
        self.url_map = url_map or {
            "auth.confirm_email": "http://localhost/auth/confirm-email/{token}",
            "auth.reset_password": "http://localhost/auth/reset-password/{token}",  # pragma: allowlist secret
        }
        self.generated_urls: list[tuple[str, dict[str, Any]]] = []

    def generate_url(self, endpoint: str, _external: bool = False, **values: Any) -> str:
        """
        Generate a URL by looking up endpoint and formatting with values.

        Args:
            endpoint: Endpoint name (e.g., "auth.confirm_email")
            _external: Whether to generate absolute URL (always absolute in fake)
            **values: URL parameters

        Returns:
            Generated URL string
        """
        # Track what was generated for test assertions
        self.generated_urls.append((endpoint, {"_external": _external, **values}))

        # Look up URL pattern and format with values
        if endpoint in self.url_map:
            url_pattern = self.url_map[endpoint]
            return url_pattern.format(**values)

        # Default: return a simple URL for testing
        return f"http://localhost/{endpoint.replace('.', '/')}"
