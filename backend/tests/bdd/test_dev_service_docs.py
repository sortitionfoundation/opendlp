"""ABOUTME: BDD tests for the service docs console after its script extraction
ABOUTME: Confirms in a real browser that the bundle loads and the execute route accepts its posts

The component tests in tests/component/test_dev_service_docs_page.py cover the markup, the
data block and that every bound method exists in src/js/. Only a browser can tell us the
bundle really loads, Alpine registers the component, and the CSRF token in that data block
satisfies /dev/service-docs/execute.
"""

import re

import pytest
from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from .config import PLAYWRIGHT_TIMEOUT, Urls

scenarios("../../features/dev-service-docs.feature")

SERVICE_DOCS_URL = f"{Urls.base}/backoffice/dev/service-docs"


@pytest.fixture
def service_docs_page(admin_logged_in_page: Page) -> Page:
    page = admin_logged_in_page
    page.goto(SERVICE_DOCS_URL)
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def assembly_tab_page(admin_logged_in_page: Page) -> Page:
    page = admin_logged_in_page
    page.goto(f"{SERVICE_DOCS_URL}?tab=assembly")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def emails_tab_page(admin_logged_in_page: Page) -> Page:
    page = admin_logged_in_page
    page.goto(f"{SERVICE_DOCS_URL}?tab=emails")
    page.wait_for_load_state("networkidle")
    return page


def _execute_button(page: Page, loading_key: str):
    """The Execute button of one service's form.

    Found by the Alpine binding that disables it while that service runs, which is the
    only thing on the page that is unique per service - the buttons all read "Execute"
    and the forms have no ids.
    """
    return page.locator(f'[\\:disabled="loading.{loading_key}"]')


def _response_panel(page: Page, key: str):
    """The <pre> a service's formatted response is written into."""
    return page.locator(f"[x-text=\"formatResponse('{key}')\"]")


# =============================================================================
# Given Steps
# =============================================================================


@given("a user is logged in as an admin")
def user_logged_in_as_admin(admin_logged_in_page: Page):
    """Background step: the console is admin-gated and dev-only."""


@given("the user is on the service docs console")
def user_on_service_docs(service_docs_page: Page):
    """The fixture handles navigation."""


@given("the user is on the service docs assembly tab")
def user_on_assembly_tab(assembly_tab_page: Page):
    """The fixture handles navigation."""


@given("the user is on the service docs emails tab")
def user_on_emails_tab(emails_tab_page: Page):
    """The fixture handles navigation."""


# =============================================================================
# When Steps
# =============================================================================


@when("the user loads the respondents CSV sample")
def load_respondents_sample(service_docs_page: Page):
    service_docs_page.get_by_role("button", name="Load Sample").first.click()


@when('the user creates an assembly called "Console Created Assembly"')
def create_assembly(assembly_tab_page: Page):
    page = assembly_tab_page
    page.locator("[x-model='createAssemblyTitle']").fill("Console Created Assembly")
    page.locator("[x-model='createAssemblyQuestion']").fill("Does the console work?")
    page.locator("[x-model='createAssemblyNumberToSelect']").fill("12")
    _execute_button(page, "create_assembly").click()


@when("the user asks for an email template that does not exist")
def get_missing_email_template(emails_tab_page: Page):
    """A free-text id field, unlike the assembly tab's select of existing assemblies -
    which is the only way to ask the server for something that is not there."""
    page = emails_tab_page
    page.locator("[x-model='getTemplateId']").fill("00000000-0000-4000-8000-000000000000")
    _execute_button(page, "get_email_template").click()


# =============================================================================
# Then Steps
# =============================================================================


@then("the console should have no inline script body")
def no_inline_script_body(service_docs_page: Page):
    """Every executable script on the page is a src= reference to a built bundle.

    The JSON data block is excluded - the browser does not run it, which is why the
    configuration can live there.
    """
    inline = service_docs_page.evaluate(
        """() => Array.from(document.querySelectorAll('script:not([src])'))
                     .filter(s => s.type !== 'application/json')
                     .map(s => s.textContent.trim())
                     .filter(Boolean)"""
    )
    assert inline == []


@then("the console forms should respond to Alpine")
def forms_respond_to_alpine(service_docs_page: Page):
    """x-cloak is lifted from the controller's root only once Alpine has initialised it.

    If the bundle failed to register the component, Alpine would leave the attribute in
    place and the whole page would stay hidden.
    """
    root = service_docs_page.locator("[x-data='serviceDocsController()']")
    expect(root).to_be_visible(timeout=PLAYWRIGHT_TIMEOUT)
    assert root.get_attribute("x-cloak") is None


@then("the respondents CSV field should hold the sample data")
def csv_field_holds_sample(service_docs_page: Page):
    """The samples moved into src/js/components/service-docs/samples.js with the rest."""
    field = service_docs_page.locator("[x-model='importRespondentsCsvContent']")
    # The first line of IMPORT_RESPONDENTS_CSV, enough to identify it.
    expect(field).to_have_value(re.compile(r"external_id,name,email"), timeout=PLAYWRIGHT_TIMEOUT)


@then("the create assembly panel should show a success response")
def create_panel_shows_success(assembly_tab_page: Page):
    expect(_response_panel(assembly_tab_page, "create_assembly")).to_contain_text(
        '"status": "success"', timeout=PLAYWRIGHT_TIMEOUT
    )


@then("the response should name the assembly that was created")
def response_names_the_assembly(assembly_tab_page: Page):
    expect(_response_panel(assembly_tab_page, "create_assembly")).to_contain_text(
        "Console Created Assembly", timeout=PLAYWRIGHT_TIMEOUT
    )


@then("the get email template panel should show an error response")
def get_template_panel_shows_error(emails_tab_page: Page):
    """A failed service reports in its own panel - there is no toast for a failure."""
    expect(_response_panel(emails_tab_page, "get_email_template")).to_contain_text(
        '"status": "error"', timeout=PLAYWRIGHT_TIMEOUT
    )
