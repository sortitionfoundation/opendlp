Feature: Selection History
  As an Assembly Organiser
  I want to view the history of selection runs
  So that I can track past selections and review their outcomes.

  Background:
    Given a user is logged in as an admin

  Scenario: View selection page with no history
    Given an assembly with gsheet configured but no selection runs
    When the user visits the selection page
    Then the empty state message is displayed

  Scenario: View selection history with records
    Given an assembly with several selection runs
    When the user visits the selection page
    Then the history table displays all runs with correct details
    And the View links are present

  Scenario: Navigate through paginated selection history
    Given an assembly with more than 15 selection runs
    When the user visits the selection page
    Then the first page is displayed with 15 runs
    And the Next pagination link is visible
    And the Previous pagination is disabled
    When the user clicks the Next pagination link
    Then the second page is displayed
    And the Previous pagination link is visible
    When the user clicks the Previous pagination link
    Then the first page is displayed

  Scenario: View details of a selection run from history
    Given an assembly with a completed selection run
    When the user visits the selection page
    And the user clicks View on a history record
    Then the user is redirected to the selection run details page

  Scenario: Verify status tags display correctly
    Given an assembly with runs in different statuses
    When the user visits the selection page
    Then each status is displayed in the history table
