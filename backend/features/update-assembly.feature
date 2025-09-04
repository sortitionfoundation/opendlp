Feature: Update Assembly.
  As an Assembly Manager
  I want to be able to update an Assembly
  So that I can see update the details for others to see and to allow actions that need data.

  Scenario: Edit Assembly
    Given there is an assembly created
    And the user starts editing the assembly
    When the user makes the question "What should Liliput do about the Climate Emergency?"
    And the user finishes editing the assembly
    Then the user should see the edited assembly
    And the user should see the assembly question "What should Liliput do about the Climate Emergency?"
