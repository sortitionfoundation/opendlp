# ABOUTME: Component tests for the backoffice registration view's read-only / edit-mode toggle
# ABOUTME: Drives the real Flask route + services over a FakeUnitOfWork via a logged-in client

import re
import uuid
from unittest.mock import patch

import pytest

from opendlp.domain.registration_page import (
    RegistrationPage,
    RegistrationPageHtml,
    RegistrationPageNotReady,
    RegistrationPageStatus,
)
from opendlp.domain.respondent_field_schema import (
    ChoiceOption,
    FieldType,
    RespondentFieldDefinition,
    RespondentFieldGroup,
)
from opendlp.domain.respondents import Respondent
from opendlp.domain.targets import TargetCategory, TargetValue
from opendlp.domain.value_objects import ContentStyle, RespondentStatus
from opendlp.entrypoints.blueprints.backoffice_registration import IMAGE_WIDTH_MAX, IMAGE_WIDTH_MIN
from tests.fakes import FakeUnitOfWork


def _seed_page(
    fake_store,
    assembly_id,
    status,
    *,
    url_slug="my-slug",
    form_html="<p>hi</p>",
    intro_html="",
    name="English",
    language="",
    thank_you_html="",
    thank_you_use_default=True,
):
    page = RegistrationPage(
        assembly_id=assembly_id,
        url_slug=url_slug,
        status=status,
        name=name,
        language=language,
        thank_you_html=thank_you_html,
        thank_you_use_default=thank_you_use_default,
    )
    html = RegistrationPageHtml(registration_page_id=page.id, form_html=form_html, intro_html=intro_html)
    with FakeUnitOfWork(store=fake_store) as uow:
        uow.registration_pages.add(page)
        uow.registration_page_html_sources.add(html)
        uow.commit()
    return page


def _extract_textarea(body: str, name: str = "html_content") -> str:
    assert f'name="{name}"' in body, f"{name} textarea missing from body"
    after_name = body.split(f'name="{name}"', 1)[1]
    return after_name.split(">", 1)[0]


@pytest.fixture
def assembly_id(existing_assembly):
    return existing_assembly.id


def _seed_respondents(
    fake_store, assembly_id: uuid.UUID, page_id: uuid.UUID | None, statuses: list[RespondentStatus]
) -> None:
    with FakeUnitOfWork(store=fake_store) as uow:
        for status in statuses:
            uow.respondents.add(
                Respondent(
                    assembly_id=assembly_id,
                    external_id=f"r-{uuid.uuid4().hex[:8]}",
                    selection_status=status,
                    registration_page_id=page_id,
                )
            )
        uow.commit()


def _count_cell(body: str, page_name: str) -> str:
    """The text of a page's Registrations cell in the pages list."""
    row = body.split(page_name, 1)[1].split("</tr>", 1)[0]
    cell = row.split('data-cell="registration-count"', 1)[1].split("</td>", 1)[0]
    return cell.split(">", 1)[1].strip()


def _total(body: str, key: str) -> str:
    """The number on one of the headline totals above the pages list."""
    total = body.split(f'data-total="{key}"', 1)[1]
    return re.findall(r"data-total-count[^>]*>(\d+)</span>", total)[0]


class TestViewEditModeFlag:
    """?edit=1 unlocks the editor of whichever step is shown - here the intro."""

    def test_default_test_status_is_read_only(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro")

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True), "intro_content")

    def test_edit_param_enables_edit_in_test_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1")

        assert response.status_code == 200
        assert "readonly" not in _extract_textarea(response.get_data(as_text=True), "intro_content")

    def test_edit_param_enables_edit_in_published_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1")

        assert response.status_code == 200
        assert "readonly" not in _extract_textarea(response.get_data(as_text=True), "intro_content")

    def test_edit_param_is_ignored_in_closed_status(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1")

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True), "intro_content")

    def test_edit_param_other_values_do_not_enable_edit(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=true"
        )

        assert response.status_code == 200
        assert "readonly" in _extract_textarea(response.get_data(as_text=True), "intro_content")


class TestEditModeRendersExpectedHtml:
    def test_test_status_read_only_has_readonly_textarea_and_edit_link(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" in _extract_textarea(body)
        # Edit link points at the section-scoped edit URL
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form&amp;edit=1" in body
        # Next → CTA advances to the auto-reply email step, ← Back returns to the intro
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=email" in body
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro" in body
        assert "Cancel</a>" not in body

    def test_test_status_edit_mode_shows_header_save_controls(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form&edit=1")

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

        view_body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form"
        ).get_data(as_text=True)
        edit_body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form&edit=1"
        ).get_data(as_text=True)

        def stepper_markup(body: str) -> str:
            return body.split('class="stepper"', 1)[1].split("</ol>", 1)[0]

        assert "<a href" in stepper_markup(view_body)
        assert "<a href" not in stepper_markup(edit_body)
        assert stepper_markup(edit_body).count('aria-disabled="true"') == 6

    def test_view_mode_hides_assets_panel_and_edit_mode_shows_it(self, logged_in_admin, fake_store, assembly_id):
        """The Assets panel is an editing tool, so it only renders in edit mode."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        view_body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form"
        ).get_data(as_text=True)
        edit_body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form&edit=1"
        ).get_data(as_text=True)

        assert ">Assets</h2>" not in view_body
        assert ">Assets</h2>" in edit_body

    def test_published_status_edit_mode_uses_save_and_republish_label(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form&edit=1")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "readonly" not in _extract_textarea(body)
        assert "Save and Republish" in body
        assert "Cancel</span></a>" in body

    def test_closed_status_ignores_edit_param(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form&edit=1")

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


def _dialog_header(body: str) -> str:
    """The editor dialog's header: everything from it to the start of the dialog body."""
    return body.split('class="dialog-header', 1)[1].split('class="dialog-body', 1)[0]


