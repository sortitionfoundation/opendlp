from flask import url_for
from flask.testing import FlaskClient


def get_csrf_token(client: FlaskClient, endpoint: str) -> str:
    """Helper to extract CSRF token from form."""
    # For now, we'll use a placeholder - in a real implementation this would parse HTML
    return "csrf_token_placeholder"


def route_url(client: FlaskClient, endpoint: str, **values: object) -> str:
    """Build a relative URL for a Flask endpoint so tests don't hard-code paths.

    Uses the client's own app context, so the URL tracks the route definition and
    callers don't need updating when a route's path changes.
    """
    with client.application.test_request_context():
        return url_for(endpoint, **values)
