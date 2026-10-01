Feature: Replacement Selection from the database
  As an Assembly Manager
  I want to select replacements from the respondents held in the database
  When people who were selected have withdrawn.

  Background:
    Given a user is logged in as an admin

  Scenario: Review the replacement targets before running
    Given a database assembly where one selected person has withdrawn
    When the user visits the selection page
    And the user opens the replacement selection dialog
    Then the dialog shows how many places are to be filled
    And the dialog shows the calculated replacement targets
    And the Run Replacement Selection button is visible

  Scenario: Run a replacement selection
    Given a database assembly where one selected person has withdrawn
    When the user visits the selection page
    And the user opens the replacement selection dialog
    And the user clicks Run Replacement Selection
    Then the task progress dialog is displayed
    And the replacement selection completes
    And the withdrawn place has been filled from the pool

  Scenario: Accept the algorithm's suggestions when the targets cannot be met
    Given a database assembly whose replacement targets cannot all be met from the pool
    When the user visits the selection page
    And the user opens the replacement selection dialog
    Then the dialog lists the suggested changes to the targets
    When the user accepts all the suggestions
    Then the suggested minimum is in its target cell and the suggestions are gone
    When the user clicks Recheck feasibility
    Then the dialog says the targets can be met
