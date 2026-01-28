"""ABOUTME: BDD tests for backoffice UI (Pines UI + Tailwind CSS)
ABOUTME: Tests the separate design system used for admin interfaces"""

from playwright.sync_api import Page, expect
from pytest_bdd import given, scenarios, then

from .config import Urls

# Load all scenarios from the feature file
scenarios("../../features/backoffice.feature")


@given("I am on the backoffice hello page")
def visit_backoffice_hello(page: Page):
    """Navigate to the backoffice hello page."""
    page.goto(Urls.backoffice_hello)


@then('I should see "Hello from Backoffice!"')
def see_hello_text(page: Page):
    """Verify the hello heading is visible."""
    heading = page.locator("h1")
    expect(heading).to_contain_text("Hello from Backoffice!")


@then('I should see "Pines UI + Tailwind CSS"')
def see_design_system_text(page: Page):
    """Verify the design system description is visible."""
    expect(page.locator("body")).to_contain_text("Pines UI + Tailwind CSS")


@then("I should see the Tailwind test box")
def see_tailwind_test_box(page: Page):
    """Verify the Tailwind test box is visible."""
    test_box = page.locator("#tailwind-test")
    expect(test_box).to_be_visible()
    expect(test_box).to_contain_text("Tailwind CSS is working!")


@then("the Tailwind test box should have a blue background")
def tailwind_box_has_blue_background(page: Page):
    """Verify Tailwind CSS is applied by checking computed background color."""
    test_box = page.locator("#tailwind-test")
    # Tailwind's bg-blue-600 compiles to rgb(37, 99, 235)
    background_color = test_box.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(37, 99, 235)", f"Expected blue background, got {background_color}"


# Design Token Tests (Iteration 3)


@then("I should see the primary token box")
def see_primary_token_box(page: Page):
    """Verify the primary token box is visible."""
    token_box = page.locator("#token-primary")
    expect(token_box).to_be_visible()
    expect(token_box).to_contain_text("Primary")


@then("the primary token box should have the brand orange background")
def primary_token_has_orange_background(page: Page):
    """Verify design token --color-brand-primary (#D7764E) is applied."""
    token_box = page.locator("#token-primary")
    # Brand orange #D7764E = rgb(215, 118, 78)
    background_color = token_box.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(215, 118, 78)", f"Expected brand orange, got {background_color}"


@then("I should see the secondary token box")
def see_secondary_token_box(page: Page):
    """Verify the secondary token box is visible."""
    token_box = page.locator("#token-secondary")
    expect(token_box).to_be_visible()
    expect(token_box).to_contain_text("Secondary")


@then("the secondary token box should have the brand plum background")
def secondary_token_has_plum_background(page: Page):
    """Verify design token --color-brand-secondary (#501D43) is applied."""
    token_box = page.locator("#token-secondary")
    # Brand plum #501D43 = rgb(80, 29, 67)
    background_color = token_box.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(80, 29, 67)", f"Expected brand plum, got {background_color}"
