"""ABOUTME: BDD tests for the public home page served at /
ABOUTME: Drives a real browser to check the hero renders, sign-in works from it, the demo sits where the layout says, and it fits a phone"""

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then, when

from .config import Urls

scenarios("../../features/home-page.feature")


@given("an anonymous visitor opens the home page")
def open_home_page(logged_out_page: Page) -> None:
    logged_out_page.goto(Urls.front_page)


@given("an anonymous visitor opens the home page on a phone")
def open_home_page_on_phone(logged_out_page: Page) -> None:
    logged_out_page.set_viewport_size({"width": 375, "height": 800})
    logged_out_page.goto(Urls.front_page)
    logged_out_page.wait_for_load_state("networkidle")


@given("an anonymous visitor opens the home page on a wide screen")
def open_home_page_on_wide_screen(logged_out_page: Page) -> None:
    logged_out_page.set_viewport_size({"width": 1440, "height": 900})
    logged_out_page.goto(Urls.front_page)
    logged_out_page.wait_for_load_state("networkidle")


@then("they should see the home page hero")
def see_hero(logged_out_page: Page) -> None:
    expect(logged_out_page.get_by_role("heading", level=1)).to_contain_text("Bringing Simplicity to Sortition")
    expect(logged_out_page.locator("[data-hero-demo]")).to_be_visible()


@when("they choose to sign in from the home page")
def choose_sign_in(logged_out_page: Page) -> None:
    # The sign-in panel's button, not the footer link of the same name.
    logged_out_page.get_by_role("main").get_by_role("button", name="Sign in").click()


@then("they should be on the sign in page")
def on_sign_in_page(logged_out_page: Page) -> None:
    expect(logged_out_page).to_have_url(Urls.login)


@then("the home page should not scroll sideways")
def no_horizontal_scroll(logged_out_page: Page) -> None:
    overflow = logged_out_page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert overflow == 0


def _hero_boxes(page: Page) -> tuple[dict[str, float], dict[str, float]]:
    heading = page.get_by_role("heading", level=1).bounding_box()
    drawing = page.locator("[data-hero-demo]").bounding_box()
    assert heading is not None
    assert drawing is not None
    return heading, drawing


@then("the product demo should sit to the right of the heading")
def animation_beside_heading(logged_out_page: Page) -> None:
    heading, drawing = _hero_boxes(logged_out_page)
    assert drawing["x"] >= heading["x"] + heading["width"]


@then("the product demo should sit below the heading")
def animation_below_heading(logged_out_page: Page) -> None:
    heading, drawing = _hero_boxes(logged_out_page)
    assert drawing["y"] >= heading["y"] + heading["height"]
