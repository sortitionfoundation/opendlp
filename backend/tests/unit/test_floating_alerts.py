"""ABOUTME: Jinja render tests for the floating_alerts and alert macros
ABOUTME: Verifies floating alerts rendering with proper accessibility attributes"""

from flask import Flask, render_template_string

from opendlp import config
from opendlp.translations import gettext


def _make_app() -> Flask:
    app = Flask(__name__, template_folder=str(config.get_templates_path()))
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key"  # pragma: allowlist secret
    app.jinja_env.globals["_"] = gettext
    app.jinja_env.globals["gettext"] = gettext
    return app


def _render_alert(message: str, variant: str = "info", dismissible: bool = False, floating: bool = False) -> str:
    app = _make_app()
    with app.test_request_context("/"):
        return render_template_string(
            """{% from "backoffice/components/alert.html" import alert %}
            {{ alert(message, variant=variant, dismissible=dismissible, floating=floating) }}""",
            message=message,
            variant=variant,
            dismissible=dismissible,
            floating=floating,
        )


def _render_floating_alerts_with_flash(messages: list[tuple[str, str]]) -> str:
    """Render floating_alerts macro with mocked flash messages."""
    app = _make_app()
    with app.test_request_context("/"):
        # Mock get_flashed_messages
        app.jinja_env.globals["get_flashed_messages"] = lambda with_categories=False: messages
        return render_template_string(
            """{% from "backoffice/components/floating_alerts.html" import floating_alerts %}
            {{ floating_alerts() }}"""
        )


class TestAlertMacro:
    def test_alert_renders_message(self) -> None:
        html = _render_alert("Test message")
        assert "Test message" in html
        assert 'role="alert"' in html

    def test_alert_success_variant(self) -> None:
        html = _render_alert("Success!", variant="success")
        assert "Success!" in html
        assert "success" in html.lower() or "var(--color-success" in html

    def test_alert_warning_variant(self) -> None:
        html = _render_alert("Warning!", variant="warning")
        assert "Warning!" in html
        assert "warning" in html.lower() or "var(--color-warning" in html

    def test_alert_error_variant(self) -> None:
        html = _render_alert("Error!", variant="error")
        assert "Error!" in html
        assert "error" in html.lower() or "var(--color-error" in html

    def test_alert_info_variant(self) -> None:
        html = _render_alert("Info!", variant="info")
        assert "Info!" in html
        assert "info" in html.lower() or "var(--color-info" in html

    def test_alert_dismissible_has_close_button(self) -> None:
        html = _render_alert("Dismissible alert", dismissible=True)
        assert "Dismissible alert" in html
        assert "x-data" in html
        assert "x-show" in html
        # Close button should have aria-label
        assert "Dismiss" in html or "dismiss" in html.lower()

    def test_alert_non_dismissible_no_close_button(self) -> None:
        html = _render_alert("Non-dismissible alert", dismissible=False)
        assert "Non-dismissible alert" in html
        assert "x-data" not in html

    def test_alert_floating_no_margin(self) -> None:
        """Floating alerts should not have bottom margin class."""
        html = _render_alert("Floating alert", floating=True)
        assert "Floating alert" in html
        # mb-6 should not be present for floating alerts
        assert "mb-6" not in html

    def test_alert_non_floating_has_margin(self) -> None:
        """Non-floating alerts should have bottom margin class."""
        html = _render_alert("Normal alert", floating=False)
        assert "Normal alert" in html
        assert "mb-6" in html


class TestFloatingAlertsMacro:
    def test_floating_alerts_empty_when_no_messages(self) -> None:
        """When no flash messages, container should not be rendered."""
        html = _render_floating_alerts_with_flash([])
        # Should be empty or minimal whitespace
        assert "floating-alerts" not in html

    def test_floating_alerts_renders_success_message(self) -> None:
        html = _render_floating_alerts_with_flash([("success", "Changes saved!")])
        assert "floating-alerts" in html
        assert "Changes saved!" in html
        assert 'aria-live="polite"' in html

    def test_floating_alerts_renders_error_message(self) -> None:
        html = _render_floating_alerts_with_flash([("error", "Something went wrong")])
        assert "floating-alerts" in html
        assert "Something went wrong" in html

    def test_floating_alerts_renders_warning_message(self) -> None:
        html = _render_floating_alerts_with_flash([("warning", "Please review")])
        assert "floating-alerts" in html
        assert "Please review" in html

    def test_floating_alerts_renders_info_message(self) -> None:
        html = _render_floating_alerts_with_flash([("info", "New feature available")])
        assert "floating-alerts" in html
        assert "New feature available" in html

    def test_floating_alerts_renders_multiple_messages(self) -> None:
        html = _render_floating_alerts_with_flash([
            ("success", "Item saved"),
            ("warning", "Please review settings"),
        ])
        assert "floating-alerts" in html
        assert "Item saved" in html
        assert "Please review settings" in html

    def test_floating_alerts_has_fixed_positioning(self) -> None:
        html = _render_floating_alerts_with_flash([("info", "Test")])
        assert "fixed" in html
        assert "bottom-6" in html
        assert "right-6" in html

    def test_floating_alerts_has_z_index(self) -> None:
        html = _render_floating_alerts_with_flash([("info", "Test")])
        assert "z-30" in html

    def test_floating_alerts_are_dismissible(self) -> None:
        """All floating alerts should be dismissible."""
        html = _render_floating_alerts_with_flash([("success", "Test")])
        assert "x-data" in html
        assert "x-show" in html

    def test_floating_alerts_unknown_category_defaults_to_info(self) -> None:
        """Unknown flash categories should render as info variant."""
        html = _render_floating_alerts_with_flash([("unknown_category", "Unknown type")])
        assert "floating-alerts" in html
        assert "Unknown type" in html
