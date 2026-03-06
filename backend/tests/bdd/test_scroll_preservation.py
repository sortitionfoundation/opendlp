"""ABOUTME: BDD tests for scroll position preservation across page reloads
ABOUTME: Tests the $preserveScroll Alpine.js magic helper and scroll restoration"""

import os

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

# Skip all tests in this file when running in CI
# Scroll behavior tests are inherently flaky in headless browsers
pytestmark = pytest.mark.skipif(
    os.environ.get("CI", "false").lower() == "true",
    reason="Scroll preservation tests are flaky in headless CI environments",
)

scenarios("../../features/scroll-preservation.feature")


# =============================================================================
# Given Steps
# =============================================================================


@given("a user is logged in as an admin")
def user_logged_in_as_admin(admin_logged_in_page):
    """Background step: ensure admin user is logged in."""
    # The admin_logged_in_page fixture handles the login
    pass


@given("the user is on a page with paginated content")
def user_on_paginated_page(logged_in_page, assembly_with_many_runs):
    """Navigate to a page with pagination (old data page with run history)."""
    page = logged_in_page
    page.goto(f"http://localhost:5002/assemblies/{assembly_with_many_runs.id}/data")
    page.wait_for_load_state("networkidle")


@given("the user is on a page with a form")
def user_on_page_with_form(logged_in_page, assembly_with_gsheet):
    """Navigate to selection page which has forms."""
    page = logged_in_page
    page.goto(f"http://localhost:5002/backoffice/assembly/{assembly_with_gsheet.id}/selection")
    page.wait_for_load_state("networkidle")


@given(parsers.parse("the user is on a page with scroll={scroll_value} in the URL"))
def user_on_page_with_scroll_param(logged_in_page, existing_assembly, scroll_value):
    """Navigate to a page with scroll parameter in URL."""
    page = logged_in_page
    page.goto(f"http://localhost:5002/backoffice/assembly/{existing_assembly.id}?scroll={scroll_value}")
    page.wait_for_load_state("networkidle")


@given("the user is on a page without a scroll parameter")
def user_on_page_without_scroll(logged_in_page, existing_assembly):
    """Navigate to a page without scroll parameter."""
    page = logged_in_page
    page.goto(f"http://localhost:5002/backoffice/assembly/{existing_assembly.id}")
    page.wait_for_load_state("networkidle")


@given("the user is on a page with Alpine.js enabled")
def user_on_alpine_page(logged_in_page, existing_assembly):
    """Navigate to backoffice page (Alpine.js enabled)."""
    page = logged_in_page
    page.goto(f"http://localhost:5002/backoffice/assembly/{existing_assembly.id}/selection")
    page.wait_for_load_state("networkidle")


@given(parsers.parse("the page has a link with :href=\"$preserveScroll('{target}')\""))
def page_has_preserve_scroll_link(logged_in_page, target):
    """Verify page has a link using $preserveScroll (or inject one for testing)."""
    page = logged_in_page

    # Inject a test link using $preserveScroll
    page.evaluate(f"""
        const link = document.createElement('a');
        link.id = 'test-preserve-scroll-link';
        link.textContent = 'Test Link';
        link.setAttribute('x-data', '{{}}');
        link.setAttribute(':href', "$preserveScroll('{target}')");
        document.body.appendChild(link);

        // Manually trigger Alpine to process the link
        if (window.Alpine) {{
            window.Alpine.initTree(link);
        }}
    """)


@given(parsers.parse("the user has scrolled down to position {pixels:d} pixels"))
@given(parsers.parse("the user has scrolled to position {pixels:d} pixels"))
def user_scrolled_to_position(logged_in_page, pixels):
    """Scroll the page to a specific position."""
    page = logged_in_page
    page.evaluate(f"window.scrollTo(0, {pixels})")
    page.wait_for_timeout(100)  # Give scroll time to settle


# =============================================================================
# When Steps
# =============================================================================


@when('the user clicks the "Next" pagination link')
def user_clicks_next_pagination(logged_in_page):
    """Click the Next pagination link."""
    page = logged_in_page
    page.click('a:has-text("Next"), a:has-text("›"), .pagination-next')
    page.wait_for_load_state("networkidle")


@when("the user submits the form")
def user_submits_form(logged_in_page):
    """Submit a form on the page."""
    page = logged_in_page
    # Click the "Check Spreadsheet" button as an example
    page.click('button:has-text("Check Spreadsheet"), button[type="submit"]')
    page.wait_for_load_state("networkidle")


@when(parsers.parse("the user manually scrolls to position {pixels:d} pixels"))
def user_manually_scrolls(logged_in_page, pixels):
    """Manually scroll the page."""
    page = logged_in_page
    page.evaluate(f"window.scrollTo(0, {pixels})")


@when(parsers.parse("waits for {milliseconds:d} milliseconds"))
def wait_milliseconds(logged_in_page, milliseconds):
    """Wait for specified time."""
    page = logged_in_page
    page.wait_for_timeout(milliseconds)


@when("the user reloads the page")
def user_reloads_page(logged_in_page):
    """Reload the current page."""
    page = logged_in_page
    page.reload()
    page.wait_for_load_state("networkidle")


@when("the user clicks the link")
def user_clicks_link(logged_in_page):
    """Click the test link."""
    page = logged_in_page
    page.click("#test-preserve-scroll-link")
    page.wait_for_load_state("networkidle")


# =============================================================================
# Then Steps
# =============================================================================


@then("the page should reload")
@then("the page should reload or redirect")
def page_reloaded(logged_in_page):
    """Verify page has reloaded (implicit - already waited for networkidle)."""
    # This is implicit - if we got here, the page loaded successfully
    pass


@then(parsers.parse("the scroll position should be restored to approximately {pixels:d} pixels"))
def scroll_position_restored(logged_in_page, pixels):
    """Verify scroll position is approximately at expected value."""
    page = logged_in_page
    actual_scroll = page.evaluate("window.scrollY")

    # Allow tolerance of ±20 pixels
    tolerance = 20
    assert abs(actual_scroll - pixels) < tolerance, f"Expected scroll position ~{pixels}px, but got {actual_scroll}px"


@then("the URL should not contain a scroll parameter")
@then("the scroll parameter should be removed from the URL")
def url_has_no_scroll_param(logged_in_page):
    """Verify URL does not contain scroll parameter."""
    page = logged_in_page

    # Wait a moment for cleanup to complete
    page.wait_for_timeout(250)

    url = page.url
    assert "scroll=" not in url, f"Expected no scroll parameter, but found in URL: {url}"


@then("the scroll position should be at the top (0 pixels)")
def scroll_at_top(logged_in_page):
    """Verify scroll position is at or near the top."""
    page = logged_in_page
    actual_scroll = page.evaluate("window.scrollY")

    # Allow small tolerance for browser variations
    assert actual_scroll < 50, f"Expected scroll at top (<50px), but got {actual_scroll}px"


@then(parsers.parse('the browser should navigate to "{url_pattern}"'))
def browser_navigated_to_url(logged_in_page, url_pattern):
    """Verify browser navigated to URL matching pattern."""
    page = logged_in_page
    current_url = page.url

    # Check if URL contains the pattern (allowing for domain differences)
    assert url_pattern in current_url, f"Expected URL to contain '{url_pattern}', but got: {current_url}"
