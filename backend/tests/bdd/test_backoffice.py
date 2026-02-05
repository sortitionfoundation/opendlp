"""ABOUTME: BDD tests for backoffice UI (Pines UI + Tailwind CSS)
ABOUTME: Tests the separate design system used for admin interfaces"""

import os
import re

import pytest
from playwright.sync_api import Page, expect, sync_playwright
from pytest_bdd import given, parsers, scenarios, then, when

from .config import ADMIN_PASSWORD, Urls

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


@then('I should see "Primitive Tokens"')
def see_primitive_tokens_text(page: Page):
    """Verify the Primitive Tokens section heading is visible."""
    expect(page.locator("body")).to_contain_text("Primitive Tokens")


# Design Token Tests


@then("I should see the primary token box")
def see_primary_token_box(page: Page):
    """Verify the primary token box is visible."""
    token_box = page.locator("#token-primary")
    expect(token_box).to_be_visible()
    expect(token_box).to_contain_text("Burnt Orange")


@then("the primary token box should have the brand orange background")
def primary_token_has_orange_background(page: Page):
    """Verify design token --color-burnt-orange (#FF7043) is applied."""
    token_box = page.locator("#token-primary")
    # Burnt orange #FF7043 = rgb(255, 112, 67)
    background_color = token_box.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(255, 112, 67)", f"Expected burnt orange, got {background_color}"


@then("I should see the secondary token box")
def see_secondary_token_box(page: Page):
    """Verify the secondary token box is visible."""
    token_box = page.locator("#token-secondary")
    expect(token_box).to_be_visible()
    expect(token_box).to_contain_text("Dark Grey")


@then("the secondary token box should have the brand plum background")
def secondary_token_has_plum_background(page: Page):
    """Verify design token --color-dark-grey (#424242) is applied."""
    token_box = page.locator("#token-secondary")
    # Dark grey #424242 = rgb(66, 66, 66)
    background_color = token_box.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(66, 66, 66)", f"Expected dark grey, got {background_color}"


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
    expect(button).to_contain_text("Submit")


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
    expect(button).to_contain_text("Cancel")


@then("I should see the disabled button")
def see_disabled_button(page: Page):
    """Verify the disabled button is visible."""
    button = page.locator("#btn-disabled")
    expect(button).to_be_visible()
    expect(button).to_contain_text("Disabled")


@then("the primary button should have the brand orange background")
def primary_button_has_orange_background(page: Page):
    """Verify primary button uses --color-button-primary-bg (burnt orange #FF7043)."""
    button = page.locator("#btn-primary")
    # Burnt orange #FF7043 = rgb(255, 112, 67)
    background_color = button.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(255, 112, 67)", f"Expected burnt orange, got {background_color}"


@then("the secondary button should have the brand plum background")
def secondary_button_has_plum_background(page: Page):
    """Verify secondary button uses --color-button-secondary-bg (dark grey #424242)."""
    button = page.locator("#btn-secondary")
    # Dark grey #424242 = rgb(66, 66, 66)
    background_color = button.evaluate("el => getComputedStyle(el).backgroundColor")
    assert background_color == "rgb(66, 66, 66)", f"Expected dark grey, got {background_color}"


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


# Typography Tests


@then("I should see the typography section")
def see_typography_section(page: Page):
    """Verify the Typography section heading is visible."""
    expect(page.locator("body")).to_contain_text("Typography")


@then('I should see "Semantic Tokens"')
def see_semantic_tokens_text(page: Page):
    """Verify the Semantic Tokens sub-heading is visible."""
    expect(page.locator("body")).to_contain_text("Semantic Tokens")


@then('I should see "Use Cases"')
def see_use_cases_text(page: Page):
    """Verify the Use Cases sub-heading is visible."""
    expect(page.locator("body")).to_contain_text("Use Cases")


