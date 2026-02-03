"""ABOUTME: URL generation adapters for decoupling service layer from Flask.
ABOUTME: Provides abstract interface and concrete Flask-based implementation."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from flask import Flask


class URLGenerator(ABC):
    """Abstract interface for generating URLs."""

    @abstractmethod
    def generate_url(self, endpoint: str, _external: bool = False, **values: Any) -> str:
        """
        Generate a URL for the given endpoint.

        Args:
            endpoint: Flask endpoint name (e.g., "auth.confirm_email")
            _external: Whether to generate an absolute URL with domain
            **values: URL parameters to include

        Returns:
            Generated URL as a string
        """
        pass


class FlaskURLGenerator(URLGenerator):
    """Flask-based URL generator using Flask's url_for."""

    def __init__(self, app: "Flask"):
        """
        Initialize with Flask app.

        Args:
            app: Flask application instance
        """
        self.app = app

    def generate_url(self, endpoint: str, _external: bool = False, **values: Any) -> str:
        """
        Generate a URL using Flask's url_for.

        Args:
            endpoint: Flask endpoint name
            _external: Whether to generate an absolute URL
            **values: URL parameters

        Returns:
            Generated URL as a string
        """
        return self.app.url_for(endpoint, _external=_external, **values)
