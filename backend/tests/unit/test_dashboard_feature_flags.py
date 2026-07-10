"""ABOUTME: Unit tests for the dashboard feature-flag wiring.
ABOUTME: Covers default_dashboard_endpoint(), old_dashboard_route_enabled(), and footer rendering."""

import os

import pytest
from flask import Blueprint, Flask, render_template_string

from opendlp.entrypoints.context_processors import inject_feature_flags
from opendlp.feature_flags import (
    NEW_DASHBOARD_ENDPOINT,
    OLD_DASHBOARD_ENDPOINT,
    default_dashboard_endpoint,
    old_dashboard_route_enabled,
    reload_flags,
)


@pytest.fixture(autouse=True)
def _clean_dashboard_flags(monkeypatch):
    """Strip the FF_*DASHBOARD vars set by the global conftest so each test starts clean."""
    for key in ("FF_OLD_DEFAULT_DASHBOARD", "FF_DASHBOARD_SWITCH_LINKS"):
        monkeypatch.delenv(key, raising=False)
    reload_flags()
    yield
    reload_flags()


class TestDefaultDashboardEndpoint:
    def test_defaults_to_new_dashboard(self):
        assert default_dashboard_endpoint() == NEW_DASHBOARD_ENDPOINT

    def test_returns_old_when_flag_enabled(self, monkeypatch):
        monkeypatch.setenv("FF_OLD_DEFAULT_DASHBOARD", "true")
        reload_flags()
        assert default_dashboard_endpoint() == OLD_DASHBOARD_ENDPOINT

    def test_returns_new_when_flag_explicitly_false(self, monkeypatch):
        monkeypatch.setenv("FF_OLD_DEFAULT_DASHBOARD", "false")
        reload_flags()
        assert default_dashboard_endpoint() == NEW_DASHBOARD_ENDPOINT


class TestOldDashboardRouteEnabled:
    def test_disabled_when_both_flags_off(self):
        assert old_dashboard_route_enabled() is False

    def test_enabled_when_default_flag_on(self, monkeypatch):
        monkeypatch.setenv("FF_OLD_DEFAULT_DASHBOARD", "true")
        reload_flags()
        assert old_dashboard_route_enabled() is True

    def test_enabled_when_link_flag_on(self, monkeypatch):
        monkeypatch.setenv("FF_DASHBOARD_SWITCH_LINKS", "true")
        reload_flags()
        assert old_dashboard_route_enabled() is True

    def test_enabled_when_both_flags_on(self, monkeypatch):
        monkeypatch.setenv("FF_OLD_DEFAULT_DASHBOARD", "true")
        monkeypatch.setenv("FF_DASHBOARD_SWITCH_LINKS", "true")
        reload_flags()
        assert old_dashboard_route_enabled() is True


class TestFooterOldDashboardLink:
    """Verify the backoffice footer renders the old-dashboard link only when FF_DASHBOARD_SWITCH_LINKS is on."""

    def _render_footer(self) -> str:
        reload_flags()

        templates_dir = os.path.join(os.path.dirname(__file__), "..", "..", "templates")
        app = Flask(__name__, template_folder=templates_dir)
        app.config["TESTING"] = True
        app.context_processor(inject_feature_flags)
        app.jinja_env.globals["_"] = lambda s: s

        main_bp = Blueprint("main", __name__)

        @main_bp.route("/dashboard")
        def dashboard():
            return ""

        app.register_blueprint(main_bp)

        @app.route("/render")
        def render():
            template = "{% from 'backoffice/components/footer.html' import footer with context %}{{ footer() }}"
            return render_template_string(
                template,
                help_site_data_agreement="https://example.com/data",
                help_site_cookies="https://example.com/cookies",
                opendlp_version="test-version",
            )

        with app.test_client() as client:
            response = client.get("/render")
            return response.data.decode("utf-8")

    def test_link_absent_when_flag_off(self, monkeypatch):
        monkeypatch.delenv("FF_DASHBOARD_SWITCH_LINKS", raising=False)
        html = self._render_footer()
        assert "Old Dashboard" not in html

    def test_link_present_when_flag_on(self, monkeypatch):
        monkeypatch.setenv("FF_DASHBOARD_SWITCH_LINKS", "true")
        html = self._render_footer()
        assert "Old Dashboard" in html
        assert "/dashboard" in html

    def test_footer_links_to_cookies_page(self, monkeypatch):
        """The backoffice footer must carry the cookies link, as the GOV.UK footer does."""
        monkeypatch.delenv("FF_DASHBOARD_SWITCH_LINKS", raising=False)
        html = self._render_footer()
        assert "https://example.com/cookies" in html
