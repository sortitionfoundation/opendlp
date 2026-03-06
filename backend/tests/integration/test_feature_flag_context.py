"""ABOUTME: Integration tests for feature flag template context processor.
ABOUTME: Verifies the feature() function is available in Jinja templates via the Flask app."""

import os

from flask import Flask, render_template_string

from opendlp.entrypoints.context_processors import inject_feature_flags
from opendlp.feature_flags import reload_flags


def _make_app(env_overrides: dict[str, str] | None = None) -> Flask:
    """Create a minimal Flask app with feature flag context processor registered."""
    if env_overrides:
        os.environ.update(env_overrides)
    reload_flags()

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.context_processor(inject_feature_flags)

    @app.route("/test-feature")
    def test_feature() -> str:
        template = "{% if feature('example') %}ENABLED{% else %}DISABLED{% endif %}"
        return render_template_string(template)

    return app


class TestFeatureFlagContextProcessor:
    """Test that the feature() function works inside Jinja templates."""

    def test_feature_enabled_in_template(self, monkeypatch):
        monkeypatch.setenv("FF_EXAMPLE", "true")
        app = _make_app()
        with app.test_client() as client:
            response = client.get("/test-feature")
            assert response.data == b"ENABLED"

    def test_feature_disabled_in_template(self, monkeypatch):
        monkeypatch.delenv("FF_EXAMPLE", raising=False)
        app = _make_app()
        with app.test_client() as client:
            response = client.get("/test-feature")
            assert response.data == b"DISABLED"

    def test_feature_explicitly_false_in_template(self, monkeypatch):
        monkeypatch.setenv("FF_EXAMPLE", "false")
        app = _make_app()
        with app.test_client() as client:
            response = client.get("/test-feature")
            assert response.data == b"DISABLED"
