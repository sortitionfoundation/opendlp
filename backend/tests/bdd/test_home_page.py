"""ABOUTME: BDD tests for the public home page served at /
ABOUTME: Drives a real browser to check the hero renders, sign-in works from it, the demo sits where the layout says, plays and pauses, and it fits a phone"""

import re

from playwright.sync_api import Locator, Page, expect
from pytest_bdd import given, scenarios, then, when

from .config import Urls

scenarios("../../features/home-page.feature")

# the class the demo's script sets while it plays
RUNNING = re.compile(r"(^|\s)is-running(\s|$)")

# What the demo shows at a moment: the screen, where the cursor is, and what has been typed.
DEMO_STATE = """() => {
    const root = document.querySelector("[data-hero-demo]");
    return JSON.stringify({
        scene: root.querySelector(".hero-demo__scene.is-active")?.dataset.scene,
        cursor: getComputedStyle(root.querySelector('[data-demo="cursor"]')).transform,
        typed: [...root.querySelectorAll("[data-type]")].map((input) => input.value),
    });
}"""


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


@given("an anonymous visitor who prefers reduced motion opens the home page")
def open_home_page_with_reduced_motion(logged_out_page: Page) -> None:
    logged_out_page.emulate_media(reduced_motion="reduce")
    logged_out_page.set_viewport_size({"width": 1440, "height": 900})
    logged_out_page.goto(Urls.front_page)
    logged_out_page.wait_for_load_state("networkidle")


@then("they should see the home page hero")
def see_hero(logged_out_page: Page) -> None:
    expect(logged_out_page.get_by_role("heading", level=1)).to_contain_text("Bringing Simplicity to Sortition")
    expect(logged_out_page.locator("[data-hero-visual]")).to_be_visible()


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
    demo = page.locator("[data-hero-visual]").bounding_box()
    assert heading is not None
    assert demo is not None
    return heading, demo


@then("the product demo should sit to the right of the heading")
def demo_beside_heading(logged_out_page: Page) -> None:
    heading, demo = _hero_boxes(logged_out_page)
    assert demo["x"] >= heading["x"] + heading["width"]


@then("the product demo should sit below the heading")
def demo_below_heading(logged_out_page: Page) -> None:
    heading, demo = _hero_boxes(logged_out_page)
    assert demo["y"] >= heading["y"] + heading["height"]


@then("the product demo should move on from its first screen")
def demo_plays(logged_out_page: Page) -> None:
    demo = logged_out_page.locator("[data-hero-demo]")
    expect(demo).to_have_class(RUNNING)
    # Your projects first; the cursor clicks Create project about two seconds in.
    expect(demo.locator('[data-scene="create"]')).to_be_visible(timeout=10_000)


@then("the product demo should rest on the dashboard screen")
def demo_at_rest(logged_out_page: Page) -> None:
    demo = logged_out_page.locator("[data-hero-demo]")
    expect(demo.locator('[data-scene="dashboard"]')).to_be_visible()
    # A playing demo opens on Your projects, with the cursor showing.
    expect(demo.locator('[data-scene="projects"]')).to_be_hidden()
    expect(demo.locator('[data-demo="cursor"]')).to_be_hidden()
    expect(demo).not_to_have_class(RUNNING)


@then("there should be no button to pause the demo")
def no_pause_button(logged_out_page: Page) -> None:
    expect(logged_out_page.locator("[data-hero-demo-toggle]")).to_be_hidden()


def _pause_button(page: Page) -> Locator:
    return page.get_by_role("button", name="Pause the demo")


@when("they pause the product demo from the keyboard")
def pause_demo_from_keyboard(logged_out_page: Page) -> None:
    toggle = _pause_button(logged_out_page)
    # Tab from the top of the page until the button has focus, so it is in the tab order.
    for _ in range(20):
        logged_out_page.keyboard.press("Tab")
        if toggle.evaluate("button => button === document.activeElement"):
            break
    expect(toggle).to_be_focused()
    logged_out_page.keyboard.press("Space")
    expect(toggle).to_have_attribute("aria-pressed", "true")


@then("the product demo should hold still")
def demo_holds_still(logged_out_page: Page) -> None:
    held = logged_out_page.evaluate(DEMO_STATE)
    logged_out_page.wait_for_timeout(3_000)
    assert logged_out_page.evaluate(DEMO_STATE) == held


@when("they play the product demo from the keyboard")
def play_demo_from_keyboard(logged_out_page: Page) -> None:
    toggle = _pause_button(logged_out_page)
    expect(toggle).to_be_focused()
    logged_out_page.keyboard.press("Enter")
    expect(toggle).to_have_attribute("aria-pressed", "false")


@then("the product demo should move on again")
def demo_moves_on_again(logged_out_page: Page) -> None:
    held = logged_out_page.evaluate(DEMO_STATE)
    logged_out_page.wait_for_function(f"(held) => ({DEMO_STATE})() !== held", arg=held, timeout=10_000)