class TestEditorHeader:
    """The page's registration URL and status sit in the header, for every step."""

    @pytest.mark.parametrize("section", ["page", "intro", "form", "thank-you", "email", "preview"])
    def test_header_shows_the_registration_url(self, logged_in_admin, fake_store, assembly_id, section):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section={section}")

        header = _dialog_header(response.get_data(as_text=True))
        assert re.search(r'href="[^"]*/register/my-slug"', header)

    @pytest.mark.parametrize(
        ("status", "label"),
        [
            (RegistrationPageStatus.TEST, "Test mode"),
            (RegistrationPageStatus.PUBLISHED, "Published"),
            (RegistrationPageStatus.CLOSED, "Closed"),
        ],
    )
    def test_header_shows_the_status(self, logged_in_admin, fake_store, assembly_id, status, label):
        _seed_page(fake_store, assembly_id, status)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro")

        assert label in _dialog_header(response.get_data(as_text=True))

    def test_test_mode_has_no_warning_banner(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro")

        assert "Submissions are recorded as test entries" not in response.get_data(as_text=True)

    def test_closed_warning_points_to_the_preview_step(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro")

        body = response.get_data(as_text=True)
        assert "Registration closed" in body
        assert re.search(r'href="[^"]*\?section=preview"[^>]*>\s*Go to Preview and publish to re-open it.', body)

    def test_closed_warning_on_the_preview_step_does_not_point_to_itself(
        self, logged_in_admin, fake_store, assembly_id
    ):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=preview")

        body = response.get_data(as_text=True)
        assert "Registration closed" in body
        assert "Go to Preview and publish to re-open it." not in body


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


class TestFillAnEmptyForm:
    """The read-only form step offers to fill an empty form with starter HTML."""

    def test_an_empty_form_offers_both_fills(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html="  ")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form").get_data(
            as_text=True
        )

        assert re.search(r'name="fill_form" value="govuk"><span>Fill with accessible HTML</span>', body)
        assert re.search(r'name="fill_form" value="plain"><span>Fill with plain HTML</span>', body)

    @pytest.mark.parametrize(
        ("form_html", "status", "edit"),
        [
            ("<p>hi</p>", RegistrationPageStatus.TEST, ""),
            ("", RegistrationPageStatus.TEST, "&edit=1"),
            ("", RegistrationPageStatus.CLOSED, ""),
        ],
        ids=["form-has-html", "editing", "closed"],
    )
    def test_no_fill_is_offered_otherwise(self, logged_in_admin, fake_store, assembly_id, form_html, status, edit):
        _seed_page(fake_store, assembly_id, status, form_html=form_html)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form{edit}"
        ).get_data(as_text=True)

        assert 'name="fill_form"' not in body

    def test_a_fill_saves_the_starter_html_and_lands_read_only(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html="")

        # The read-only textarea posts its (empty) content alongside the button.
        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "form", "html_content": "", "fill_form": "govuk"},
        )

        assert response.status_code == 302
        assert "section=form" in response.location
        assert "edit=1" not in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_page_html_sources.get_by_page_id(page.id)
        assert "{{ csrf_form_element }}" in stored.form_html
        assert "govuk-button" in stored.form_html

    def test_a_stale_fill_leaves_the_form_alone(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html="<p>mine</p>")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "form", "html_content": "", "fill_form": "plain"},
            follow_redirects=True,
        )

        assert "The form already has HTML, so it was left as it is" in response.get_data(as_text=True)
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_page_html_sources.get_by_page_id(page.id)
        assert stored.form_html == "<p>mine</p>"


