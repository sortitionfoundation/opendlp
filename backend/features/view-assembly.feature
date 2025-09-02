Feature: View Assembly.
  As an Assembly Manager
  I want to be able to view an Assembly
  So that I can see the state of the Assembly and get to the next action.

  Scenario: View Assembly
    Given there is an assembly created
    When the user opens the view assembly page for an assembly
    Then the user should see the "title" of the Assembly
    And the user should see the "question" of the Assembly
