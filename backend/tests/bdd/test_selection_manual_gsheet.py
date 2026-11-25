"""ABOUTME: BDD steps running selection.feature against a project whose data is in a Google Sheet
ABOUTME: Drives the data source settings dialog and the Selection tab's progress and replacement dialogs"""

from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, scenarios, then, when

from opendlp.domain.assembly import Assembly
from tests.bdd.config import Urls
from tests.data import VALID_GSHEET_URL

"""
Note this file is one of several that will run selection.feature  This one is for
manual set up of Google Spreadsheets.  Others will be for auto set up of Google Spreadsheets
and eventually for when the data is all in the database.

The idea is that the feature file describes the process at a high level. So we can have
multiple implementations that use the exact same feature file.
"""

scenarios("../../features/selection.feature")

TARGETS_FOUND = "Found 4 targets with a total of 20 values"


@given("people are registered")
def _():
    """people are registered."""
    # For this version, the registrants details are in the GSheet


@given("the assembly is set up", target_fixture="assembly_to_select")
def _(assembly_creator):
    """the assembly is set up for "manual gsheet setup"."""
    return assembly_creator("Assembly to select", number_to_select=22)


def _settings_dialog(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Data source settings")


def _progress_modal(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Task progress")


def _replacement_modal(page: Page) -> Locator:
    return page.get_by_role("dialog", name="Replacement Selection")


def _open_selection_tab(page: Page, assembly: Assembly) -> None:
    page.goto(Urls.backoffice_assembly_url(str(assembly.id)))
    page.get_by_role("tab", name="Select and Replace", exact=True).click()
    expect(page).to_have_url(Urls.assembly_selection(assembly.id))


def _open_replacement_modal(page: Page, assembly: Assembly) -> None:
    _open_selection_tab(page, assembly)
    page.get_by_role("button", name="Select replacements").click()
    expect(_replacement_modal(page)).to_be_visible()


@when("I open the Assembly")
def _(admin_logged_in_page: Page, assembly_to_select):
    """I open the Assembly and say its data is in a Google Sheet."""
    page = admin_logged_in_page
    page.goto(Urls.backoffice_assembly_url(str(assembly_to_select.id)))
    page.get_by_role("button", name="Data source settings", exact=True).click()
    dialog = _settings_dialog(page)
    expect(dialog).to_be_visible()
    with page.expect_response(lambda response: response.url.endswith("/data-source/refresh")):
        dialog.locator("#project-location").select_option(label="In Google Sheets")


@then("I can configure the options for selection")
def _(page: Page):
    """I can configure the options for selection in "manual gsheet setup"."""
    dialog = _settings_dialog(page)
    expect(dialog.get_by_text("Generate remaining tab", exact=True)).to_be_visible()
    check_same_address = dialog.get_by_label("Check same address")
    expect(check_same_address).to_be_checked()
    # the box itself is drawn by its label, so that is what takes the click
    dialog.locator("label.checkbox-container").filter(has=page.locator("#check_same_address")).click()
    expect(check_same_address).not_to_be_checked()


@then("I can specify the categories and targets")
def _(page: Page):
    """I can specify the categories and targets in "manual gsheet setup"."""
    # the initial selection and the replacements each have a "Categories tab" field
    expect(_settings_dialog(page).locator('[name="select_targets_tab"]')).to_be_visible()


@then("I can specify the source of the respondents data")
def _(page: Page):
    """I can specify the source of the respondents data in "manual gsheet setup"."""
    dialog = _settings_dialog(page)
    url_field = dialog.get_by_label("Spreadsheet URL")
    expect(url_field).to_be_visible()
    url_field.fill(VALID_GSHEET_URL)
    # the initial selection and the replacements each have a "Respondents tab" field
    respondents_field = dialog.locator('[name="select_registrants_tab"]')
    expect(respondents_field).to_be_visible()
    respondents_field.fill("All respondents")


@then("I can save the options")
def _(page: Page, assembly_to_select):
    """I can save the options, and the details page then shows the spreadsheet."""
    with page.expect_response(lambda response: response.url.endswith("/data-source/save")):
        _settings_dialog(page).get_by_role("button", name="Save", exact=True).click()
    expect(_settings_dialog(page)).to_have_count(0)
    card = page.locator("#data-source")
    expect(card).to_contain_text("In Google Sheets")
    expect(card.get_by_role("link", name=VALID_GSHEET_URL)).to_be_visible()


@given("the selection options are set", target_fixture="assembly_to_select")
def _(assembly_gsheet_creator):
    """the options are set."""
    assembly, _ = assembly_gsheet_creator("Configured assembly to select")
    return assembly


@when("I check the data")
def _(admin_logged_in_page: Page, assembly_to_select: Assembly):
    """I check the data, from the Selection tab."""
    page = admin_logged_in_page
    _open_selection_tab(page, assembly_to_select)
    expect(page.get_by_role("button", name="Run Selection", exact=True)).to_be_visible()
    page.get_by_role("button", name="Check Spreadsheet").click()
    expect(_progress_modal(page)).to_be_visible()


@when("I start the selection")
def _(admin_logged_in_page: Page, assembly_to_select: Assembly):
    """I start the selection, from the Selection tab."""
    page = admin_logged_in_page
    _open_selection_tab(page, assembly_to_select)
    page.get_by_role("button", name="Run Selection", exact=True).click()
    expect(_progress_modal(page)).to_be_visible()


def _expect_told_in_progress_modal(page: Page) -> None:
    told = _progress_modal(page).get_by_text(TARGETS_FOUND).first
    expect(told).to_be_attached(timeout=30_000)
    expect(_progress_modal(page).get_by_role("button", name="Close").first).to_be_visible(timeout=30_000)
    # A finished task's messages are collapsed
    _progress_modal(page).locator("details:not([open]) > summary").filter(has_text="Messages").click()
    expect(told).to_be_visible()


@then("I am told the number of categories and category values")
def _(page: Page):
    """I am told the number of categories and category values, in the messages of the check.

    The replacement dialog moves straight on to asking how many to select, and
    the messages of its check are then read from the selection history. That is
    done in a second tab, so the dialog is still there for the next step.
    """
    if not _replacement_modal(page).count():
        _expect_told_in_progress_modal(page)
        return
    expect(_replacement_modal(page).get_by_label("Number of people to select")).to_be_visible(timeout=30_000)
    run_id = parse_qs(urlparse(page.url).query)["current_replacement"][0]
    history_page = page.context.new_page()
    history_page.goto(f"{page.url.split('?')[0]}/history/{run_id}")
    _expect_told_in_progress_modal(history_page)
    history_page.close()


@then("I am told selection has completed")
def _(page: Page):
    """I am told selection has completed."""
    expect(page.get_by_role("dialog").get_by_text("Task completed successfully.").first).to_be_visible(timeout=30_000)


@when("I initialise the replacements process")
def _(admin_logged_in_page: Page, assembly_to_select: Assembly):
    """I initialise the replacements process."""
    _open_replacement_modal(admin_logged_in_page, assembly_to_select)
    _replacement_modal(admin_logged_in_page).get_by_role("button", name="Check Spreadsheet").click()


@then("I am asked for the number to select")
def _(page: Page):
    """I am asked for the number to select."""
    number_input = _replacement_modal(page).get_by_label("Number of people to select")
    expect(number_input).to_be_visible(timeout=30_000)
    expect(number_input).to_be_enabled()


@given("the replacements process is initialised", target_fixture="assembly_to_select")
def _(admin_logged_in_page: Page, assembly_gsheet_creator):
    """the replacements process is initialised."""
    assembly, _ = assembly_gsheet_creator("Configured assembly to select")
    _open_replacement_modal(admin_logged_in_page, assembly)
    modal = _replacement_modal(admin_logged_in_page)
    modal.get_by_role("button", name="Check Spreadsheet").click()
    expect(modal.get_by_label("Number of people to select")).to_be_visible(timeout=30_000)
    return assembly


@given("I have set the number to select")
def _(page: Page):
    """I have set the number to select."""
    number_input = _replacement_modal(page).get_by_label("Number of people to select")
    expect(number_input).to_be_enabled()
    number_input.fill("22")


@when("I start the replacements")
def _(page: Page):
    """I start the replacements."""
    button = _replacement_modal(page).get_by_role("button", name="Run Replacement Selection")
    expect(button).to_be_enabled()
    button.click()
