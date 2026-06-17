"""ABOUTME: Unit tests for the registration view's read-only / edit-mode toggle
ABOUTME: Covers the ?edit=1 query param and how save errors preserve edit mode"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from flask_login import AnonymousUserMixin

from opendlp.domain.assembly import Assembly
from opendlp.domain.registration_page import (
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageStatus,
)
from opendlp.entrypoints.flask_app import create_app


class _FakeAnonymous(AnonymousUserMixin):
    """Anonymous user stand-in so backoffice templates can resolve
    ``current_user.global_role.value`` while LOGIN_DISABLED bypasses login_required."""

    id = uuid.uuid4()

    @property
    def global_role(self):  # type: ignore[no-untyped-def]
        role = MagicMock()
        role.value = "user"
        return role


@pytest.fixture
def app():
    a = create_app("testing")
    a.config["LOGIN_DISABLED"] = True
    a.login_manager.anonymous_user = _FakeAnonymous  # type: ignore[attr-defined]
    return a


@pytest.fixture
def authed_client(app):
    return app.test_client()


@pytest.fixture
def assembly_id() -> uuid.UUID:
    return uuid.uuid4()


def _nav_context(assembly_id: uuid.UUID) -> MagicMock:
    """Stand-in for AssemblyNavContext — only the bits the view passes through."""
    nav = MagicMock()
    nav.assembly = Assembly(title="Test Assembly", assembly_id=assembly_id)
    nav.gsheet = None
    nav.data_source = ""
    nav.targets_enabled = False
    nav.respondents_enabled = False
    nav.selection_enabled = False
    return nav


def _page_and_html(
    assembly_id: uuid.UUID,
    status: RegistrationPageStatus,
) -> tuple[RegistrationPage, RegistrationPageHtml]:
    page = RegistrationPage(assembly_id=assembly_id, url_slug="my-slug", status=status)
    return page, RegistrationPageHtml(registration_page_id=page.id, form_html="<p>hi</p>")


class TestViewEditModeFlag:
    """The route computes edit_mode from ?edit=1 and the current status."""

    def _patches(self, status: RegistrationPageStatus, assembly_id: uuid.UUID):
        return (
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.current_user",
                new=MagicMock(id=uuid.uuid4()),
            ),
            patch("opendlp.entrypoints.blueprints.backoffice_registration.bootstrap.bootstrap"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.get_assembly_nav_context",
                return_value=_nav_context(assembly_id),
            ),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.get_registration_page_with_source",
                return_value=_page_and_html(assembly_id, status),
            ),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.list_registration_images",
                return_value=[],
            ),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.render_template",
                return_value="ok",
            ),
        )

    def _edit_mode_kwarg(self, render_mock: MagicMock) -> bool:
        assert render_mock.called, "render_template was not called"
        _, kwargs = render_mock.call_args
        return bool(kwargs.get("edit_mode"))

    def test_default_test_status_is_read_only(self, authed_client, assembly_id):
        p = self._patches(RegistrationPageStatus.TEST, assembly_id)
        with p[0], p[1], p[2], p[3], p[4], p[5] as render_template:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        assert self._edit_mode_kwarg(render_template) is False

    def test_edit_param_enables_edit_in_test_status(self, authed_client, assembly_id):
        p = self._patches(RegistrationPageStatus.TEST, assembly_id)
        with p[0], p[1], p[2], p[3], p[4], p[5] as render_template:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        assert self._edit_mode_kwarg(render_template) is True

    def test_edit_param_enables_edit_in_published_status(self, authed_client, assembly_id):
        p = self._patches(RegistrationPageStatus.PUBLISHED, assembly_id)
        with p[0], p[1], p[2], p[3], p[4], p[5] as render_template:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        assert self._edit_mode_kwarg(render_template) is True

    def test_edit_param_is_ignored_in_closed_status(self, authed_client, assembly_id):
        # CLOSED has no save path so ?edit=1 should NOT unlock the editor.
        p = self._patches(RegistrationPageStatus.CLOSED, assembly_id)
        with p[0], p[1], p[2], p[3], p[4], p[5] as render_template:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        assert self._edit_mode_kwarg(render_template) is False

    def test_edit_param_other_values_do_not_enable_edit(self, authed_client, assembly_id):
        # Only the canonical ?edit=1 unlocks the editor — defensive against random truthy values.
        p = self._patches(RegistrationPageStatus.TEST, assembly_id)
        with p[0], p[1], p[2], p[3], p[4], p[5] as render_template:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration?edit=true")

        assert response.status_code == 200
        assert self._edit_mode_kwarg(render_template) is False


def _patches_with_full_render(status: RegistrationPageStatus, assembly_id: uuid.UUID):
    """Same patches as TestViewEditModeFlag but WITHOUT mocking render_template, so
    the test exercises the real Jinja output. Used to assert on textarea readonly,
    Edit/Cancel buttons, and the disabled status dropdown."""
    page = RegistrationPage(assembly_id=assembly_id, url_slug="my-slug", status=status)
    html = RegistrationPageHtml(registration_page_id=page.id, form_html="<p>hi</p>")
    return (
        patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.current_user",
            new=MagicMock(id=uuid.uuid4()),
        ),
        patch("opendlp.entrypoints.blueprints.backoffice_registration.bootstrap.bootstrap"),
        patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.get_assembly_nav_context",
            return_value=_nav_context(assembly_id),
        ),
        patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.get_registration_page_with_source",
            return_value=(page, html),
        ),
        patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.list_registration_images",
            return_value=[],
        ),
    )


def _extract_textarea(body: str) -> str:
    """Pluck the html_content textarea's opening tag for targeted assertions."""
    assert 'name="html_content"' in body, "html_content textarea missing from body"
    after_name = body.split('name="html_content"', 1)[1]
    tag_inner = after_name.split(">", 1)[0]
    return tag_inner


