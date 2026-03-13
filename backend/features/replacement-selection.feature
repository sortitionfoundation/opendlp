Feature: Replacement Selection
  As an Assembly Manager
  I want to select replacement participants
  When original selections decline or cannot participate.

  Background:
    Given a user is logged in as an admin

  # =============================================================================
  # Replacement Modal Access
  # =============================================================================

  Scenario: Open replacement modal from selection page
    Given an assembly with gsheet configured
    When the user visits the selection page
    And the user clicks the Replacements button
    Then the replacement modal is displayed
    And the Check Spreadsheet button is visible

  Scenario: Replacement modal shows loading state
    Given an assembly with gsheet configured
    When the user opens the replacement modal
    And the user clicks Check Spreadsheet
    Then the modal shows a loading spinner
    And the status shows Running or Pending

  # =============================================================================
  # Replacement Load Task
  # =============================================================================

  Scenario: Load spreadsheet for replacement selection
    Given an assembly with gsheet configured
    When the user opens the replacement modal
    And the user clicks Check Spreadsheet
    And the load task completes successfully
    Then the modal shows the available replacement count
    And the number input field is visible
    And the Run Replacements button is visible

  Scenario: Load task shows selection range information
    Given an assembly with gsheet configured
    When the user opens the replacement modal
    And the user clicks Check Spreadsheet
    And the load task completes successfully
    Then the modal shows the available replacement count
    And the Re-check Spreadsheet button is visible

  # =============================================================================
  # Replacement Run Task
  # =============================================================================

  Scenario: Run replacement selection
    Given an assembly with gsheet configured
    And the replacement load task has completed
    When the user enters the number to select
    And the user clicks Run Replacements
    Then the modal shows a loading spinner
    And the Cancel Task button is visible

  Scenario: Replacement selection completes successfully
    Given an assembly with gsheet configured
    And the replacement load task has completed
    When the user enters the number to select
    And the user clicks Run Replacements
    And the replacement task completes
    Then the modal shows Completed status
    And the result message shows success
    And the Close button is visible

  # =============================================================================
  # Task Cancellation
  # =============================================================================

  Scenario: Cancel running replacement task
    Given an assembly with gsheet configured
    And the replacement load task has completed
    When the user enters the number to select
    And the user clicks Run Replacements
    And the user clicks Cancel Task
    Then the modal shows Cancelled status

  # =============================================================================
  # Modal Close Behavior
  # =============================================================================

  Scenario: Close modal after task completion
    Given an assembly with gsheet configured
    And a completed replacement task exists
    When the user opens the replacement modal with the completed task
    And the user clicks Close
    Then the user is returned to the selection page
    And the replacement modal is not visible

  Scenario: Cannot close modal while task is running
    Given an assembly with gsheet configured
    And the replacement load task has completed
    When the user enters the number to select
    And the user clicks Run Replacements
    Then the Close button is not visible
    And the modal cannot be closed by clicking backdrop

  # =============================================================================
  # Re-check Spreadsheet
  # =============================================================================

  Scenario: Re-check spreadsheet after load
    Given an assembly with gsheet configured
    And the replacement load task has completed
    When the user clicks Re-check Spreadsheet
    Then a new load task starts
    And the modal shows loading state

  # =============================================================================
  # Selection History Integration
  # =============================================================================

  Scenario: Replacement tasks appear in selection history
    Given an assembly with gsheet configured
    And a completed replacement task exists
    When the user visits the selection page
    Then the selection history shows the replacement task
    And the task type shows as Replace Selection
