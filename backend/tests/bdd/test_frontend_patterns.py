"""ABOUTME: BDD tests for the frontend patterns reference page after its script extraction
ABOUTME: Confirms in a real browser that the built bundle registers and drives the components

The component tests in tests/component/test_dev_patterns_page.py cover the markup and the
script tag. Only a browser can tell us the bundle actually loads and Alpine picks it up -
which is the risk that came with moving the components out of an inline block.
"""

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from tests.bdd.config import Urls

scenarios("../../features/frontend-patterns.feature")


@pytest.fixture
def patterns_page(admin_logged_in_page: Page) -> Page:
    page = admin_logged_in_page
    page.goto(Urls.backoffice_patterns)
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def file_upload_page(admin_logged_in_page: Page) -> Page:
    page = admin_logged_in_page
    page.goto(f"{Urls.backoffice_patterns}?tab=file-upload")
    page.wait_for_load_state("networkidle")
    return page


def _write(tmp_path: Path, name: str, contents: str) -> str:
    path = tmp_path / name
    path.write_text(contents)
    return str(path)


# =============================================================================
# Given Steps
# =============================================================================


@given("a user is logged in as an admin")
def user_logged_in_as_admin(admin_logged_in_page: Page):
    """Background step: the patterns page is admin-gated."""


@given("the user is on the frontend patterns page")
def user_on_patterns_page(patterns_page: Page):
    """The fixture handles navigation."""


@given("the user is on the file upload patterns tab")
def user_on_file_upload_tab(file_upload_page: Page):
    """The fixture handles navigation."""


# =============================================================================
# When Steps
# =============================================================================


@when("the user chooses a CSV file in the demo")
def choose_csv_file(file_upload_page: Page, tmp_path: Path):
    file_upload_page.set_input_files("#demo-file", _write(tmp_path, "people.csv", "name,age\n" + "x" * 2048))


@when("the user chooses a text file in the demo")
def choose_text_file(file_upload_page: Page, tmp_path: Path):
    file_upload_page.set_input_files("#demo-file", _write(tmp_path, "notes.txt", "hello"))


@when("the user clicks the copy button for the urlSelect sample")
def click_copy_url_select(patterns_page: Page):
    patterns_page.click('button:has-text("Copy")')


# =============================================================================
# Then Steps
# =============================================================================


@then("the page should have no inline script body")
def page_has_no_inline_script(patterns_page: Page):
    """Every <script> is a src= reference, so nothing on the page needs a CSP exemption."""
    inline_count = patterns_page.evaluate(
        """
        Array.from(document.querySelectorAll('script'))
            .filter(s => !s.src && s.textContent.trim().length > 0).length
        """
    )
    assert inline_count == 0, f"expected no inline script bodies, found {inline_count}"


@then("the patterns Alpine components should be registered")
def components_are_registered(patterns_page: Page):
    """x-cloak is only removed once Alpine has initialised the x-data root.

    If the bundle failed to load, or loaded too late for alpine:init, the root
    element keeps x-cloak and stays hidden - which is exactly the silent failure
    this scenario exists to catch.
    """
    root = patterns_page.locator('[x-data="patternsController()"]')
    expect(root).to_be_visible()


@then("the demo should show the file name and size")
def demo_shows_file_name_and_size(file_upload_page: Page):
    expect(file_upload_page.locator('[x-text="fileName"]')).to_have_text("people.csv")
    expect(file_upload_page.locator('[x-text="fileSize"]')).to_have_text("2.0 KB")


@then("the demo should show a file type error")
def demo_shows_file_type_error(file_upload_page: Page):
    expect(file_upload_page.locator('[x-text="error"]')).to_have_text("Please select a CSV file")


@then("the demo should show no file name")
def demo_shows_no_file_name(file_upload_page: Page):
    expect(file_upload_page.locator('[x-text="fileName"]')).to_be_hidden()


@then("a toast should appear")
def toast_appears(patterns_page: Page):
    """The message depends on whether the browser grants clipboard access.

    Either outcome proves the component is registered and reactive, which is what
    is being tested here - the clipboard itself is the browser's business.
    """
    toast = patterns_page.locator('[x-text="toast.message"]')
    expect(toast).to_be_visible()
    assert toast.inner_text() in ("Copied to clipboard!", "Failed to copy")
