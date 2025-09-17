"""Democratic Lottery part 2 feature tests."""

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from tests.bdd.config import Urls

scenarios("../../features/selection.feature")


@given("people are registered")
def _():
    """people are registered."""
    # For this version, the registrants details are in the GSheet
    pass


@given('that the assembly is set up for "manual gsheet setup"', target_fixture="assembly_to_select")
def _(assembly_creator):
    """that the assembly is set up for "manual gsheet setup"."""
    # TODO: do this properly with a google sheet
    # assembly = assembly_creator("Assembly to select", gsheet_url=VALID_GSHEET_URL)
    assembly = assembly_creator("Assembly to select")
    return assembly


@when('I open the Assembly with "manual gsheet setup"')
def _(logged_in_page: Page, assembly_to_select):
    """I open the Assembly with "manual gsheet setup"."""
    # First navigate to the assembly view page
    view_url = Urls.for_assembly("view_assembly", assembly_to_select.id)
    logged_in_page.goto(view_url)

    # Then check that the Start Selection link goes to the gsheet_select page
    link = logged_in_page.get_by_role("link", name="Start Selection (Google Spreadsheet)")
    expect(link).to_be_visible()
    link.click()
    expect(logged_in_page).to_have_url(Urls.for_assembly("gsheet_select", assembly_to_select.id))


@then('I can configure the options for selection in "manual gsheet setup"')
def _(page: Page):
    """I can configure the options for selection in "manual gsheet setup"."""
    generate_remaining = page.get_by_label("Generate remaining tab")
    expect(generate_remaining).to_be_visible()


@then('I can specify the categories and targets in "manual gsheet setup"')
def _(page: Page):
    """I can specify the categories and targets in "manual gsheet setup"."""
    categories_field = page.get_by_label("Google Spreadsheet categories tab")
    expect(categories_field).to_be_visible()


@then('I can specify the source of the respondents data in "manual gsheet setup"')
def _(page: Page):
    """I can specify the source of the respondents data in "manual gsheet setup"."""
    respondents_field = page.get_by_label("Google Spreadsheet respondents tab")
    expect(respondents_field).to_be_visible()
