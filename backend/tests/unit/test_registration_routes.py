"""ABOUTME: Unit tests for public registration page routes
ABOUTME: Tests feature flag behavior, route responses, and redirect handling"""

import os
from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient

from opendlp.domain.registration_page import (
    RegistrationPage,
    RegistrationPageStatus,
)
from opendlp.entrypoints.blueprints.registration import (
    registration_url,
    registration_url_prefix,
    short_url,
    short_url_prefix,
)
from opendlp.entrypoints.flask_app import create_app
from opendlp.feature_flags import reload_flags
from opendlp.service_layer.registration_page_service import (
    RegistrationPageVisibility,
    RegistrationPageVisibilityState,
)
from opendlp.service_layer.registration_submission_service import (
    RegistrationClosedError,
    RegistrationNotFoundError,
    RegistrationSubmissionResult,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove any FF_* vars that may leak between tests, then reload flags."""
    for key in list(os.environ):
        if key.startswith("FF_"):
            monkeypatch.delenv(key, raising=False)
    reload_flags()
    yield
    reload_flags()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> FlaskClient:
    """Client with FF_REGISTRATION_PAGE enabled."""
    monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
    reload_flags()
    app = create_app("testing")
    return app.test_client()


@pytest.fixture
def client_with_feature_disabled() -> FlaskClient:
    """Client with FF_REGISTRATION_PAGE unset — feature is off by default."""
    app = create_app("testing")
    return app.test_client()


class TestFeatureFlagBehavior:
    """Routes return 404 unless FF_REGISTRATION_PAGE is enabled."""

    def test_show_form_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.get("/register/test-slug")
        assert response.status_code == 404

    def test_submit_form_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.post("/register/test-slug", data={})
        assert response.status_code == 404

    def test_thank_you_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.get("/register/test-slug/thank-you")
        assert response.status_code == 404

    def test_short_url_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.get("/r/abc123")
        assert response.status_code == 404

    def test_closed_page_returns_404_when_feature_disabled(self, client_with_feature_disabled: FlaskClient) -> None:
        response = client_with_feature_disabled.get("/registration-closed")
        assert response.status_code == 404


class TestBlueprintRegistration:
    """Test that the registration blueprint is properly registered."""

    def test_registration_blueprint_registered(self) -> None:
        app = create_app("testing")
        blueprint_names = [bp.name for bp in app.blueprints.values()]
        assert "registration" in blueprint_names


class TestShowRegistrationForm:
    """Test GET /register/<url_slug> route."""

    def test_returns_404_when_page_not_found(self, client: FlaskClient) -> None:
        with patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find:
            mock_find.return_value = None
            response = client.get("/register/nonexistent")
            assert response.status_code == 404

    def test_redirects_to_closed_page_when_closed(self, client: FlaskClient) -> None:
        page = MagicMock(spec=RegistrationPage)
        page.url_slug = "test-slug"
        page.status = RegistrationPageStatus.CLOSED

        with (
            patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find,
            patch("opendlp.entrypoints.blueprints.registration.resolve_visibility") as mock_resolve,
        ):
            mock_find.return_value = page
            mock_resolve.return_value = RegistrationPageVisibility(
                page=page, state=RegistrationPageVisibilityState.CLOSED
            )

            response = client.get("/register/test-slug")
            assert response.status_code == 302
            assert "/registration-closed" in response.location

    def test_renders_form_when_live(self, client: FlaskClient) -> None:
        page = MagicMock(spec=RegistrationPage)
        page.url_slug = "test-slug"
        page.status = RegistrationPageStatus.PUBLISHED

        with (
            patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find,
            patch("opendlp.entrypoints.blueprints.registration.resolve_visibility") as mock_resolve,
            patch("opendlp.entrypoints.blueprints.registration.render_registration_form") as mock_render,
            patch("opendlp.entrypoints.blueprints.registration.bootstrap"),
        ):
            mock_find.return_value = page
            mock_resolve.return_value = RegistrationPageVisibility(
                page=page, state=RegistrationPageVisibilityState.LIVE
            )
            mock_render.return_value = "<form>Test Form</form>"

            response = client.get("/register/test-slug")
            assert response.status_code == 200
            assert b"Test Form" in response.data

    def test_renders_test_banner_when_test_mode(self, client: FlaskClient) -> None:
        page = MagicMock(spec=RegistrationPage)
        page.url_slug = "test-slug"
        page.status = RegistrationPageStatus.TEST

        with (
            patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find,
            patch("opendlp.entrypoints.blueprints.registration.resolve_visibility") as mock_resolve,
            patch("opendlp.entrypoints.blueprints.registration.render_registration_form") as mock_render,
            patch("opendlp.entrypoints.blueprints.registration.bootstrap"),
        ):
            mock_find.return_value = page
            mock_resolve.return_value = RegistrationPageVisibility(
                page=page, state=RegistrationPageVisibilityState.TEST
            )
            mock_render.return_value = "<form>Test Form</form>"

            response = client.get("/register/test-slug")
            assert response.status_code == 200
            assert b"Test Mode" in response.data


class TestSubmitRegistrationForm:
    """Test POST /register/<url_slug> route."""

    def test_returns_404_when_page_not_found(self, client: FlaskClient) -> None:
        with patch("opendlp.entrypoints.blueprints.registration.submit_registration") as mock_submit:
            mock_submit.side_effect = RegistrationNotFoundError("Not found")
            response = client.post("/register/nonexistent", data={})
            assert response.status_code == 404

    def test_redirects_to_closed_when_closed(self, client: FlaskClient) -> None:
        with patch("opendlp.entrypoints.blueprints.registration.submit_registration") as mock_submit:
            mock_submit.side_effect = RegistrationClosedError("Closed")
            response = client.post("/register/closed-slug", data={})
            assert response.status_code == 302
            assert "/registration-closed" in response.location

    def test_redirects_to_thank_you_on_valid_submission(self, client: FlaskClient) -> None:
        result = RegistrationSubmissionResult(
            respondent=MagicMock(),
            values={},
            field_errors={},
            form_errors=[],
            is_test=False,
        )

        with (
            patch("opendlp.entrypoints.blueprints.registration.submit_registration") as mock_submit,
            patch("opendlp.entrypoints.blueprints.registration.send_registration_auto_reply"),
        ):
            mock_submit.return_value = result
            response = client.post("/register/valid-slug", data={"name": "Test"})
            assert response.status_code == 302
            assert "/register/valid-slug/thank-you" in response.location

    def test_re_renders_form_with_errors_on_invalid_submission(self, client: FlaskClient) -> None:
        result = RegistrationSubmissionResult(
            respondent=None,
            values={"name": "Test"},
            field_errors={"email": ["Invalid email"]},
            form_errors=[],
            is_test=False,
        )

        page = MagicMock(spec=RegistrationPage)
        page.url_slug = "test-slug"
        page.status = RegistrationPageStatus.PUBLISHED

        with (
            patch("opendlp.entrypoints.blueprints.registration.submit_registration") as mock_submit,
            patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find,
            patch("opendlp.entrypoints.blueprints.registration.resolve_visibility") as mock_resolve,
            patch("opendlp.entrypoints.blueprints.registration.render_registration_form") as mock_render,
            patch("opendlp.entrypoints.blueprints.registration.bootstrap"),
        ):
            mock_submit.return_value = result
            mock_find.return_value = page
            mock_resolve.return_value = RegistrationPageVisibility(
                page=page, state=RegistrationPageVisibilityState.LIVE
            )
            mock_render.return_value = "<form>Form with errors</form>"

            response = client.post("/register/test-slug", data={"name": "Test"})
            assert response.status_code == 200
            # Verify the form was re-rendered with the failed submission's state
            render_kwargs = mock_render.call_args.kwargs
            assert render_kwargs["errors"] == {"email": ["Invalid email"]}
            assert render_kwargs["values"] == {"name": "Test"}


class TestAutoReplyWiring:
    """The blueprint triggers the auto-reply send after a valid submission."""

    def test_valid_submission_triggers_auto_reply(self, client: FlaskClient) -> None:
        respondent = MagicMock()
        result = RegistrationSubmissionResult(
            respondent=respondent, values={}, field_errors={}, form_errors=[], is_test=False
        )
        with (
            patch("opendlp.entrypoints.blueprints.registration.submit_registration") as mock_submit,
            patch("opendlp.entrypoints.blueprints.registration.send_registration_auto_reply") as mock_auto_reply,
        ):
            mock_submit.return_value = result
            client.post("/register/valid-slug", data={"name": "Test"})

            mock_auto_reply.assert_called_once()
            assert mock_auto_reply.call_args.kwargs["respondent"] is respondent
            assert mock_auto_reply.call_args.kwargs["assembly_id"] == respondent.assembly_id

    def test_invalid_submission_does_not_trigger_auto_reply(self, client: FlaskClient) -> None:
        result = RegistrationSubmissionResult(
            respondent=None,
            values={"name": "Test"},
            field_errors={"email": ["Invalid email"]},
            form_errors=[],
            is_test=False,
        )
        page = MagicMock(spec=RegistrationPage)
        page.url_slug = "test-slug"
        page.status = RegistrationPageStatus.PUBLISHED

        with (
            patch("opendlp.entrypoints.blueprints.registration.submit_registration") as mock_submit,
            patch("opendlp.entrypoints.blueprints.registration.send_registration_auto_reply") as mock_auto_reply,
            patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find,
            patch("opendlp.entrypoints.blueprints.registration.resolve_visibility") as mock_resolve,
            patch("opendlp.entrypoints.blueprints.registration.render_registration_form") as mock_render,
            patch("opendlp.entrypoints.blueprints.registration.bootstrap"),
        ):
            mock_submit.return_value = result
            mock_find.return_value = page
            mock_resolve.return_value = RegistrationPageVisibility(
                page=page, state=RegistrationPageVisibilityState.LIVE
            )
            mock_render.return_value = "<form>errors</form>"

            client.post("/register/test-slug", data={"name": "Test"})

            mock_auto_reply.assert_not_called()


class TestThankYouPage:
    """Test GET /register/<url_slug>/thank-you route."""

    def test_returns_404_when_page_not_found(self, client: FlaskClient) -> None:
        with patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find:
            mock_find.return_value = None
            response = client.get("/register/nonexistent/thank-you")
            assert response.status_code == 404

    def test_renders_default_thank_you_when_no_custom_html(self, client: FlaskClient) -> None:
        page = MagicMock(spec=RegistrationPage)
        page.url_slug = "test-slug"

        with (
            patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find,
            patch("opendlp.entrypoints.blueprints.registration.render_thank_you_html") as mock_render,
            patch("opendlp.entrypoints.blueprints.registration.bootstrap"),
        ):
            mock_find.return_value = page
            mock_render.return_value = ""  # No custom HTML

            response = client.get("/register/test-slug/thank-you")
            assert response.status_code == 200
            assert b"Thank you for registering" in response.data

    def test_renders_custom_thank_you_when_provided(self, client: FlaskClient) -> None:
        page = MagicMock(spec=RegistrationPage)
        page.url_slug = "test-slug"

        with (
            patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_url_slug") as mock_find,
            patch("opendlp.entrypoints.blueprints.registration.render_thank_you_html") as mock_render,
            patch("opendlp.entrypoints.blueprints.registration.bootstrap"),
        ):
            mock_find.return_value = page
            mock_render.return_value = "<h1>Custom Thank You</h1>"

            response = client.get("/register/test-slug/thank-you")
            assert response.status_code == 200
            assert b"Custom Thank You" in response.data


class TestShortUrlRedirect:
    """Test GET /r/<short_url_slug> route."""

    def test_returns_404_when_page_not_found(self, client: FlaskClient) -> None:
        with patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_short_url_slug") as mock_find:
            mock_find.return_value = None
            response = client.get("/r/nonexistent")
            assert response.status_code == 404

    def test_returns_404_when_page_has_no_url_slug(self, client: FlaskClient) -> None:
        page = MagicMock(spec=RegistrationPage)
        page.url_slug = ""  # No URL slug set

        with patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_short_url_slug") as mock_find:
            mock_find.return_value = page
            response = client.get("/r/abc123")
            assert response.status_code == 404

    def test_redirects_to_canonical_url_with_302(self, client: FlaskClient) -> None:
        page = MagicMock(spec=RegistrationPage)
        page.url_slug = "full-slug"

        with patch("opendlp.entrypoints.blueprints.registration.find_registration_page_by_short_url_slug") as mock_find:
            mock_find.return_value = page
            response = client.get("/r/abc")
            assert response.status_code == 302
            assert "/register/full-slug" in response.location


class TestRegistrationClosed:
    """Test GET /registration-closed route."""

    def test_renders_closed_page(self, client: FlaskClient) -> None:
        response = client.get("/registration-closed")
        assert response.status_code == 200
        assert b"Registration Closed" in response.data


class TestUrlHelpers:
    """The URL helpers derive their paths from the registered route rules."""

    def test_registration_url_matches_route(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
        reload_flags()
        app = create_app("testing")
        with app.test_request_context("http://example.org/"):
            assert registration_url("my-slug") == "http://example.org/register/my-slug"
            assert short_url("ma26") == "http://example.org/r/ma26"

    def test_prefixes_are_urls_without_a_slug(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FF_REGISTRATION_PAGE", "true")
        reload_flags()
        app = create_app("testing")
        with app.test_request_context("http://example.org/"):
            assert registration_url_prefix() == "http://example.org/register/"
            assert short_url_prefix() == "http://example.org/r/"
