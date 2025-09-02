Feature: Create Assembly.
  As an Admin
  I want to be able to create Assemblies
  So that I can see the state of the Assembly and get to the next action.

  Scenario: Create Assembly
    Given the user opens the create assembly page
    When the user fills in the title field with "Liliput Climate Assembly"
    And the form is submitted
    Then the user should be redirected to the view assembly page after create
    And the assembly title "Liliput Climate Assembly" should be visible
