# ABOUTME: Component tests for the backoffice registration view's read-only / edit-mode toggle
# ABOUTME: Drives the real Flask route + services over a FakeUnitOfWork via a logged-in client

from unittest.mock import patch

import pytest

from opendlp.domain.registration_page import (
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageStatus,
)
from tests.fakes import FakeUnitOfWork


def _seed_page(fake_store, assembly_id, status, *, url_slug="my-slug", form_html="<p>hi</p>"):
    page = RegistrationPage(assembly_id=assembly_id, url_slug=url_slug, status=status)
    html = RegistrationPageHtml(registration_page_id=page.id, form_html=form_html)
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(html)
        uow.commit()
    return page


def _extract_textarea(body: str) -> str:
    assert 'name="html_content"' in body, "html_content textarea missing from body"
    after_name = body.split('name="html_content"', 1)[1]
    return after_name.split(">", 1)[0]


@pytest.fixture
def assembly_id(existing_assembly):
    return existing_assembly.id


class TestViewEditModeFlag:
    def test_default_test_status_is_read_only(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True))

    def test_edit_param_enables_edit_in_test_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        assert "readonly" not in _extract_textarea(response.get_data(as_text=True))

    def test_edit_param_enables_edit_in_published_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        assert "readonly" not in _extract_textarea(response.get_data(as_text=True))

    def test_edit_param_is_ignored_in_closed_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True))

    def test_edit_param_other_values_do_not_enable_edit(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration?edit=true")

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True))


class TestEditModeRendersExpectedHtml:
    def test_test_status_read_only_has_readonly_textarea_and_edit_link(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" in _extract_textarea(body)
        # Edit link points at the section-scoped edit URL
        assert f"/backoffice/assembly/{assembly_id}/registration?section=form&amp;edit=1" in body
        # Next → CTA advances to the auto-reply email step
        assert f"/backoffice/assembly/{assembly_id}/registration?section=email" in body
        assert "Cancel</a>" not in body

    def test_test_status_edit_mode_shows_save_and_next_buttons(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" not in _extract_textarea(body)
        assert "Cancel</span></a>" in body
        assert "Save</span></button>" in body
        assert "Save and next →</span></button>" in body
        # Cancel returns to read-only on the form step
        cancel_block = body.split("Cancel</span></a>", 1)[0]
        anchor = cancel_block.rsplit("<a", 1)[1]
        assert f"/backoffice/assembly/{assembly_id}/registration" in anchor
        assert "edit=1" not in anchor

    def test_published_status_edit_mode_uses_save_and_republish_label(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" not in _extract_textarea(body)
        assert "Save and Republish" in body
        assert "Cancel</span></a>" in body

    def test_closed_status_ignores_edit_param(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" in _extract_textarea(body)
        assert "Edit</a>" not in body
        assert "Cancel</a>" not in body


class TestViewPermissions:
    def test_non_member_is_redirected(self, logged_in_user, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_user.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 302


class TestSaveRedirectPreservesEditMode:
    def test_save_success_redirects_to_read_only(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/save",
            data={"action": "save", "html_content": "<p>updated body</p>"},
        )

        assert response.status_code == 302
        assert f"/backoffice/assembly/{assembly_id}/registration" in response.location
        assert "edit=1" not in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_page_html_sources.get_by_page_id(page.id)
        assert stored.form_html == "<p>updated body</p>"

    def test_save_value_error_redirects_back_in_edit_mode(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        with patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.update_registration_page_html",
            side_effect=ValueError("bad html"),
        ):
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_id}/registration/save",
                data={"action": "save", "html_content": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "edit=1" in response.location

    def test_save_unexpected_error_redirects_back_in_edit_mode(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        with patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.update_registration_page_html",
            side_effect=RuntimeError("boom"),
        ):
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_id}/registration/save",
                data={"action": "save", "html_content": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "edit=1" in response.location

    def test_publish_action_error_does_not_force_edit_mode(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        with patch(
            "opendlp.entrypoints.blueprints.backoffice_registration._handle_registration_action",
            side_effect=RegistrationPageNotReady(["missing field"]),
        ):
            response = logged_in_admin.post(
                f"/backoffice/assembly/{assembly_id}/registration/save",
                data={"action": "publish", "html_content": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "edit=1" not in response.location


class TestCodeEditorEnhancement:
    """The HTML textareas opt into the CodeMirror progressive enhancement."""

    def test_html_content_textarea_marked_for_code_editor_in_read_only(self, logged_in_admin, fake_store, assembly_id):
        """Read-only view still tags the textarea so it renders highlighted (Q4)."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        textarea = _extract_textarea(response.get_data(as_text=True))
        assert "data-code-editor" in textarea
        assert "readonly" in textarea

    def test_html_content_textarea_marked_for_code_editor_in_edit_mode(self, logged_in_admin, fake_store, assembly_id):
        """Edit mode tags the textarea and leaves it editable."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration?edit=1")

        assert response.status_code == 200
        textarea = _extract_textarea(response.get_data(as_text=True))
        assert "data-code-editor" in textarea
        assert "readonly" not in textarea

    def test_editor_bundle_is_loaded_on_the_page(self, logged_in_admin, fake_store, assembly_id):
        """The CodeMirror bundle is referenced so the enhancement can run."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        assert "backoffice/js/dist/html-editor.js" in response.get_data(as_text=True)
