"""ABOUTME: BDD tests for backoffice UI (Pines UI + Tailwind CSS)
ABOUTME: Tests the separate design system used for admin interfaces"""

import os

import pytest
from playwright.sync_api import Page, expect, sync_playwright
from pytest_bdd import given, scenarios, then, when

from .config import Urls

# Load all scenarios from the feature file
scenarios("../../features/backoffice.feature")


# Override fixtures for backoffice tests - no Celery needed for static pages
@pytest.fixture(scope="module")
def backoffice_browser():
    """Browser instance for backoffice tests only."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=os.getenv("CI", "false").lower() == "true")
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def backoffice_context(backoffice_browser, test_server):
    """Browser context without Celery dependency."""
    context = backoffice_browser.new_context()
    context.set_default_navigation_timeout(5000)
    context.set_default_timeout(5000)
    yield context
    context.close()


@pytest.fixture(scope="function")
def page(backoffice_context):
    """Override page fixture to use backoffice_context (no Celery)."""
    page = backoffice_context.new_page()
    yield page
    page.close()


# Showcase Page Tests


@given("I am on the backoffice showcase page")
def visit_backoffice_showcase(page: Page):
    """Navigate to the backoffice showcase page."""
    page.goto(Urls.backoffice_showcase)


@then('I should see "Component Showcase"')
def see_component_showcase_text(page: Page):
    """Verify the Component Showcase heading is visible."""
    heading = page.locator("h1")
    expect(heading).to_contain_text("Component Showcase")


@then('I should see "Alpine.js Interactivity"')
def see_alpine_interactivity_text(page: Page):
    """Verify the Alpine.js section heading is visible."""
    expect(page.locator("body")).to_contain_text("Alpine.js Interactivity")


@then('I should see "Design Tokens"')
def see_design_tokens_text(page: Page):
    """Verify the Design Tokens section heading is visible."""
    expect(page.locator("body")).to_contain_text("Design Tokens")


# Design Token Tests


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


# Alpine.js Tests


@then("the Alpine message should be hidden")
def alpine_message_hidden(page: Page):
    """Verify the Alpine.js toggle message is hidden."""
    message = page.locator("#alpine-message")
    expect(message).to_be_hidden()


@then("the Alpine message should be visible")
def alpine_message_visible(page: Page):
    """Verify the Alpine.js toggle message is visible."""
    message = page.locator("#alpine-message")
    expect(message).to_be_visible()


@when("I click the Alpine toggle button")
def click_alpine_toggle(page: Page):
    """Click the Alpine.js toggle button."""
    button = page.locator("#alpine-toggle")
    button.click()


@then('I should see "Alpine.js is working!"')
def see_alpine_working_text(page: Page):
    """Verify the Alpine.js confirmation message is visible."""
    expect(page.locator("body")).to_contain_text("Alpine.js is working!")


# Button Component Tests (Iteration 5)


@then("I should see the primary button")
def see_primary_button(page: Page):
    """Verify the primary button is visible."""
    button = page.locator("#btn-primary")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Primary")


@then("I should see the secondary button")
def see_secondary_button(page: Page):
    """Verify the secondary button is visible."""
    button = page.locator("#btn-secondary")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Secondary")


@then("I should see the outline button")
def see_outline_button(page: Page):
    """Verify the outline button is visible."""
    button = page.locator("#btn-outline")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Outline")


@then("I should see the disabled button")
def see_disabled_button(page: Page):
    """Verify the disabled button is visible."""
    button = page.locator("#btn-disabled")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Disabled")


@then("the primary button should have the brand orange background")
def primary_button_has_orange_background(page: Page):
    """Verify primary button uses --color-button-primary-bg (#D7764E)."""
    button = page.locator("#btn-primary")
    # Brand orange #D7764E = rgb(215, 118, 78)
    background_color = button.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(215, 118, 78)", f"Expected brand orange, got {background_color}"


@then("the secondary button should have the brand plum background")
def secondary_button_has_plum_background(page: Page):
    """Verify secondary button uses --color-button-secondary-bg (#501D43)."""
    button = page.locator("#btn-secondary")
    # Brand plum #501D43 = rgb(80, 29, 67)
    background_color = button.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(80, 29, 67)", f"Expected brand plum, got {background_color}"


@then("the disabled button should be disabled")
def disabled_button_is_disabled(page: Page):
    """Verify the disabled button has the disabled attribute."""
    button = page.locator("#btn-disabled")
    expect(button).to_be_disabled()


# Card Component Tests (Iteration 6)


@then("I should see the basic card")
def see_basic_card(page: Page):
    """Verify the basic card is visible."""
    card = page.locator("#card-basic")
    expect(card).to_be_visible()


@then("I should see the card with header")
def see_card_with_header(page: Page):
    """Verify the card with header is visible."""
    card = page.locator("#card-header")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Card with Header")


@then("I should see the card with actions")
def see_card_with_actions(page: Page):
    """Verify the card with actions is visible."""
    card = page.locator("#card-actions")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Card with Actions")


@then("the card with actions should contain buttons")
def card_with_actions_has_buttons(page: Page):
    """Verify the card with actions contains Save and Cancel buttons."""
    card = page.locator("#card-actions")
    expect(card.locator("button", has_text="Save")).to_be_visible()
    expect(card.locator("button", has_text="Cancel")).to_be_visible()
