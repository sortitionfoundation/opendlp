"""ABOUTME: BDD tests for the draft home page served at /newhome
ABOUTME: Drives a real browser to check the hero renders, sign-in works from it, and it fits a phone screen"""

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from .config import Urls

scenarios("../../features/home-page-draft.feature")

NEWHOME_URL = f"{Urls.base}/newhome"


@given("an anonymous visitor opens the draft home page")
def open_draft_home_page(logged_out_page: Page) -> None:
    logged_out_page.goto(NEWHOME_URL)


@given("an anonymous visitor opens the draft home page on a phone")
def open_draft_home_page_on_phone(logged_out_page: Page) -> None:
    logged_out_page.set_viewport_size({"width": 375, "height": 800})
    logged_out_page.goto(NEWHOME_URL)
    logged_out_page.wait_for_load_state("networkidle")


@then("they should see the draft home page hero")
def see_hero(logged_out_page: Page) -> None:
    expect(logged_out_page.get_by_role("heading", level=1)).to_contain_text("simplicity")
    expect(logged_out_page.get_by_role("img", name="OpenDLP - Democratic Lottery Platform")).to_be_visible()


@when("they choose to sign in from the draft home page")
def choose_sign_in(logged_out_page: Page) -> None:
    # The sign-in panel's button, not the footer link of the same name.
    logged_out_page.get_by_role("main").get_by_role("button", name="Sign in").click()


@then("they should be on the sign in page")
def on_sign_in_page(logged_out_page: Page) -> None:
    expect(logged_out_page).to_have_url(Urls.login)


@then("the draft home page should not scroll sideways")
def no_horizontal_scroll(logged_out_page: Page) -> None:
    overflow = logged_out_page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow == 0
