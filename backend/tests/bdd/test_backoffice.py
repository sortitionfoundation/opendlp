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
