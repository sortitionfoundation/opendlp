from playwright.sync_api import Page, expect
from pytest_bdd import scenarios, then, when

scenarios("../../features/user-data-agreement.feature")

# most stages defined in shared/ui_shared.py
# included from conftest via `pytest_plugins`


@when("the user clicks on the link to the data agreement")
def click_link_data_agreement(page: Page):
    page.click("")


@when("the data agreement is not accepted")
def data_agreement_not_accepted(page: Page):
    page.get_by_label("Accept Data Agreement").uncheck()


@when("the data agreement is accepted")
def data_agreement_is_accepted(page: Page):
    page.get_by_label("Accept Data Agreement").check()


@then("the user sees the data agreement text")
def see_data_agreement_text(page: Page):
    expect(page).to_have_title("User Data Agreement - OpenDLP")
    locator = page.locator("body > .main")
    expect(locator).to_contain_text("You agree to let the Sortition Foundation to hold")
