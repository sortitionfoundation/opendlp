from playwright.sync_api import Page, expect
from pytest_bdd import scenarios, then, when

from tests.bdd.config import Urls

scenarios("../../features/user-data-agreement.feature")

# most stages defined in shared/ui_shared.py
# included from conftest via `pytest_plugins`


@when("the user goes to the data agreement")
def _(page: Page):
    """the user goes to the data agreement."""
    # first find the link on the registration page
    data_agreement_link = page.get_by_role("link", name="View data agreement")
    expect(data_agreement_link).to_be_visible()
    # the link is opened in a new tab - first we check that the new
    # page has the expected URL
    with page.context.expect_page() as data_agreement_page:
        data_agreement_link.click()
    expect(data_agreement_page.value).to_have_url(Urls.user_data_agreement)
    # now we've confirmed the NEW page has the expected URL
    # we manually navigate the original page to that URL, so that
    # we are ready for the "then" step to check the contents of the page
    page.goto(Urls.user_data_agreement)


@then("the user sees the data agreement text")
def see_data_agreement_text(page: Page):
    expect(page).to_have_title("User Data Agreement - OpenDLP")
    expect(page.locator(".main")).to_contain_text("You agree to let the Sortition Foundation hold")
