"""ABOUTME: Template rendering adapters for decoupling service layer from Flask.
ABOUTME: Provides abstract interface and concrete Flask-based implementation."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flask import Flask


class TemplateRenderer(ABC):
    """Abstract interface for rendering templates."""

    @abstractmethod
    def render_template(self, template_name: str, **context: Any) -> str:
        """
        Render a template with the given context.

        Args:
            template_name: Path to template file (e.g., "emails/password_reset.html")
            **context: Variables to pass to the template

        Returns:
            Rendered template as a string
        """
        pass


class FlaskTemplateRenderer(TemplateRenderer):
    """Flask-based template renderer using Flask's template engine."""

    def __init__(self, app: "Flask"):
        """
        Initialize with Flask app.

        Args:
            app: Flask application instance
        """
        self.app = app

    def render_template(self, template_name: str, **context: Any) -> str:
        """
        Render a template using Flask's render_template.

        Args:
            template_name: Path to template file
            **context: Variables to pass to the template

        Returns:
            Rendered template as a string
        """
        # Import at runtime to avoid Flask dependency at module level
        from flask import render_template

        with self.app.app_context():
            return render_template(template_name, **context)