class TestEditModeRendersExpectedHtml:
    """End-to-end: render the actual template and assert on the produced HTML."""

    def test_test_status_read_only_has_readonly_textarea_and_edit_link(self, authed_client, assembly_id):
        p = _patches_with_full_render(RegistrationPageStatus.TEST, assembly_id)
        with p[0], p[1], p[2], p[3], p[4]:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # Textarea is read-only
        assert "readonly" in _extract_textarea(body)
        # Edit CTA links to ?edit=1
        assert f"/backoffice/assembly/{assembly_id}/registration?edit=1" in body
        # No Cancel button while read-only
        # The footer Cancel is rendered as an <a> (it has href); image-modal Cancels
        # are <button>s. Asserting on </a> scopes us to the footer link.
        assert "Cancel</a>" not in body
        # Status dropdown is NOT disabled while read-only
        assert 'id="status-control-toggle"' in body
        toggle_attrs = body.split('id="status-control-toggle"', 1)[1].split(">", 1)[0]
        assert "disabled" not in toggle_attrs

    def test_test_status_edit_mode_unlocks_textarea_and_disables_dropdown(self, authed_client, assembly_id):
        p = _patches_with_full_render(RegistrationPageStatus.TEST, assembly_id)
        with p[0], p[1], p[2], p[3], p[4]:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # Textarea is editable
        assert "readonly" not in _extract_textarea(body)
        # Cancel (anchor) + Save (submit button) are present
        assert "Cancel</a>" in body
        assert "Save</button>" in body
        # Status dropdown is disabled
        assert 'id="status-control-toggle"' in body
        toggle_attrs = body.split('id="status-control-toggle"', 1)[1].split(">", 1)[0]
        assert "disabled" in toggle_attrs
        # Cancel links back to the read-only URL (no edit=1)
        cancel_block = body.split("Cancel</a>", 1)[0]
        anchor = cancel_block.rsplit("<a", 1)[1]
        assert f"/backoffice/assembly/{assembly_id}/registration" in anchor
        assert "edit=1" not in anchor

    def test_published_status_edit_mode_uses_save_and_republish_label(self, authed_client, assembly_id):
        p = _patches_with_full_render(RegistrationPageStatus.PUBLISHED, assembly_id)
        with p[0], p[1], p[2], p[3], p[4]:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" not in _extract_textarea(body)
        assert "Save and Republish" in body
        assert "Cancel</a>" in body

    def test_closed_status_ignores_edit_param(self, authed_client, assembly_id):
        p = _patches_with_full_render(RegistrationPageStatus.CLOSED, assembly_id)
        with p[0], p[1], p[2], p[3], p[4]:
            response = authed_client.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # Stays read-only
        assert "readonly" in _extract_textarea(body)
        # No Edit and no footer Cancel — admins must reopen via the status dropdown first
        assert "Edit</a>" not in body
        # The footer Cancel is rendered as an <a> (it has href); image-modal Cancels
        # are <button>s. Asserting on </a> scopes us to the footer link.
        assert "Cancel</a>" not in body


