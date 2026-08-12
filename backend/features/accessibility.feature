Feature: Component Accessibility
  As a keyboard or screen reader user
  I want UI components to follow WAI-ARIA best practices
  So that I can navigate and interact with the application effectively

  Background:
    Given a user is logged in as an admin

  # =============================================================================
  # Focus Preservation Tests
  # Note: Focus restoration on page load requires element persistence across
  # navigations. These tests verify the mechanisms are in place.
  # =============================================================================

  Scenario: Focus preservation code is loaded
    Given a page with Alpine.js and focus preservation
    Then the $focusUrl magic helper should be available
    And the x-focus-preserve directive should be registered

  Scenario: Tabs have focus preservation attributes
    Given the user is on a page with tabs component
    Then tab links should have data-focus-id attributes
    And tab links should have x-focus-preserve directive

  # =============================================================================
  # Tabs Keyboard Navigation Tests
  # Note: Tabs use automatic activation (navigate on focus), so keyboard tests
  # verify the component structure rather than focus movement after navigation.
  # =============================================================================

  Scenario: Tab component - has keyboard handler attached
    Given the user is on a page with tabs component
    Then the tablist should have tabsKeyboard data component
    And the tablist should have keydown handler

  Scenario: Tab component - has correct ARIA attributes
    Given the user is on a page with tabs component
    Then the tablist should have role="tablist"
    And each tab should have role="tab"
    And the active tab should have aria-selected="true"
    And inactive tabs should have aria-selected="false"
    And disabled tabs should have aria-disabled="true"

  Scenario: Tab component - roving tabindex pattern
    Given the user is on a page with tabs component
    Then the active tab should have tabindex="0"
    And inactive tabs should have tabindex="-1"

  # =============================================================================
  # Button Accessibility Tests
  # =============================================================================

  Scenario: Icon-only buttons have aria-label
    Given the user is on a page with icon buttons
    Then each icon-only button should have an aria-label

  Scenario: Toggle buttons have aria-pressed attribute
    Given the user is on a page with toggle buttons
    Then toggle buttons should have aria-pressed attribute

  # =============================================================================
  # Search Dropdown (Autocomplete) Accessibility Tests
  # =============================================================================

  Scenario: Search dropdown component has correct ARIA structure
    Given the user is on the assembly members page
    Then the page should have a search dropdown with role="combobox"
    And the search input should have aria-autocomplete="list"
    And the search input should have aria-haspopup="listbox"
    And the page should have a live region for screen reader announcements

  # =============================================================================
  # Select Dropdown Component Tests
  # =============================================================================

  Scenario: Select dropdown has required ARIA attributes when required
    Given a page with a required select dropdown
    Then the select should have aria-required="true"

  Scenario: Select dropdown has invalid state when error present
    Given a page with a select dropdown in error state
    Then the select should have aria-invalid="true"
    And the select should have aria-describedby pointing to the error message

  Scenario: Select dropdown label is properly associated
    Given a page with a labeled select dropdown
    Then the label should have a for attribute matching the select id