@then(parsers.parse("the {token} sample should use the Oswald font"))
def sample_uses_oswald_font(page: Page, token: str):
    """Verify a typography sample uses the Oswald font family."""
    element = page.locator(f"#typo-{token}")
    font_family = element.evaluate("el => getComputedStyle(el).fontFamily")
    assert "Oswald" in font_family, f"Expected Oswald font for {token}, got {font_family}"


@then(parsers.parse("the {token} sample should use the Lato font"))
def sample_uses_lato_font(page: Page, token: str):
    """Verify a typography sample uses the Lato font family."""
    element = page.locator(f"#typo-{token}")
    font_family = element.evaluate("el => getComputedStyle(el).fontFamily")
    assert "Lato" in font_family, f"Expected Lato font for {token}, got {font_family}"


@then(parsers.parse("the {token} sample should have font size {size}"))
def sample_has_font_size(page: Page, token: str, size: str):
    """Verify a typography sample has the expected computed font size."""
    element = page.locator(f"#typo-{token}")
    font_size = element.evaluate("el => getComputedStyle(el).fontSize")
    assert font_size == size, f"Expected font size {size} for {token}, got {font_size}"


@then("the overline sample should be uppercase")
def overline_is_uppercase(page: Page):
    """Verify the overline sample has text-transform: uppercase."""
    element = page.locator("#typo-overline")
    text_transform = element.evaluate("el => getComputedStyle(el).textTransform")
    assert text_transform == "uppercase", f"Expected uppercase, got {text_transform}"


# Dashboard Tests (Protected Route)


def _login_admin(page: Page, admin_user) -> None:
    """Helper to log in as admin user."""
    page.context.clear_cookies()
    page.goto(Urls.login)
    page.fill('input[name="email"]', admin_user.email)
    page.fill('input[name="password"]', ADMIN_PASSWORD)
    page.click('button[type="submit"]')
    page.wait_for_url(Urls.dashboard)


@given("I am not logged in")
def not_logged_in(page: Page):
    """Ensure user is not logged in by clearing cookies."""
    page.context.clear_cookies()


@given("I am logged in as an admin user")
def logged_in_as_admin(page: Page, admin_user):
    """Log in as admin user."""
    _login_admin(page, admin_user)


@given(parsers.parse('there is an assembly called "{title}"'))
def create_test_assembly(title: str, admin_user, test_database):
    """Create a test assembly for the admin user."""
    from opendlp.service_layer.assembly_service import create_assembly
    from opendlp.service_layer.unit_of_work import SqlAlchemyUnitOfWork

    session_factory = test_database
    uow = SqlAlchemyUnitOfWork(session_factory)
    create_assembly(
        uow=uow,
        title=title,
        created_by_user_id=admin_user.id,
    )


@when("I try to access the backoffice dashboard")
def try_access_backoffice_dashboard(page: Page):
    """Attempt to access the backoffice dashboard."""
    page.goto(Urls.backoffice_dashboard)


@when("I visit the backoffice dashboard")
def visit_backoffice_dashboard(page: Page):
    """Navigate to the backoffice dashboard."""
    page.goto(Urls.backoffice_dashboard)


@then("I should be redirected to the login page")
def redirected_to_login(page: Page):
    """Verify user was redirected to login page (with optional next parameter)."""
    expect(page).to_have_url(re.compile(r".*/auth/login.*"), timeout=5000)


@then('I should see "Dashboard"')
def see_dashboard_text(page: Page):
    """Verify Dashboard heading is visible."""
    heading = page.locator("h1")
    expect(heading).to_contain_text("Dashboard")


@then('I should see "Welcome back"')
def see_welcome_back_text(page: Page):
    """Verify Welcome back text is visible."""
    expect(page.locator("body")).to_contain_text("Welcome back")


@then(parsers.parse('I should see an assembly card with title "{title}"'))
def see_assembly_card_with_title(page: Page, title: str):
    """Verify an assembly card with the given title is visible."""
    card = page.locator(".assembly-card", has_text=title)
    expect(card).to_be_visible()
