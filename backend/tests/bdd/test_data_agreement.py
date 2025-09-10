from playwright.sync_api import Page, expect
from pytest_bdd import scenarios, then, when

from tests.bdd.config import Urls
from tests.bdd.helpers import check_follow_link

scenarios("../../features/user-data-agreement.feature")

# most stages defined in shared/ui_shared.py
# included from conftest via `pytest_plugins`


@when("the user goes to the data agreement")
def _(page: Page):
    """the user goes to the data agreement."""
    check_follow_link(page, link_name="View data agreement", link_url=Urls.user_data_agreement)


@then("the user sees the data agreement text")
def see_data_agreement_text(page: Page):
    expect(page).to_have_title("User Data Agreement - OpenDLP")
    expect(page.locator(".main")).to_contain_text("You agree to let the Sortition Foundation hold")
