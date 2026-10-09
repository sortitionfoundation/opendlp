Feature: One writing task per assembly
  As an Assembly Manager
  I want a second selection on the same assembly to be refused while one is running
  So that two runs can never write over each other.

  Background:
    Given a user is logged in as an admin

  Scenario: Run Selection while another selection has already started
    Given a database assembly ready for selection
    When the user visits the selection page
    And a selection starts on that assembly from somewhere else
    And the user clicks Run Selection
    Then the user is told another task is already running
    And the running selection's progress dialog is displayed with a Cancel Task button
    When the user cancels the running selection
    Then the progress dialog shows the task as cancelled
