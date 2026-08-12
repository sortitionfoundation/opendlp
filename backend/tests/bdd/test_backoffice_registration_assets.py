"""ABOUTME: BDD tests for the registration page assets panel after its script extraction
ABOUTME: Confirms in a real browser that the bundle loads and drives the image/document JSON routes

The component tests in tests/component/test_backoffice_registration_page_script.py cover
the markup, the script tag and the JSON data block. Only a browser can tell us the bundle
actually loads, Alpine picks it up, and the CSRF token in that data block satisfies the
routes - which is the risk that came with moving 580 lines out of an inline block.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image
from playwright.sync_api import Page, expect
from pytest_bdd import given, parsers, scenarios, then, when

from opendlp.service_layer.assembly_service import create_assembly
from opendlp.service_layer.registration_page_service import create_registration_page_with_slugs
from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

from .config import ADMIN_PASSWORD, PLAYWRIGHT_TIMEOUT, Urls

scenarios("../../features/backoffice-registration-assets.feature")

# Set on the window before an action, and gone if the browser navigated. The whole point
# of the assets panel is that it mutates the list in place, so an uncommitted edit in the
# HTML editor survives - a reload would silently take that away.
NO_RELOAD_MARKER = "window.__assetsPanelStillLoaded = true"

# Assembly title -> id, filled in by the Given step and read by the When step.
_assembly_ids: dict[str, str] = {}


def _png_file(tmp_path: Path, name: str) -> str:
    buffer = BytesIO()
    Image.new("RGB", (20, 20), (12, 34, 56)).save(buffer, format="PNG")
    path = tmp_path / name
    path.write_bytes(buffer.getvalue())
    return str(path)


def _pdf_file(tmp_path: Path, name: str) -> str:
    path = tmp_path / name
    path.write_bytes(b"%PDF-1.4\nbody\n%%EOF")
    return str(path)


def _mark_page(page: Page) -> None:
    page.evaluate(NO_RELOAD_MARKER)


# =============================================================================
# Given / When Steps
# =============================================================================

# The registration-editor scenarios share this wording, but their step definitions
# live in test_backoffice.py and pytest-bdd registers a step in the module that
# defines it - importing the function does not bring the registration with it.


@given("I am logged in as an admin user")
def logged_in_as_admin(page: Page, admin_user):
    page.context.clear_cookies()
    page.goto(Urls.login)
    page.fill('input[name="email"]', admin_user.email)
    page.fill('input[name="password"]', ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url(Urls.dashboard)


@given(parsers.parse('there is an assembly called "{title}" with a registration page'))
def assembly_with_registration_page(title: str, admin_user, test_database):
    assembly = create_assembly(
        uow=SqlAlchemyUnitOfWork(test_database),
        title=title,
        created_by_user_id=admin_user.id,
    )
    create_registration_page_with_slugs(
        uow=SqlAlchemyUnitOfWork(test_database),
        user_id=admin_user.id,
        assembly_id=assembly.id,
        name="Registration page",
    )
    _assembly_ids[title] = str(assembly.id)


@when(parsers.parse('I visit the registration form editor for "{title}"'))
def visit_registration_form_editor(page: Page, title: str):
    """Edit mode, because the assets panel is only rendered while editing."""
    page.goto(f"{Urls.base}/backoffice/assembly/{_assembly_ids[title]}/registration?section=form&edit=1")


def _panel_upload_button(page: Page, index: int):
    """The Images and Documents subsections each head their list with an Upload button."""
    return page.locator("aside").get_by_role("button", name="Upload").nth(index)


@when("I open the image upload modal")
def open_image_upload_modal(page: Page):
    _panel_upload_button(page, 0).click()
    expect(page.get_by_role("dialog", name="Upload image")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I upload an image called "{alt}"'))
def upload_image(page: Page, tmp_path: Path, alt: str):
    _mark_page(page)
    open_image_upload_modal(page)
    page.locator("#image-upload-file").set_input_files(_png_file(tmp_path, "logo.png"))
    page.locator("#image-upload-alt").fill(alt)
    page.get_by_role("dialog", name="Upload image").get_by_role("button", name="Upload").click()
    expect(page.get_by_role("dialog", name="Upload image")).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I upload a document labelled "{label}"'))
def upload_document(page: Page, tmp_path: Path, label: str):
    _mark_page(page)
    _panel_upload_button(page, 1).click()
    expect(page.get_by_role("dialog", name="Upload document")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    page.locator("#document-upload-file").set_input_files(_pdf_file(tmp_path, "info-pack.pdf"))
    page.locator("#document-upload-label").fill(label)
    page.get_by_role("dialog", name="Upload document").get_by_role("button", name="Upload").click()
    expect(page.get_by_role("dialog", name="Upload document")).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I change the alt text of "{old}" to "{new}"'))
def change_image_alt(page: Page, old: str, new: str):
    _mark_page(page)
    page.get_by_label(f"Details for {old}").click()
    expect(page.locator("#image-edit-alt")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    page.locator("#image-edit-alt").fill(new)
    page.get_by_role("button", name="Save alt").click()
    expect(page.locator("#image-edit-alt")).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@when(parsers.parse('I delete "{name}" from its details modal'))
def delete_image_from_details(page: Page, name: str):
    page.get_by_label(f"Details for {name}").click()
    expect(page.locator("#image-edit-alt")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    page.get_by_role("button", name="Delete image").click()
    expect(page.locator("#image-edit-alt")).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


# =============================================================================
# Then Steps
# =============================================================================


@then("the registration page should have no inline script body")
def no_inline_script_body(page: Page):
    """Every executable script on the page is a src= reference to a built bundle.

    The JSON data block is excluded: the browser does not run it, which is why the
    configuration can live there.
    """
    inline = page.evaluate(
        """() => Array.from(document.querySelectorAll('script:not([src])'))
                     .filter(s => s.type !== 'application/json')
                     .map(s => s.textContent.trim())
                     .filter(Boolean)"""
    )
    assert inline == []


@then("the assets panel should respond to Alpine")
def assets_panel_responds(page: Page):
    """Opening the upload modal proves the bundle loaded and registered before alpine:init.

    The modal is behind an x-if, so it does not exist in the served HTML at all - if the
    component were not registered, nothing would appear however many times it is clicked.
    """
    open_image_upload_modal(page)


@then("the image upload button should be disabled")
def upload_button_disabled(page: Page):
    """Alt text is required, and the guard is the disabled button rather than an error."""
    upload = page.get_by_role("dialog", name="Upload image").get_by_role("button", name="Upload")
    expect(upload).to_be_disabled(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the assets panel should list an image called "{name}"'))
def panel_lists_image(page: Page, name: str):
    expect(page.get_by_label(f"Details for {name}")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the assets panel should not list an image called "{name}"'))
def panel_does_not_list_image(page: Page, name: str):
    expect(page.get_by_label(f"Details for {name}")).to_have_count(0, timeout=PLAYWRIGHT_TIMEOUT)


@then("the assets panel should list no images")
def panel_lists_no_images(page: Page):
    expect(page.get_by_text("No images uploaded yet.")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then(parsers.parse('the assets panel should list a document called "{name}"'))
def panel_lists_document(page: Page, name: str):
    expect(page.get_by_label(f"Details for {name}")).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)


@then("the page should not have reloaded")
def page_did_not_reload(page: Page):
    assert page.evaluate("() => window.__assetsPanelStillLoaded === true"), (
        "the page navigated - the assets panel is supposed to mutate its list in place"
    )