class TestSaveRedirectPreservesEditMode:
    """Save success drops ?edit=1; errors during a save keep the user in edit mode."""

    def _patch_save(self):
        return (
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.current_user",
                new=MagicMock(id=uuid.uuid4()),
            ),
            patch("opendlp.entrypoints.blueprints.backoffice_registration.bootstrap.bootstrap"),
            patch("opendlp.entrypoints.blueprints.backoffice_registration.get_assembly_nav_context"),
        )

    def test_save_success_redirects_to_read_only(self, authed_client, assembly_id):
        p = self._patch_save()
        with (
            p[0],
            p[1],
            p[2],
            patch("opendlp.entrypoints.blueprints.backoffice_registration.update_registration_page_html"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration._handle_registration_action",
                return_value="saved",
            ),
        ):
            response = authed_client.post(
                f"/backoffice/assembly/{assembly_id}/registration/save",
                data={"action": "save", "html_content": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert f"/backoffice/assembly/{assembly_id}/registration" in response.location
        assert "edit=1" not in response.location

    def test_save_value_error_redirects_back_in_edit_mode(self, authed_client, assembly_id):
        p = self._patch_save()
        with (
            p[0],
            p[1],
            p[2],
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.update_registration_page_html",
                side_effect=ValueError("bad html"),
            ),
        ):
            response = authed_client.post(
                f"/backoffice/assembly/{assembly_id}/registration/save",
                data={"action": "save", "html_content": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "edit=1" in response.location

    def test_save_unexpected_error_redirects_back_in_edit_mode(self, authed_client, assembly_id):
        p = self._patch_save()
        with (
            p[0],
            p[1],
            p[2],
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration.update_registration_page_html",
                side_effect=RuntimeError("boom"),
            ),
        ):
            response = authed_client.post(
                f"/backoffice/assembly/{assembly_id}/registration/save",
                data={"action": "save", "html_content": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "edit=1" in response.location

    def test_publish_action_error_does_not_force_edit_mode(self, authed_client, assembly_id):
        # Status transitions only fire from read-only (the dropdown is disabled in edit mode),
        # so an error landing back on the registration page keeps the user in read-only.
        p = self._patch_save()
        with (
            p[0],
            p[1],
            p[2],
            patch("opendlp.entrypoints.blueprints.backoffice_registration.update_registration_page_html"),
            patch(
                "opendlp.entrypoints.blueprints.backoffice_registration._handle_registration_action",
                side_effect=RegistrationPageNotReady(["missing field"]),
            ),
        ):
            response = authed_client.post(
                f"/backoffice/assembly/{assembly_id}/registration/save",
                data={"action": "publish", "html_content": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "edit=1" not in response.location
