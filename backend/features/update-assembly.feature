Feature: Update Assembly.
  As an Assembly Manager
  I want to be able to update an Assembly
  So that I can see update the details for others to see and to allow actions that need data.

  Scenario: Edit Assembly
    Given there is an assembly created
    And the user opens the update assembly page for an assembly
    When the user fills in the question field with "What should Liliput do about the Climate Emergency?"
    And the form is submitted
    Then the user should be redirected to the view assembly page after edit
    And the assembly question "What should Liliput do about the Climate Emergency?" should be visible
