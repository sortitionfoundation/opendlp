"""Democratic Lottery part 2 feature tests."""

from playwright.sync_api import Page, expect
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


@given("people are registered")
def _():
    """people are registered."""
    # For this version, the registrants details are in the GSheet
    pass


@given("the assembly is set up", target_fixture="assembly_to_select")
def _(assembly_creator):
    """the assembly is set up for "manual gsheet setup"."""
    assembly = assembly_creator("Assembly to select")
    return assembly


@when("I open the Assembly")
def _(logged_in_page: Page, assembly_to_select):
    """I open the Assembly with "manual gsheet setup"."""
    # First navigate to the assembly view page
    view_url = Urls.for_assembly("view_assembly", str(assembly_to_select.id))
    logged_in_page.goto(view_url)

    # Then check that the Start Selection link goes to the gsheet_select page
    link = logged_in_page.get_by_role("link", name="Configure Google Spreadsheet")
    expect(link).to_be_visible()
    link.click()
    expect(logged_in_page).to_have_url(Urls.for_assembly("gsheet_configure", assembly_to_select.id))


@then("I can configure the options for selection")
def _(page: Page):
    """I can configure the options for selection in "manual gsheet setup"."""
    generate_remaining = page.get_by_label("Generate remaining tab")
    expect(generate_remaining).to_be_visible()


@then("I can specify the categories and targets")
def _(page: Page):
    """I can specify the categories and targets in "manual gsheet setup"."""
    # there are two fields named "Targets Tab Name" - so select the one in the first fieldset (group)
    categories_field = page.get_by_role("group", name="Initial/Test Selection").get_by_label("Targets Tab Name")
    expect(categories_field).to_be_visible()


@then("I can specify the source of the respondents data")
def _(page: Page):
    """I can specify the source of the respondents data in "manual gsheet setup"."""
    url_field = page.get_by_label("Google Spreadsheet URL")
    expect(url_field).to_be_visible()
    url_field.fill(VALID_GSHEET_URL)
    # there are two fields named "Respondents Tab Name" - so select the one in the first fieldset (group)
    respondents_field = page.get_by_role("group", name="Initial/Test Selection").get_by_label("Respondents Tab Name")
    expect(respondents_field).to_be_visible()
    respondents_field.fill("All respondents")


@then("I can save the options")
def _(page: Page, assembly_to_select):
    """I can specify the source of the respondents data in "manual gsheet setup"."""
    page.click('button[type="submit"]')
    expect(page).to_have_url(Urls.for_assembly("view_assembly", assembly_to_select.id))


@given("the selection options are set", target_fixture="assembly_to_select")
def _(assembly_gsheet_creator):
    """the options are set."""
    assembly, _ = assembly_gsheet_creator("Assembly to select")
    return assembly


@when("I check the data")
def _(logged_in_page: Page, assembly_to_select: Assembly):
    """I initialise selection."""
    # First navigate to the assembly view page
    view_url = Urls.for_assembly("view_assembly", str(assembly_to_select.id))
    logged_in_page.goto(view_url)

    # Then check that the Start Selection link goes to the gsheet_select page
    link = logged_in_page.get_by_role("link", name="Start Selection")
    expect(link).to_be_visible()
    link.click()
    expect(logged_in_page).to_have_url(Urls.for_assembly("gsheet_select", str(assembly_to_select.id)))

    # check the "run selection" link is enabled currently
    link = logged_in_page.get_by_role("button", name="Run Selection")
    expect(link).to_be_visible()

    # Then click "load Spreadsheet"
    link = logged_in_page.get_by_role("button", name="Load Spreadsheet")
    expect(link).to_be_visible()
    link.click()


@when("I start the selection")
def _(logged_in_page: Page, assembly_to_select: Assembly):
    """I start the selection."""
    # First navigate to the assembly view page
    view_url = Urls.for_assembly("view_assembly", str(assembly_to_select.id))
    logged_in_page.goto(view_url)

    # Then check that the Start Selection link goes to the gsheet_select page
    link = logged_in_page.get_by_role("link", name="Start Selection")
    expect(link).to_be_visible()
    link.click()
    expect(logged_in_page).to_have_url(Urls.for_assembly("gsheet_select", str(assembly_to_select.id)))

    # check the "run selection" link is enabled currently
    link = logged_in_page.get_by_role("button", name="Run Selection")
    expect(link).to_be_visible()
    # and click it
    link.click()


@then("I am told the number of categories and category values")
def _(page: Page):
    """I am told the number of categories and category values."""
    expect(page.get_by_text("Found 4 categories for targets with a total of 20 values")).to_be_visible(timeout=30_000)


@then("I am told selection is running")
def _(page: Page):
    """I am told selection is running."""
    expect(page.get_by_text("Running stratified selection with")).to_be_visible(timeout=10_000)


@then("I am told selection has completed")
def _(page: Page):
    """I am told selection has completed."""
    expect(page.get_by_text("Running stratified selection with")).to_be_visible(timeout=10_000)
