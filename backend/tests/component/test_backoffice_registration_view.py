# ABOUTME: Component tests for the backoffice registration view's read-only / edit-mode toggle
# ABOUTME: Drives the real Flask route + services over a FakeUnitOfWork via a logged-in client

import uuid
from unittest.mock import patch

import pytest

from opendlp.domain.registration_page import (
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageStatus,
)
from tests.fakes import FakeUnitOfWork


def _seed_page(
    fake_store, assembly_id, status, *, url_slug="my-slug", form_html="<p>hi</p>", name="English", language=""
):
    page = RegistrationPage(assembly_id=assembly_id, url_slug=url_slug, status=status, name=name, language=language)
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

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug")

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True))

    def test_edit_param_enables_edit_in_test_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1")

        assert response.status_code == 200
        assert "readonly" not in _extract_textarea(response.get_data(as_text=True))

    def test_edit_param_enables_edit_in_published_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1")

        assert response.status_code == 200
        assert "readonly" not in _extract_textarea(response.get_data(as_text=True))

    def test_edit_param_is_ignored_in_closed_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1")

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True))

    def test_edit_param_other_values_do_not_enable_edit(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=true")

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True))


class TestEditModeRendersExpectedHtml:
    def test_test_status_read_only_has_readonly_textarea_and_edit_link(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" in _extract_textarea(body)
        # Edit link points at the section-scoped edit URL
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form&amp;edit=1" in body
        # Next → CTA advances to the auto-reply email step
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=email" in body
        assert "Cancel</a>" not in body

    def test_test_status_edit_mode_shows_header_save_controls(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" not in _extract_textarea(body)
        assert "Cancel</span></a>" in body
        assert "Save</span></button>" in body
        # Save-and-next is gone: the footer is navigation only, and it locks while editing
        assert "Save and next" not in body
        assert "Editing in progress" in body
        # Cancel returns to read-only on the form step
        cancel_block = body.split("Cancel</span></a>", 1)[0]
        anchor = cancel_block.rsplit("<a", 1)[1]
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug" in anchor
        assert "edit=1" not in anchor

    def test_edit_mode_disables_the_stepper_navigation(self, logged_in_admin, fake_store, assembly_id):
        """While editing, the stepper renders aria-disabled spans instead of links."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        view_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug").get_data(
            as_text=True
        )
        edit_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1").get_data(
            as_text=True
        )

        def stepper_markup(body: str) -> str:
            return body.split('class="stepper"', 1)[1].split("</ol>", 1)[0]

        assert "<a href" in stepper_markup(view_body)
        assert "<a href" not in stepper_markup(edit_body)
        assert stepper_markup(edit_body).count('aria-disabled="true"') == 3

    def test_view_mode_hides_assets_panel_and_edit_mode_shows_it(self, logged_in_admin, fake_store, assembly_id):
        """The Assets panel is an editing tool, so it only renders in edit mode."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        view_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug").get_data(
            as_text=True
        )
        edit_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1").get_data(
            as_text=True
        )

        assert ">Assets</h2>" not in view_body
        assert ">Assets</h2>" in edit_body

    def test_published_status_edit_mode_uses_save_and_republish_label(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" not in _extract_textarea(body)
        assert "Save and Republish" in body
        assert "Cancel</span></a>" in body

    def test_closed_status_ignores_edit_param(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" in _extract_textarea(body)
        assert "Edit</a>" not in body
        assert "Cancel</a>" not in body


class TestViewPermissions:
    def test_non_member_is_redirected(self, logged_in_user, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_user.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug")

        assert response.status_code == 302


class TestSaveRedirectPreservesEditMode:
    def test_save_success_redirects_to_read_only(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "html_content": "<p>updated body</p>"},
        )

        assert response.status_code == 302
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug" in response.location
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
                f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
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
                f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
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
                f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
                data={"action": "publish", "html_content": "<p>x</p>"},
            )

        assert response.status_code == 302
        assert "edit=1" not in response.location


class TestCodeEditorEnhancement:
    """The HTML textareas opt into the CodeMirror progressive enhancement."""

    def test_html_content_textarea_marked_for_code_editor_in_read_only(self, logged_in_admin, fake_store, assembly_id):
        """Read-only view still tags the textarea so it renders highlighted (Q4)."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug")

        assert response.status_code == 200
        textarea = _extract_textarea(response.get_data(as_text=True))
        assert "data-code-editor" in textarea
        assert "readonly" in textarea

    def test_html_content_textarea_marked_for_code_editor_in_edit_mode(self, logged_in_admin, fake_store, assembly_id):
        """Edit mode tags the textarea and leaves it editable."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1")

        assert response.status_code == 200
        textarea = _extract_textarea(response.get_data(as_text=True))
        assert "data-code-editor" in textarea
        assert "readonly" not in textarea

    def test_editor_bundle_is_loaded_on_the_page(self, logged_in_admin, fake_store, assembly_id):
        """The CodeMirror bundle is referenced so the enhancement can run."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug")

        assert response.status_code == 200
        assert "backoffice/js/dist/html-editor.js" in response.get_data(as_text=True)


_PREVIEWABLE_FORM = (
    '<form action="{{ form_action }}" method="post">'
    "{{ csrf_form_element }}"
    '<label for="fn">First name</label><input id="fn" name="first_name" />'
    '<button type="submit">Register</button>'
    "</form>"
)


class TestFormPreviewRoute:
    """The embedded read-only preview of the saved registration form (preview step)."""

    def test_preview_renders_saved_form_with_submission_disabled(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html=_PREVIEWABLE_FORM)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug/form-preview")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # The saved form renders through the public pipeline...
        assert 'name="first_name"' in body
        assert ">Register</button>" in body
        # ...but submission is neutralised: empty action, blocking script, no security fields
        assert 'action=""' in body
        assert "preview: submission disabled" in body
        assert 'name="csrf_token"' not in body
        assert "_opendlp_ttoken_" not in body

    def test_preview_is_framable_by_same_origin_only(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html=_PREVIEWABLE_FORM)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug/form-preview")

        assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
        assert "frame-ancestors 'self'" in response.headers.get("Content-Security-Policy", "")

    def test_preview_404_without_registration_page(self, logged_in_admin, assembly_id):
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug/form-preview")

        assert response.status_code == 404

    def test_preview_404_for_unknown_assembly(self, logged_in_admin):
        response = logged_in_admin.get(f"/backoffice/assembly/{uuid.uuid4()}/registration/my-slug/form-preview")

        assert response.status_code == 404

    def test_preview_500_when_rendering_fails(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html=_PREVIEWABLE_FORM)

        with patch(
            "opendlp.entrypoints.blueprints.backoffice_registration.render_registration_form",
            side_effect=RuntimeError("boom"),
        ):
            response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug/form-preview")

        assert response.status_code == 500

    def test_preview_404_for_non_member(self, logged_in_user, fake_store, assembly_id):
        # Slug lookup masks pages the user cannot view as not-found, so slugs
        # cannot be probed to discover which assemblies exist.
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html=_PREVIEWABLE_FORM)

        response = logged_in_user.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug/form-preview")

        assert response.status_code == 404

    def test_preview_section_embeds_the_preview_iframe(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html=_PREVIEWABLE_FORM)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=preview")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "<iframe" in body
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug/form-preview" in body


class TestLifecycleFooterControls:
    """The preview step's footer offers the lifecycle actions for the current status:
    TEST → Publish; PUBLISHED → Unpublish + Close registration; CLOSED → nothing."""

    def _preview_body(self, logged_in_admin, assembly_id) -> str:
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=preview")
        assert response.status_code == 200
        return response.get_data(as_text=True)

    def test_test_status_offers_publish_only(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = self._preview_body(logged_in_admin, assembly_id)

        assert 'value="publish"' in body
        assert 'value="unpublish"' not in body
        assert "Close registration/my-slug" not in body

    def test_published_status_offers_unpublish_and_close(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        body = self._preview_body(logged_in_admin, assembly_id)

        assert 'value="publish"' not in body
        assert 'value="unpublish"' in body
        assert "Unpublish</span></button>" in body
        assert "Close registration</span></button>" in body
        # Close goes through the confirmation dialog (terminal action, no reopen).
        assert "Close registration?" in body

    def test_closed_status_offers_no_lifecycle_actions(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        body = self._preview_body(logged_in_admin, assembly_id)

        assert 'value="publish"' not in body
        assert 'value="unpublish"' not in body
        assert "Close registration/my-slug" not in body

    def test_publish_publishes_the_page_and_lands_on_the_list(self, logged_in_admin, fake_store, assembly_id):
        # Publishing finishes the editor flow, so it dismisses the editor modal:
        # the redirect goes to the pages list, not back into the editor.
        page = _seed_page(
            fake_store,
            assembly_id,
            RegistrationPageStatus.TEST,
            form_html="<form>{{ csrf_form_element }}{{ form_action }}</form>",
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "publish"},
        )

        assert response.status_code == 302
        assert response.location == f"/backoffice/assembly/{assembly_id}/registration"
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
        assert stored.status == RegistrationPageStatus.PUBLISHED

    def test_unpublish_returns_page_to_test_and_lands_on_preview(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "unpublish"},
        )

        assert response.status_code == 302
        assert "section=preview" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
        assert stored.status == RegistrationPageStatus.TEST

    def test_close_closes_the_page_and_lands_on_the_list(self, logged_in_admin, fake_store, assembly_id):
        # Closing finishes the editor flow, so it dismisses the editor modal:
        # the redirect goes to the pages list, not back into the editor.
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "close"},
        )

        assert response.status_code == 302
        assert response.location == f"/backoffice/assembly/{assembly_id}/registration"
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
        assert stored.status == RegistrationPageStatus.CLOSED

    def test_unknown_action_is_a_plain_save_landing_on_the_form_step(self, logged_in_admin, fake_store, assembly_id):
        # An action outside the save/lifecycle sets carries no HTML and triggers no
        # transition: it falls through to the plain-save path and lands read-only
        # on the form step (no edit=1), leaving the page untouched.
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "bogus"},
        )

        assert response.status_code == 302
        assert "section=form" in response.location
        assert "edit=1" not in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
        assert stored.status == RegistrationPageStatus.PUBLISHED


class TestRegistrationListView:
    def test_lists_every_page_with_links_to_their_editors(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="my-slug", name="English")
        _seed_page(
            fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="my-slug-es", name="Spanish", language="es"
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "English" in body
        assert "Spanish" in body
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug" in body
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug-es" in body

    def test_published_page_shows_its_publish_date(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(
            fake_store,
            assembly_id,
            RegistrationPageStatus.TEST,
            url_slug="pub-slug",
            name="Live",
            form_html="<form>{{ csrf_form_element }} {{ form_action }}</form>",
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
            stored.publish(uow.registration_page_html_sources.get_by_page_id(page.id), author_id=uuid.uuid4())
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        # The publish date renders through the babel dateformat filter (not the em dash placeholder)
        row = body.split("Live", 1)[1].split("</tr>", 1)[0]
        date_cell = row.split('data-cell="published-at"', 1)[1].split("</td>", 1)[0]
        assert "\u2014" not in date_cell

    def test_empty_assembly_offers_page_creation(self, logged_in_admin, fake_store, assembly_id):
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        assert f"/backoffice/assembly/{assembly_id}/registration/create" in response.get_data(as_text=True)

    def test_close_action_offered_only_for_published_pages(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="live-slug", name="Live")
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert f"/backoffice/assembly/{assembly_id}/registration/live-slug/save" in body
        assert f"/backoffice/assembly/{assembly_id}/registration/draft-slug/save" not in body

    def test_create_button_label_reflects_whether_pages_exist(self, logged_in_admin, fake_store, assembly_id):
        empty_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")
        populated_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert "Create registration page" in empty_body
        assert "Create another registration page" not in empty_body
        assert "Create another registration page" in populated_body
        assert "Create HTML page" not in populated_body

    def test_each_row_shows_the_full_and_short_urls(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="climate-en", name="English")
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.registration_pages.get(page.id).update_slugs(short_url_slug="123456")
            uow.commit()

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert "/register/climate-en" in body
        assert "/r/123456" in body

    def test_a_page_without_a_short_url_shows_the_full_url_only(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="climate-en", name="English")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert "/register/climate-en" in body
        assert "Short URL" not in body

    def test_the_short_url_row_carries_a_qr_code(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="climate-en", name="English")
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.registration_pages.get(page.id).update_slugs(short_url_slug="123456")
            uow.commit()

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert "data:image/png;base64," in body
        assert f"/backoffice/assembly/{assembly_id}/registration/climate-en/qr-code.png" in body


class TestRegistrationListDeleteAction:
    def test_delete_offered_for_a_never_published_page(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert f"/backoffice/assembly/{assembly_id}/registration/draft-slug/delete" in body
        assert "Delete this registration page?" in body

    def test_delete_not_offered_for_a_published_page(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="live-slug", name="Live")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert f"/backoffice/assembly/{assembly_id}/registration/live-slug/delete" not in body

    def test_delete_removes_the_page_and_lands_on_the_list(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")

        response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/draft-slug/delete")

        assert response.status_code == 302
        assert response.location.rstrip("/").endswith(f"/backoffice/assembly/{assembly_id}/registration")
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id) is None
            assert uow.registration_page_html_sources.get_by_page_id(page.id) is None

    def test_delete_refuses_a_published_page_and_keeps_it(self, logged_in_admin, fake_store, assembly_id):
        """The list hides the action, but a page published in another tab can still be posted at."""
        page = _seed_page(
            fake_store,
            assembly_id,
            RegistrationPageStatus.TEST,
            url_slug="live-slug",
            name="Live",
            form_html="<form>{{ csrf_form_element }} {{ form_action }}</form>",
        )
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
            stored.publish(uow.registration_page_html_sources.get_by_page_id(page.id), author_id=uuid.uuid4())
            uow.commit()

        response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/live-slug/delete")

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id) is not None

    def test_delete_of_an_unknown_slug_lands_on_the_list(self, logged_in_admin, fake_store, assembly_id):
        response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/nope/delete")

        assert response.status_code == 302
        assert response.location.rstrip("/").endswith(f"/backoffice/assembly/{assembly_id}/registration")

    def test_non_member_cannot_delete(self, logged_in_user, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")

        response = logged_in_user.post(f"/backoffice/assembly/{assembly_id}/registration/draft-slug/delete")

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id) is not None


class TestEditorAtSlugUrl:
    def test_editor_renders_at_the_slug_url(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html="<p>slug-editor</p>")

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug")

        assert response.status_code == 200
        assert "slug-editor" in response.get_data(as_text=True)

    def test_unknown_slug_redirects_to_the_list(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/nope")

        assert response.status_code == 302
        assert response.location.rstrip("/").endswith(f"/backoffice/assembly/{assembly_id}/registration")

    def test_foreign_assembly_slug_redirects_to_the_list(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, uuid.uuid4(), RegistrationPageStatus.TEST, url_slug="foreign-slug")

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/foreign-slug")

        assert response.status_code == 302
        assert response.location.rstrip("/").endswith(f"/backoffice/assembly/{assembly_id}/registration")


class TestEditorNameAndSlugEditing:
    def test_save_renames_the_page(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "html_content": "<p>hi</p>", "page_name": "Spanish variant"},
        )

        assert response.status_code == 302
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id).name == "Spanish variant"

    def test_save_with_a_new_slug_redirects_to_the_new_url(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "html_content": "<p>hi</p>", "url_slug": "renamed-slug"},
        )

        assert response.status_code == 302
        assert f"/backoffice/assembly/{assembly_id}/registration/renamed-slug" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id).url_slug == "renamed-slug"

    def test_duplicate_name_is_rejected_and_page_kept(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="other-slug", name="Taken")
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "html_content": "<p>hi</p>", "page_name": "Taken"},
        )

        assert response.status_code == 302
        assert "edit=1" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id).name == "English"

    def test_edit_mode_offers_name_and_slug_inputs(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        read_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug").get_data(
            as_text=True
        )
        edit_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?edit=1").get_data(
            as_text=True
        )

        assert 'name="page_name"' not in read_body
        assert 'name="page_name"' in edit_body
        assert 'name="url_slug"' in edit_body
        assert 'name="short_url_slug"' in edit_body
        # The heading shows the page name in read-only mode
        assert "English" in read_body