class TestIntroStep:
    """Step 2 of the editor: the intro HTML, saved through the same route as the form."""

    def test_bare_editor_url_lands_on_the_page_step(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, intro_html="<h1>Welcome</h1>")

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug")

        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert 'id="reg-steps-panel-page"' in body
        assert 'id="reg-steps-panel-intro"' not in body
        assert 'name="intro_content"' not in body

    def test_unknown_section_falls_back_to_the_page_step(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=nope")

        assert 'id="reg-steps-panel-page"' in response.get_data(as_text=True)

    def test_intro_section_shows_the_saved_intro(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, intro_html="<h1>Welcome</h1>")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro").get_data(
            as_text=True
        )

        assert 'id="reg-steps-panel-intro"' in body
        assert "&lt;h1&gt;Welcome&lt;/h1&gt;" in body
        assert 'name="html_content"' not in body

    def test_stepper_has_six_steps_starting_with_name_and_urls(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug").get_data(as_text=True)

        stepper = body.split('class="stepper"', 1)[1].split("</ol>", 1)[0]
        assert stepper.count("<li") == 6
        assert "Name and URLs" in stepper
        assert (
            stepper.index("?section=page")
            < stepper.index("?section=intro")
            < stepper.index("?section=form")
            < stepper.index("?section=thank-you")
            < stepper.index("?section=email")
            < stepper.index("?section=preview")
        )

    def test_intro_footer_goes_back_to_the_page_step(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro").get_data(
            as_text=True
        )

        footer = body.split('class="wizard-footer"', 1)[1]
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=page" in footer
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form" in footer

    def test_intro_textarea_is_a_code_editor_in_both_modes(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        base = f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro"

        read_textarea = _extract_textarea(logged_in_admin.get(base).get_data(as_text=True), "intro_content")
        edit_textarea = _extract_textarea(logged_in_admin.get(f"{base}&edit=1").get_data(as_text=True), "intro_content")

        assert "data-code-editor" in read_textarea
        assert "readonly" in read_textarea
        assert "data-code-editor" in edit_textarea
        assert "readonly" not in edit_textarea

    def test_intro_textarea_has_a_visible_label(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        assert re.search(r'<label for="intro_content"[^>]*>\s*Intro\s*</label>', body)

    @pytest.mark.parametrize(
        ("field_id", "error_id", "error_expr"),
        [
            ("link-modal-url", "link-modal-url-error", "linkError"),
            ("image-size-modal-width", "image-size-modal-width-error", "imageSizeError"),
        ],
    )
    def test_dialog_errors_are_announced_with_their_field(
        self, logged_in_admin, fake_store, assembly_id, field_id, error_id, error_expr
    ):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        field = re.search(rf'<input[^>]*id="{field_id}"[^>]*>', body, re.DOTALL)
        assert field is not None
        assert re.search(rf'aria-describedby="[^"]*\b{error_id}\b', field.group(0))
        assert f":aria-invalid=\"{error_expr} ? 'true' : 'false'\"" in field.group(0)
        assert f'id="{error_id}"' in body

    def test_intro_step_renders_the_visual_editor_with_toolbar_and_images(
        self, logged_in_admin, fake_store, assembly_id
    ):
        """In edit mode the intro textarea is marked for the visual editor, with images, tables, a toolbar and Insert buttons."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        assert 'data-rich-editor-for="intro_content"' in body
        assert "data-rich-editor " in body
        assert 'data-rich-editor-images="true"' in body
        assert 'role="toolbar"' in body
        assert 'data-command="image"' in body
        for command in ("alignLeft", "alignCenter", "alignRight"):
            assert f'data-command="{command}"' in body
        assert 'data-rich-editor-tables="true"' in body
        assert 'data-command="table"' in body
        assert 'id="intro_content-table-menu"' in body
        assert 'aria-controls="intro_content-visual"' in body
        assert "insertImage(image)" in body

    @pytest.mark.parametrize("label", ["insert", "details", "copy_snippet", "delete"])
    def test_asset_row_buttons_have_hover_text(self, logged_in_admin, fake_store, assembly_id, label):
        """Each icon-only asset button shows its accessible name on hover, too."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        assert re.search(rf':aria-label="image.aria_label_{label}"\s+:title="image.aria_label_{label}"', body)

    def test_editor_page_carries_the_link_dialog_messages(self, logged_in_admin, fake_store, assembly_id):
        """The link dialog's messages, including the ones for a refused address, come from the server."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        assert '"linkUrlRequired"' in body
        assert '"linkUrlNotAllowed"' in body
        assert '"linkUrlNotAbsolute"' in body
        assert 'data-rich-editor-absolute-links="true"' not in body

    def test_read_only_intro_step_has_no_toolbar(self, logged_in_admin, fake_store, assembly_id):
        """Outside edit mode the editor is shown read-only, so there is nothing to format with."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro").get_data(
            as_text=True
        )

        assert 'data-rich-editor-for="intro_content"' in body
        assert 'role="toolbar"' not in body

    def test_intro_step_offers_the_content_style_with_govuk_chosen_for_a_new_page(
        self, logged_in_admin, fake_store, assembly_id
    ):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        assert 'name="content_style"' in body
        assert 'value="govuk"' in body and 'value="plain"' in body
        assert 'data-content-style="govuk"' in body
        assert "Accessible (recommended)" in body
        assert "Plain — bring your own styles" in body

    def test_intro_step_explains_each_content_style_in_an_info_icon(self, logged_in_admin, fake_store, assembly_id):
        """Each style's explanation is the radio's description, not part of its name."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        govuk_radio = re.search(r'<input[^>]*value="govuk"[^>]*>', body)
        assert govuk_radio is not None
        assert 'aria-describedby="content_style_1-info"' in govuk_radio.group(0)
        assert re.search(r'id="content_style_1-info">The accessible style gives headings', body)
        assert re.search(r'id="content_style_2-info">You can use classes and inline style.<', body)

    def test_intro_step_does_not_mention_variables(self, logged_in_admin, fake_store, assembly_id):
        """The title and question are written into the intro, so variables are left for the docs."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        assert "<h2" in body and ">Introduction</h2>" in body
        assert "Enter the content for registrants to read before they get to the form." in body
        assert "assembly_title" not in body
        assert "highlights variables" not in body
        assert '<p class="sr-only">Press Alt+F10 to move from the text to the toolbar.</p>' in body

    def test_content_style_radios_are_read_only_outside_edit_mode(self, logged_in_admin, fake_store, assembly_id):
        """The radios stay on show, greyed and disabled, so the choice reads the same in both modes."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        base = f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro"

        view_body = logged_in_admin.get(base).get_data(as_text=True)
        edit_body = logged_in_admin.get(f"{base}&edit=1").get_data(as_text=True)

        view_radios = re.findall(r'<input[^>]*name="content_style"[^>]*>', view_body, re.DOTALL)
        assert len(view_radios) == 2
        assert all("disabled" in radio for radio in view_radios)
        assert "radio-readonly" in view_body
        edit_radios = re.findall(r'<input[^>]*name="content_style"[^>]*>', edit_body, re.DOTALL)
        assert len(edit_radios) == 2
        assert not any("disabled" in radio for radio in edit_radios)
        assert "radio-readonly" not in edit_body

    def _save_intro_with_style(self, client, assembly_id, content_style=None):
        data = {"action": "save", "step": "intro", "intro_content": "<h1>Hi</h1>"}
        if content_style is not None:
            data["content_style"] = content_style
        response = client.post(f"/backoffice/assembly/{assembly_id}/registration/my-slug/save", data=data)
        assert response.status_code == 302
        assert "edit=1" not in response.location

    def _stored_style(self, fake_store, page):
        with FakeUnitOfWork(store=fake_store) as uow:
            html = uow.registration_page_html_sources.get_by_page_id(page.id)
            assert html is not None
            return html.content_style

    @pytest.mark.parametrize("style", [ContentStyle.PLAIN, ContentStyle.GOVUK])
    def test_saving_the_intro_saves_the_chosen_style(self, logged_in_admin, fake_store, assembly_id, style):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        other = ContentStyle.GOVUK if style == ContentStyle.PLAIN else ContentStyle.PLAIN
        self._save_intro_with_style(logged_in_admin, assembly_id, other.value)

        self._save_intro_with_style(logged_in_admin, assembly_id, style.value)

        assert self._stored_style(fake_store, page) == style

    @pytest.mark.parametrize("posted", [None, "", "fancy"])
    def test_a_post_without_a_known_style_leaves_it_alone(self, logged_in_admin, fake_store, assembly_id, posted):
        """No style, or one that is not a style, saves the intro and keeps the style it had."""
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        self._save_intro_with_style(logged_in_admin, assembly_id, "plain")

        self._save_intro_with_style(logged_in_admin, assembly_id, posted)

        assert self._stored_style(fake_store, page) == ContentStyle.PLAIN

    def test_image_width_limits_come_from_one_place(self, logged_in_admin, fake_store, assembly_id):
        """The Image size dialog, its message and the editor's drag limit all read the server's limits."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro&edit=1"
        ).get_data(as_text=True)

        assert f'"imageWidth": {{"max": {IMAGE_WIDTH_MAX}, "min": {IMAGE_WIDTH_MIN}}}' in body
        assert f"from {IMAGE_WIDTH_MIN} to {IMAGE_WIDTH_MAX}" in body
        width_field = re.search(r'<input[^>]*id="image-size-modal-width"[^>]*>', body, re.DOTALL)
        assert width_field is not None
        assert f'min="{IMAGE_WIDTH_MIN}"' in width_field.group(0)
        assert f'max="{IMAGE_WIDTH_MAX}"' in width_field.group(0)
        assert f'data-image-min-width="{IMAGE_WIDTH_MIN}"' in body

    def test_only_the_form_step_offers_a_skeleton(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        base = f"/backoffice/assembly/{assembly_id}/registration/my-slug"

        intro_body = logged_in_admin.get(f"{base}?section=intro&edit=1").get_data(as_text=True)
        form_body = logged_in_admin.get(f"{base}?section=form&edit=1").get_data(as_text=True)

        assert "Show Intro Skeleton" not in intro_body
        assert "fetchFormSkeleton()" not in intro_body
        assert "fetchFormSkeleton()" in form_body
        assert "Form Skeleton" in form_body

    def test_the_form_skeleton_is_only_offered_while_editing(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form").get_data(
            as_text=True
        )

        assert "fetchFormSkeleton()" not in body

    def test_form_step_heading_and_help_follow_the_mode(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        base = f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form"

        view_body = logged_in_admin.get(base).get_data(as_text=True)
        edit_body = logged_in_admin.get(f"{base}&edit=1").get_data(as_text=True)

        for body in (view_body, edit_body):
            assert ">Registration form</h2>" in body
        assert "The HTML for the form on the registration page." in view_body
        assert "Paste/edit your HTML form code below." not in view_body
        assert "Paste/edit your HTML form code below." in edit_body
        assert "Other placeholders in the generated HTML help the form work well for registrants." in edit_body

    def test_skeleton_design_system_link_opens_in_a_new_tab(self, logged_in_admin, fake_store, assembly_id):
        """Following the link must not lose the skeleton the organiser was looking at."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro").get_data(
            as_text=True
        )

        link = re.search(r'<a href="https://design-system.service.gov.uk/"[^>]*>', body)
        assert link is not None
        assert 'target="_blank"' in link.group(0)
        assert 'rel="noopener noreferrer"' in link.group(0)

    def test_save_persists_the_intro_and_returns_to_the_intro_step(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, form_html="<p>form</p>")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "intro", "intro_content": "<h1>Welcome</h1>"},
        )

        assert response.status_code == 302
        assert "section=intro" in response.location
        assert "edit=1" not in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_page_html_sources.get_by_page_id(page.id)
        assert stored.intro_html == "<h1>Welcome</h1>"
        assert stored.form_html == "<p>form</p>"

    def test_save_and_next_from_the_intro_advances_to_the_form(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save_and_next", "step": "intro", "intro_content": "<h1>Welcome</h1>"},
        )

        assert response.status_code == 302
        assert "section=form" in response.location

    def test_save_and_next_from_the_last_step_stays_on_it(self, logged_in_admin, fake_store, assembly_id):
        """The preview step has no next step, so a save_and_next posted from it stays there."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save_and_next", "step": "preview"},
        )

        assert response.status_code == 302
        assert "section=preview" in response.location
        assert "edit=1" not in response.location
        with logged_in_admin.session_transaction() as session:
            categories = [category for category, _ in session.get("_flashes", [])]
        assert categories == ["success"]

    def test_save_from_the_form_still_returns_to_the_form(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "form", "html_content": "<p>x</p>"},
        )

        assert response.status_code == 302
        assert "section=form" in response.location

    @pytest.mark.parametrize("step", ["", "nope"])
    def test_a_save_without_a_known_step_returns_to_the_form(self, logged_in_admin, fake_store, assembly_id, step):
        """The posted step names the origin; anything else is treated as the form, as lifecycle posts are."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        data = {"action": "save", "intro_content": "<h1>Welcome</h1>"}
        if step:
            data["step"] = step

        response = logged_in_admin.post(f"/backoffice/assembly/{assembly_id}/registration/my-slug/save", data=data)

        assert response.status_code == 302
        assert "section=form" in response.location

    @pytest.mark.parametrize("section", ["intro", "form", "thank-you"])
    def test_each_step_posts_its_name(self, logged_in_admin, fake_store, assembly_id, section):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section={section}&edit=1"
        ).get_data(as_text=True)

        assert f'<input type="hidden" name="step" value="{section}"' in body

    def test_oversize_intro_returns_to_the_intro_step_in_edit_mode(
        self, logged_in_admin, fake_store, assembly_id, temp_env_vars
    ):
        temp_env_vars(REGISTRATION_INTRO_HTML_MAX_BYTES="1024")
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "intro", "intro_content": "x" * 2000},
        )

        assert response.status_code == 302
        assert "section=intro" in response.location
        assert "edit=1" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_page_html_sources.get_by_page_id(page.id).intro_html == ""


class TestThankYouStep:
    """Step 4 of the editor: the standard thank-you page, or the page's own HTML."""

    def _get(self, client, assembly_id, query=""):
        return client.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=thank-you{query}").get_data(
            as_text=True
        )

    def _save(self, client, assembly_id, **data):
        return client.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "thank-you", **data},
        )

    def _stored(self, fake_store, page):
        with FakeUnitOfWork(store=fake_store) as uow:
            return uow.registration_pages.get(page.id)

    def test_renders_its_panel_with_the_saved_html(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(
            fake_store,
            assembly_id,
            RegistrationPageStatus.TEST,
            thank_you_html="<p>Thanks a lot</p>",
            thank_you_use_default=False,
        )

        body = self._get(logged_in_admin, assembly_id)

        assert 'id="reg-steps-panel-thank-you"' in body
        assert "&lt;p&gt;Thanks a lot&lt;/p&gt;" in body
        assert "readonly" in _extract_textarea(body, "thank_you_html")

    def test_edit_mode_unlocks_the_editor_with_variables_and_images(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = self._get(logged_in_admin, assembly_id, "&edit=1")

        assert "readonly" not in _extract_textarea(body, "thank_you_html")
        assert 'data-rich-editor-for="thank_you_html"' in body
        assert "{{ project_title }}" in body
        assert 'data-command="image"' in body

    def test_closed_page_stays_read_only(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        body = self._get(logged_in_admin, assembly_id, "&edit=1")

        assert "readonly" in _extract_textarea(body, "thank_you_html")

    def test_standard_page_is_chosen_and_the_editor_hidden_for_a_new_page(
        self, logged_in_admin, fake_store, assembly_id
    ):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = self._get(logged_in_admin, assembly_id, "&edit=1")

        assert re.search(r'name="thank_you_page"\s+id="[^"]+"\s+value="standard"\s+checked', body)
        assert re.search(r"x-show=\"thankYouChoice === 'own'\"\s+style=\"display: none;\"", body)

    def test_own_page_is_chosen_and_the_editor_shown(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(
            fake_store, assembly_id, RegistrationPageStatus.TEST, thank_you_html="<p>x</p>", thank_you_use_default=False
        )

        body = self._get(logged_in_admin, assembly_id, "&edit=1")

        assert re.search(r'name="thank_you_page"\s+id="[^"]+"\s+value="own"\s+checked', body)
        assert 'style="display: none;"' not in body.split("thankYouChoice === 'own'", 1)[1].split(">", 1)[0]

    @pytest.mark.parametrize(("use_default", "hidden"), [(True, True), (False, False)])
    def test_assets_panel_is_shown_only_for_own_page(
        self, logged_in_admin, fake_store, assembly_id, use_default, hidden
    ):
        """The standard page can't use images or documents, so the Assets panel goes with the editor."""
        _seed_page(
            fake_store,
            assembly_id,
            RegistrationPageStatus.TEST,
            thank_you_html="<p>x</p>",
            thank_you_use_default=use_default,
        )

        body = self._get(logged_in_admin, assembly_id, "&edit=1")

        aside = body.split("<aside", 1)[1].split(">", 1)[0]
        assert "x-show=\"thankYouChoice === 'own'\"" in aside
        assert ("display: none;" in aside) is hidden

    @pytest.mark.parametrize(
        ("show", "text"), [("own", "your thank-you page"), ("standard", "standard thank-you page")]
    )
    def test_links_to_each_public_thank_you_page_in_a_new_tab(
        self, logged_in_admin, fake_store, assembly_id, show, text
    ):
        """Both, whichever is chosen, so the link never points at the page the radios are not on."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = self._get(logged_in_admin, assembly_id)

        link = re.search(rf'<a[^>]*href="/register/my-slug/thank-you\?show={show}"[^>]*>([^<]*)</a>', body)
        assert link is not None
        assert link.group(1) == text
        assert 'target="_blank"' in link.group(0)
        assert 'class="underline"' in link.group(0)
        assert "color: var(--color-links)" in link.group(0)

    @pytest.mark.parametrize(
        ("style", "label"),
        [(ContentStyle.GOVUK, "Accessible (recommended)"), (ContentStyle.PLAIN, "Plain — bring your own styles")],
    )
    def test_says_which_style_the_page_uses_and_where_to_change_it(
        self, logged_in_admin, fake_store, assembly_id, style, label
    ):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.registration_page_html_sources.get_by_page_id(page.id).update_content_style(style)
            uow.commit()

        body = self._get(logged_in_admin, assembly_id)

        note = body.split('id="thank-you-content-style"', 1)[1].split("</p>", 1)[0]
        assert label in note
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro" in note

    def test_the_editor_and_the_radio_have_different_names(self, logged_in_admin, fake_store, assembly_id):
        """A screen reader would otherwise announce two different controls the same way."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = self._get(logged_in_admin, assembly_id)

        assert re.search(r'<label for="thank_you_html"[^>]*>\s*Content of your thank-you page', body)
        assert 'data-rich-editor-label="Content of your thank-you page"' in body

    def test_does_not_offer_to_leave_for_the_intro_step_while_editing(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = self._get(logged_in_admin, assembly_id, "&edit=1")

        note = body.split('id="thank-you-content-style"', 1)[1].split("</p>", 1)[0]
        assert "Accessible (recommended)" in note
        assert "section=intro" not in note

    def test_footer_goes_back_to_the_form_and_on_to_the_email(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        footer = self._get(logged_in_admin, assembly_id).split('class="wizard-footer"', 1)[1]

        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form" in footer
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=email" in footer

    def test_the_neighbouring_steps_point_at_it(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        step_url = f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=thank-you"

        for section in ("form", "email"):
            body = logged_in_admin.get(
                f"/backoffice/assembly/{assembly_id}/registration/my-slug?section={section}"
            ).get_data(as_text=True)
            assert step_url in body.split('class="wizard-footer"', 1)[1], section

    def test_save_stores_own_html_and_returns_to_the_step(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = self._save(logged_in_admin, assembly_id, thank_you_page="own", thank_you_html="<p>Ta</p>")

        assert response.status_code == 302
        assert "section=thank-you" in response.location
        assert "edit=1" not in response.location
        stored = self._stored(fake_store, page)
        assert stored.thank_you_html == "<p>Ta</p>"
        assert stored.thank_you_use_default is False

    def test_choosing_the_standard_page_keeps_the_html(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(
            fake_store, assembly_id, RegistrationPageStatus.TEST, thank_you_html="<p>x</p>", thank_you_use_default=False
        )

        self._save(logged_in_admin, assembly_id, thank_you_page="standard", thank_you_html="<p>x</p>")

        stored = self._stored(fake_store, page)
        assert stored.thank_you_use_default is True
        assert stored.thank_you_html == "<p>x</p>"

    def test_save_and_next_advances_to_the_email(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save_and_next", "step": "thank-you", "thank_you_page": "standard", "thank_you_html": ""},
        )

        assert "section=email" in response.location

    def test_save_and_next_from_the_form_advances_to_it(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save_and_next", "step": "form", "html_content": "<p>x</p>"},
        )

        assert "section=thank-you" in response.location

    def test_broken_own_html_is_refused_back_in_edit_mode(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = self._save(logged_in_admin, assembly_id, thank_you_page="own", thank_you_html="<p>{{ name }}</p>")

        assert "section=thank-you" in response.location
        assert "edit=1" in response.location
        with logged_in_admin.session_transaction() as session:
            messages = [message for _, message in session.get("_flashes", [])]
        assert any("{{ name }}" in message for message in messages)
        assert self._stored(fake_store, page).thank_you_html == ""

    def test_oversize_html_is_refused_back_in_edit_mode(self, logged_in_admin, fake_store, assembly_id, temp_env_vars):
        temp_env_vars(REGISTRATION_THANK_YOU_HTML_MAX_BYTES="1024")
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = self._save(logged_in_admin, assembly_id, thank_you_page="own", thank_you_html="x" * 2000)

        assert "edit=1" in response.location
        assert self._stored(fake_store, page).thank_you_html == ""

    def test_a_post_without_the_choice_leaves_the_thank_you_alone(self, logged_in_admin, fake_store, assembly_id):
        """Other steps and lifecycle posts carry no thank-you fields."""
        page = _seed_page(
            fake_store, assembly_id, RegistrationPageStatus.TEST, thank_you_html="<p>x</p>", thank_you_use_default=False
        )

        logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "intro", "intro_content": "<h1>Hi</h1>"},
        )

        stored = self._stored(fake_store, page)
        assert stored.thank_you_html == "<p>x</p>"
        assert stored.thank_you_use_default is False

    def test_blank_html_offers_the_starter(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = self._get(logged_in_admin, assembly_id)

        assert re.search(r'name="fill_thank_you" value="1"><span>Fill with starter content</span>', body)

    @pytest.mark.parametrize(
        ("thank_you_html", "status", "edit"),
        [
            ("<p>x</p>", RegistrationPageStatus.TEST, ""),
            ("", RegistrationPageStatus.TEST, "&edit=1"),
            ("", RegistrationPageStatus.CLOSED, ""),
        ],
        ids=["has-html", "editing", "closed"],
    )
    def test_no_starter_is_offered_otherwise(
        self, logged_in_admin, fake_store, assembly_id, thank_you_html, status, edit
    ):
        _seed_page(fake_store, assembly_id, status, thank_you_html=thank_you_html)

        assert 'name="fill_thank_you"' not in self._get(logged_in_admin, assembly_id, edit)

    def test_the_starter_fills_and_shows_the_page_and_lands_read_only(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        # The read-only textarea posts its (empty) content alongside the button.
        response = self._save(logged_in_admin, assembly_id, thank_you_html="", fill_thank_you="1")

        assert "section=thank-you" in response.location
        assert "edit=1" not in response.location
        stored = self._stored(fake_store, page)
        assert "Thank you for registering" in stored.thank_you_html
        assert stored.thank_you_use_default is False

    def test_a_stale_starter_fill_leaves_the_html_alone(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, thank_you_html="<p>mine</p>")

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "thank-you", "thank_you_html": "", "fill_thank_you": "1"},
            follow_redirects=True,
        )

        assert "The thank-you page already has HTML, so it was left as it is" in response.get_data(as_text=True)
        assert self._stored(fake_store, page).thank_you_html == "<p>mine</p>"


class TestCodeEditorEnhancement:
    """The HTML textareas opt into the CodeMirror progressive enhancement."""

    def test_html_content_textarea_marked_for_code_editor_in_read_only(self, logged_in_admin, fake_store, assembly_id):
        """Read-only view still tags the textarea so it renders highlighted (Q4)."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form")

        assert response.status_code == 200
        textarea = _extract_textarea(response.get_data(as_text=True))
        assert "data-code-editor" in textarea
        assert "readonly" in textarea

    def test_html_content_textarea_marked_for_code_editor_in_edit_mode(self, logged_in_admin, fake_store, assembly_id):
        """Edit mode tags the textarea and leaves it editable."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form&edit=1")

        assert response.status_code == 200
        textarea = _extract_textarea(response.get_data(as_text=True))
        assert "data-code-editor" in textarea
        assert "readonly" not in textarea

    def test_editor_bundle_is_loaded_on_the_page(self, logged_in_admin, fake_store, assembly_id):
        """The CodeMirror bundle is referenced so the enhancement can run."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form")

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

    def test_preview_renders_the_intro_above_the_form(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(
            fake_store,
            assembly_id,
            RegistrationPageStatus.TEST,
            form_html=_PREVIEWABLE_FORM,
            intro_html="<h1>{{ assembly_title }}</h1>",
        )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug/form-preview")

        body = response.get_data(as_text=True)
        assert '<h1 class="govuk-heading-xl">' in body
        assert body.index('<h1 class="govuk-heading-xl">') < body.index('name="first_name"')

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
    TEST → Publish; PUBLISHED → Unpublish + Close registration; CLOSED → Re-open."""

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
        # Close goes through the confirmation dialog, as it turns visitors away at once.
        assert "Close registration?" in body

    def test_closed_status_offers_reopen_only(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        body = self._preview_body(logged_in_admin, assembly_id)

        assert 'value="reopen"' in body
        assert "Re-open registration</span></button>" in body
        assert 'value="publish"' not in body
        assert 'value="unpublish"' not in body
        assert "Close registration/my-slug" not in body

    def test_reopen_publishes_the_page_and_lands_on_preview(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(
            fake_store,
            assembly_id,
            RegistrationPageStatus.CLOSED,
            form_html="<form>{{ csrf_form_element }}{{ form_action }}</form>",
        )

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "reopen"},
        )

        assert response.status_code == 302
        assert "section=preview" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            stored = uow.registration_pages.get(page.id)
        assert stored.status == RegistrationPageStatus.PUBLISHED

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

    def test_each_page_shows_its_registration_count(self, logged_in_admin, fake_store, assembly_id):
        busy = _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="busy-slug", name="Busy")
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="quiet-slug", name="Quiet")
        with FakeUnitOfWork(store=fake_store) as uow:
            for i in range(2):
                uow.respondents.add(
                    Respondent(assembly_id=assembly_id, external_id=f"r-{i}", registration_page_id=busy.id)
                )
            uow.commit()

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert _count_cell(body, "Busy") == "2"
        assert _count_cell(body, "Quiet") == "0"

    def test_page_count_shows_test_submissions_separately(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="live-slug", name="Live")
        _seed_respondents(
            fake_store,
            assembly_id,
            page.id,
            [
                RespondentStatus.POOL,
                RespondentStatus.WITHDRAWN,
                RespondentStatus.TEST_SUBMISSION,
                RespondentStatus.TEST_SUBMISSION,
                RespondentStatus.TEST_SUBMISSION,
                RespondentStatus.DELETED,
            ],
        )

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert _count_cell(body, "Live") == "2 (+3 test)"

    def test_shows_the_registration_totals_near_the_top(self, logged_in_admin, fake_store, assembly_id):
        first = _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="one-slug", name="One")
        second = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="two-slug", name="Two")
        _seed_respondents(
            fake_store,
            assembly_id,
            first.id,
            [RespondentStatus.POOL, RespondentStatus.SELECTED, RespondentStatus.WITHDRAWN, RespondentStatus.DELETED],
        )
        _seed_respondents(
            fake_store, assembly_id, second.id, [RespondentStatus.CONFIRMED, RespondentStatus.TEST_SUBMISSION]
        )
        # Uploaded respondents have no page; deleted ones are not counted anywhere.
        _seed_respondents(
            fake_store,
            assembly_id,
            None,
            [RespondentStatus.POOL, RespondentStatus.POOL, RespondentStatus.WITHDRAWN, RespondentStatus.DELETED],
        )

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert _total(body, "registrations") == "4"
        assert _total(body, "test-submissions") == "1"
        assert _total(body, "uploaded") == "3"
        # A line between each pair of numbers, none before the first.
        assert body.count("data-total-divider") == 2

    def test_hides_empty_test_and_upload_totals(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="live-slug", name="Live")
        _seed_respondents(fake_store, assembly_id, page.id, [RespondentStatus.POOL])

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert _total(body, "registrations") == "1"
        assert 'data-total="test-submissions"' not in body
        assert 'data-total="uploaded"' not in body
        assert "data-total-divider" not in body

    def test_empty_assembly_offers_page_creation(self, logged_in_admin, fake_store, assembly_id):
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")

        assert response.status_code == 200
        assert f"/backoffice/assembly/{assembly_id}/registration/create" in response.get_data(as_text=True)

    def test_empty_assembly_shows_the_illustrated_empty_state(self, logged_in_admin, fake_store, assembly_id):
        empty_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")
        populated_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        illustration = "/static/img/illustrations/no-registration-page.svg"
        assert illustration in empty_body
        assert "No registration page created yet" in empty_body
        assert illustration not in populated_body
        assert "No registration page created yet" not in populated_body

    def test_empty_state_illustration_is_served(self, logged_in_admin):
        response = logged_in_admin.get("/static/img/illustrations/no-registration-page.svg")

        assert response.status_code == 200
        assert response.mimetype == "image/svg+xml"

    def test_close_action_offered_only_for_published_pages(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="live-slug", name="Live")
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert f"/backoffice/assembly/{assembly_id}/registration/live-slug/save" in body
        assert f"/backoffice/assembly/{assembly_id}/registration/draft-slug/save" not in body

    def test_create_button_label_is_the_same_whether_or_not_pages_exist(self, logged_in_admin, fake_store, assembly_id):
        empty_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")
        populated_body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert "Create registration page" in empty_body
        assert "Create registration page" in populated_body
        assert "Create another registration page" not in populated_body
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

    def test_each_row_has_an_edit_button_to_its_editor(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="draft-slug", name="Draft")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        edit_link = re.search(r'<a [^>]*aria-label="Edit Draft"[^>]*>', body)
        assert edit_link is not None
        assert f'href="/backoffice/assembly/{assembly_id}/registration/draft-slug"' in edit_link.group(0)

    def test_menu_no_longer_offers_assembly_details_or_edit(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED, url_slug="live-slug", name="Live")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert "Actions for Live" in body
        assert "See assembly details" not in body
        assert "Edit registration" not in body

    def test_row_with_no_menu_actions_has_no_menu(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED, url_slug="closed-slug", name="Shut")

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert 'aria-label="Edit Shut"' in body
        assert "Actions for Shut" not in body


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

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form")

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
    """The page name and URLs are edited on their own step, the first."""

    def test_save_renames_the_page(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "page", "page_name": "Spanish variant"},
        )

        assert response.status_code == 302
        assert "section=page" in response.location
        assert "edit=1" not in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id).name == "Spanish variant"

    def test_save_and_next_from_the_page_step_advances_to_the_intro(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save_and_next", "step": "page", "page_name": "English"},
        )

        assert response.status_code == 302
        assert "section=intro" in response.location

    def test_save_with_a_new_slug_redirects_to_the_new_url(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "page", "url_slug": "renamed-slug"},
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
            data={"action": "save", "step": "page", "page_name": "Taken"},
        )

        assert response.status_code == 302
        assert "section=page" in response.location
        assert "edit=1" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id).name == "English"

    def test_a_taken_slug_returns_to_the_page_step_with_the_old_slug(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST, url_slug="other-slug", name="Other")
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        response = logged_in_admin.post(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug/save",
            data={"action": "save", "step": "page", "url_slug": "other-slug"},
        )

        assert response.status_code == 302
        assert "/registration/my-slug?section=page&edit=1" in response.location
        with FakeUnitOfWork(store=fake_store) as uow:
            assert uow.registration_pages.get(page.id).url_slug == "my-slug"

    def test_page_step_edit_mode_offers_name_and_slug_inputs(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=page&edit=1"
        ).get_data(as_text=True)

        assert '<input type="hidden" name="step" value="page"' in body
        assert re.search(r'name="page_name"\s+id="page_name"\s+value="English"', body)
        assert 'name="url_slug"' in body
        assert 'name="short_url_slug"' in body
        assert "Save</span></button>" in body
        assert "Cancel</span></a>" in body
        assert "These URLs are locked" not in body

    def test_page_step_read_view_shows_the_name_and_both_urls(self, logged_in_admin, fake_store, assembly_id):
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.registration_pages.get(page.id).update_slugs(short_url_slug="123456")
            uow.commit()

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=page").get_data(
            as_text=True
        )
        panel = body.split('id="reg-steps-panel-page"', 1)[1].split('class="wizard-footer"', 1)[0]

        assert 'name="page_name"' not in panel
        assert 'name="url_slug"' not in panel
        assert "English" in panel
        assert "/register/my-slug" in panel
        assert "Short URL" in panel
        assert "/r/123456" in panel
        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=page&amp;edit=1" in panel

    def test_page_step_read_view_leaves_out_an_unset_short_url(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=page").get_data(
            as_text=True
        )
        panel = body.split('id="reg-steps-panel-page"', 1)[1].split('class="wizard-footer"', 1)[0]

        assert "/register/my-slug" in panel
        assert "Short URL" not in panel

    def test_page_step_footer_goes_on_to_the_intro_and_not_back(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=page").get_data(
            as_text=True
        )
        footer = body.split('class="wizard-footer"', 1)[1]

        assert f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro" in footer
        assert "Back" not in footer

    @pytest.mark.parametrize("edit", ["", "&edit=1"])
    def test_published_page_step_explains_the_locked_urls(self, logged_in_admin, fake_store, assembly_id, edit):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.PUBLISHED)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=page{edit}"
        ).get_data(as_text=True)

        assert "These URLs are locked" in body
        if edit:
            assert re.search(r'name="url_slug"[^>]*\sdisabled', body)
            assert "Save and Republish" in body

    def test_closed_page_step_offers_no_edit(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.CLOSED)

        body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=page&edit=1"
        ).get_data(as_text=True)

        assert 'name="page_name"' not in body
        assert "section=page&amp;edit=1" not in body

    @pytest.mark.parametrize("section", ["intro", "form"])
    def test_other_steps_do_not_offer_them(self, logged_in_admin, fake_store, assembly_id, section):
        """The intro and form steps edit their HTML only; the heading is the page name, not an input."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)

        edit_body = logged_in_admin.get(
            f"/backoffice/assembly/{assembly_id}/registration/my-slug?section={section}&edit=1"
        ).get_data(as_text=True)

        assert 'name="page_name"' not in edit_body
        assert 'name="url_slug"' not in edit_body
        assert 'name="short_url_slug"' not in edit_body
        assert ">English</h2>" in edit_body


class TestSetupTaskList:
    """The registration landing prepends the set-up task list (sources, fields, pages)."""

    def test_task_list_summarises_sources_and_fields(
        self, logged_in_admin, fake_store, assembly_id, admin_user, existing_assembly
    ):
        with FakeUnitOfWork(store=fake_store) as uow:
            category = TargetCategory(
                assembly_id=assembly_id,
                name="Gender",
                values=[TargetValue(value="Male", min=1, max=5)],
            )
            uow.target_categories.add(category)
            uow.target_categories.add(
                TargetCategory(
                    assembly_id=assembly_id,
                    name="Region",
                    values=[TargetValue(value="North", min=1, max=5)],
                )
            )
            uow.respondent_field_definitions.add(
                RespondentFieldDefinition(
                    assembly_id=assembly_id,
                    field_key="Gender",
                    label="Gender",
                    group=RespondentFieldGroup.ABOUT_YOU,
                    sort_order=10,
                    field_type=FieldType.CHOICE_RADIO,
                    options=[ChoiceOption(value="Male")],
                    target_category_id=category.id,
                )
            )

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Link targets to questions" in body
        assert "1 of 2 targets have a question" in body
        assert "Registration questions" in body
        assert "1 question on the registration page" in body
        assert f"/assembly/{assembly_id}/target-sources" in body
        assert f"/assembly/{assembly_id}/respondent-schema" in body

    def test_each_step_is_one_link_with_a_numbered_circle(self, logged_in_admin, assembly_id):
        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        steps = re.findall(r'<a class="setup-step"\s+href="([^"]*)">(.*?)</a>', body, re.DOTALL)
        assert [href for href, _ in steps] == [
            f"/backoffice/assembly/{assembly_id}/target-sources",
            f"/backoffice/assembly/{assembly_id}/respondent-schema",
        ]
        for index, (_, inner) in enumerate(steps, start=1):
            assert re.search(rf'<span class="stepper-number" aria-hidden="true">\s*{index}\s*</span>', inner)

    def test_the_page_authoring_step_is_not_listed(self, logged_in_admin, assembly_id):
        body = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration").get_data(as_text=True)

        assert "Registration pages" not in body
        assert "Author the page HTML below" not in body

    def test_no_targets_yet_points_at_the_targets_tab(self, logged_in_admin, assembly_id):
        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration")
        body = response.get_data(as_text=True)

        assert "No targets yet" in body


class TestFieldsChangedWarning:
    """The form editor warns when the field schema changed after the HTML was last saved."""

    def _seed_field(self, fake_store, assembly_id):
        with FakeUnitOfWork(store=fake_store) as uow:
            uow.respondent_field_definitions.add(
                RespondentFieldDefinition(
                    assembly_id=assembly_id,
                    field_key="gender",
                    label="Gender",
                    group=RespondentFieldGroup.ABOUT_YOU,
                    sort_order=10,
                )
            )

    def test_warns_when_a_field_postdates_the_saved_html(self, logged_in_admin, fake_store, assembly_id):
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        self._seed_field(fake_store, assembly_id)  # created after the page HTML

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form")

        assert b"registration questions have changed" in response.data

    def test_quiet_when_the_html_is_newer_than_every_field(self, logged_in_admin, fake_store, assembly_id):
        self._seed_field(fake_store, assembly_id)
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)  # HTML saved after the field

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form")

        assert b"registration questions have changed" not in response.data

    def test_still_warns_after_the_intro_and_style_are_saved(self, logged_in_admin, fake_store, assembly_id):
        """Saving the intro or the style does not touch the form HTML, so the warning stays."""
        page = _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        self._seed_field(fake_store, assembly_id)
        with FakeUnitOfWork(store=fake_store) as uow:
            html = uow.registration_page_html_sources.get_by_page_id(page.id)
            assert html is not None
            html.update_intro_html("<h1>Welcome</h1>")
            html.update_content_style(ContentStyle.PLAIN)
            uow.commit()

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=form")

        assert b"registration questions have changed" in response.data

    def test_intro_step_never_warns(self, logged_in_admin, fake_store, assembly_id):
        """The intro does not depend on the field schema, so a schema change is not its concern."""
        _seed_page(fake_store, assembly_id, RegistrationPageStatus.TEST)
        self._seed_field(fake_store, assembly_id)

        response = logged_in_admin.get(f"/backoffice/assembly/{assembly_id}/registration/my-slug?section=intro")

        assert b"registration questions have changed" not in response.data
