Feature: Scroll Position Preservation
  As a user navigating through paginated content
  I want my scroll position to be preserved across page reloads
  So that I don't lose my place when clicking pagination links

  Background:
    Given a user is logged in as an admin

  Scenario: Scroll position is preserved when clicking pagination
    Given the user is on a page with paginated content
    And the user has scrolled down to position 1000 pixels
    When the user clicks the "Next" pagination link
    Then the page should reload
    And the scroll position should be restored to approximately 1000 pixels
    And the URL should not contain a scroll parameter

  Scenario: Scroll position is preserved when submitting a form
    Given the user is on a page with a form
    And the user has scrolled down to position 500 pixels
    When the user submits the form
    Then the page should reload or redirect
    And the scroll position should be restored to approximately 500 pixels
    And the URL should not contain a scroll parameter

  Scenario: Manual scroll removes scroll parameter
    Given the user is on a page with scroll=1000 in the URL
    When the user manually scrolls to position 400 pixels
    And waits for 200 milliseconds
    Then the scroll parameter should be removed from the URL

  Scenario: Page reload without scroll parameter goes to top
    Given the user is on a page without a scroll parameter
    And the user has scrolled down to position 800 pixels
    When the user reloads the page
    Then the scroll position should be at the top (0 pixels)

  Scenario: Using $preserveScroll magic helper on links
    Given the user is on a page with Alpine.js enabled
    And the page has a link with :href="$preserveScroll('/target')"
    And the user has scrolled to position 1200 pixels
    When the user clicks the link
    Then the browser should navigate to "/target?scroll=1200"
